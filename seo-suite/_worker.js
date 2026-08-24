/**
 * Cloudflare Pages _worker.js for the SEO Suite dashboard.
 * Routes /api/* to Supabase and serves the static SPA for everything else.
 */

function sbHeaders(env) {
  return {
    apikey: env.SUPABASE_ANON_KEY,
    Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
    Accept: "application/json",
  };
}

async function sbFetch(env, path, _retried = false) {
  const url = `${env.SUPABASE_URL}/rest/v1${path}`;
  const res = await fetch(url, { headers: sbHeaders(env) });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    // Graceful degradation while supabase_schema_patch_v3.sql is unapplied:
    // the property column doesn't exist yet, so retry without that filter
    // (all legacy rows are vantagecircle anyway).
    if (!_retried && /column .*property.* does not exist/.test(text)) {
      return sbFetch(env, path.replace(/([&?])property=eq\.[^&]*/g, "$1").replace(/[?&]$/, ""), true);
    }
    throw new Error(`Supabase ${res.status}: ${text}`);
  }
  return res.json();
}

// Paginated variant: a `select=day` inventory over a 993-keyword property
// returns one row per keyword per day, so a bare limit=1000 only sees the
// latest day. Page until a short page arrives.
async function sbFetchAll(env, path, pageSize = 1000) {
  const sep = path.includes("?") ? "&" : "?";
  const out = [];
  for (let offset = 0; ; offset += pageSize) {
    const page = await sbFetch(env, `${path}${sep}limit=${pageSize}&offset=${offset}`);
    out.push(...page);
    if (page.length < pageSize) break;
  }
  return out;
}

async function sbPost(env, table, body, prefer = "return=representation") {
  const url = `${env.SUPABASE_URL}/rest/v1/${encodeURIComponent(table)}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { ...sbHeaders(env), "Content-Type": "application/json", Prefer: prefer },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Supabase ${res.status}: ${text}`);
  }
  if (prefer === "return=minimal" || res.status === 204) return { ok: true };
  const text = await res.text();
  return text ? JSON.parse(text) : { ok: true };
}

async function sbPatch(env, table, filters, body) {
  const qs = Object.entries(filters)
    .map(([k, v]) => `${encodeURIComponent(k)}=eq.${encodeURIComponent(v)}`)
    .join("&");
  const url = `${env.SUPABASE_URL}/rest/v1/${encodeURIComponent(table)}?${qs}`;
  const res = await fetch(url, {
    method: "PATCH",
    headers: { ...sbHeaders(env), "Content-Type": "application/json", Prefer: "return=minimal" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Supabase ${res.status}: ${text}`);
  }
  return { ok: true };
}

function todayISO() {
  return new Date().toISOString().split("T")[0];
}

function daysAgoISO(n) {
  return new Date(Date.now() - n * 86400000).toISOString().split("T")[0];
}

function jsonError(message, status = 500) {
  return Response.json({ error: message }, { status, headers: { "Content-Type": "application/json" } });
}

const YOU = "vantage circle";  // summary card tracks the VC project
const NOT_FOUND = 101;
const PROPERTIES = {
  vantagecircle: {
    label: "Vantage Circle",
    domain: "vantagecircle.com",
    you: "vantage circle",
    brands: ["vantage circle", "bonusly", "kudos", "achievers", "awardco",
             "nectar", "motivosity", "o.c. tanner", "workhuman"],
  },
  vantagefit: {
    label: "Vantage Fit",
    domain: "vantagefit.io",
    you: "vantage fit",
    brands: ["vantage fit", "personify health", "virgin pulse", "wellable",
             "limeade", "incentfit", "wellsteps", "sonic boom", "woliba"],
  },
};

// ---------------------------------------------------------------- /api/summary
// Batched rewrite: 1 query for day inventory, then 1 query per property
// covering latest + previous day (run in parallel). Replaces the old
// latestRankByProperty / previousRankDays / biggestMover N+1 chain.
async function rankSummary(env) {
  const rows = await sbFetchAll(
    env,
    "/rank_snapshots?select=property,day&order=day.desc"
  );
  const byProp = {};
  for (const r of rows) {
    const p = (byProp[r.property] ||= { counts: {} });
    p.counts[r.day] = (p.counts[r.day] || 0) + 1;
  }
  const props = Object.keys(byProp);
  if (!props.length) return { summary: {}, mover: null };

  const perProp = await Promise.all(
    props.map(async (prop) => {
      const days = Object.entries(byProp[prop].counts)
        .map(([day, count]) => ({ day, count }))
        .sort((a, b) => b.day.localeCompare(a.day));
      const fullest = Math.max(...days.map((d) => d.count));
      const valid = days.filter((d) => d.count >= fullest / 2).map((d) => d.day);
      const latest = valid[0];
      const previous = valid.length > 1 ? valid[1] : null;

      const dayFilter = previous ? `in.(${latest},${previous})` : `eq.${latest}`;
      const snaps = await sbFetch(
        env,
        `/rank_snapshots?select=keyword,position,day&property=eq.${encodeURIComponent(prop)}&day=${dayFilter}`
      );

      const cur = snaps.filter((s) => s.day === latest);
      const ranked = cur.filter((s) => s.position !== null && s.position !== undefined);
      const info = {
        latest_day: latest,
        previous_day: previous,
        count: cur.length,
        ranked: ranked.length,
        top3: ranked.filter((s) => s.position <= 3).length,
        top10: ranked.filter((s) => s.position <= 10).length,
        top50: ranked.filter((s) => s.position <= 50).length,
      };

      let mover = null;
      if (previous) {
        const prev = {};
        for (const s of snaps) if (s.day === previous) prev[s.keyword] = s.position;
        for (const s of cur) {
          const p = prev[s.keyword];
          if (p === undefined) continue;
          const delta = (p === null ? NOT_FOUND : p) - (s.position === null ? NOT_FOUND : s.position);
          if (!mover || delta > mover.delta) {
            mover = { keyword: s.keyword, property: prop, delta, previous: p, current: s.position };
          }
        }
      }
      return { prop, info, mover };
    })
  );

  const summary = {};
  let best = null;
  for (const { prop, info, mover } of perProp) {
    summary[prop] = info;
    if (mover && (!best || mover.delta > best.delta)) best = mover;
  }
  return { summary, mover: best };
}

async function handleSummary(env) {
  const [rankBlock, llmDayRow, freshDayRow, compSnaps] = await Promise.all([
    rankSummary(env),
    sbFetch(env, "/llm_snapshots?select=day&property=eq.vantagecircle&order=day.desc&limit=1"),
    sbFetch(env, "/freshness_scores?select=day&order=day.desc&limit=1"),
    sbFetch(
      env,
      "/competitor_snapshots?select=property,competitor,total_urls&order=day.desc&limit=200"
    ),
  ]);

  // Latest + previous referring-domain totals across both properties
  const backlinkByProp = await Promise.all(
    Object.keys(PROPERTIES).map(async (prop) => {
      const rows = await sbFetch(
        env,
        `/backlink_snapshots?select=*&property=eq.${encodeURIComponent(prop)}&order=day.desc&limit=2`
      );
      return { prop, latest: rows[0] || null, previous: rows[1] || null };
    })
  );
  let latestRefdomains = 0, previousRefdomains = 0;
  let latestBlDay = "", previousBlDay = "";
  for (const { latest, previous } of backlinkByProp) {
    if (latest) {
      latestRefdomains += latest.refdomains || 0;
      if (latest.day > latestBlDay) latestBlDay = latest.day;
    }
    if (previous) {
      previousRefdomains += previous.refdomains || 0;
      if (previous.day > previousBlDay) previousBlDay = previous.day;
    }
  }
  const backlinkSummary = {
    latest: { refdomains: latestRefdomains, day: latestBlDay },
    previous: previousBlDay ? { refdomains: previousRefdomains, day: previousBlDay } : null,
  };

  const [llm, freshness] = await Promise.all([
    (async () => {
      if (!llmDayRow.length) return { day: null, count: 0, sov: 0 };
      const day = llmDayRow[0].day;
      const answers = await sbFetch(env, `/llm_snapshots?select=mentions&day=eq.${day}&property=eq.vantagecircle`);
      let you = 0;
      for (const a of answers) {
        const m = JSON.parse(a.mentions || "{}");
        if (m[YOU]) you++;
      }
      return { day, count: answers.length, sov: answers.length ? Math.round((you / answers.length) * 100) : 0 };
    })(),
    (async () => {
      if (!freshDayRow.length) return { day: null, total: 0, counts: {} };
      const day = freshDayRow[0].day;
      const rows = await sbFetch(env, `/freshness_scores?select=action&day=eq.${day}`);
      const counts = {};
      for (const r of rows) counts[r.action] = (counts[r.action] || 0) + 1;
      return { day, total: rows.length, counts };
    })(),
  ]);

  const competitors = {};
  for (const row of compSnaps) {
    const c = (competitors[row.property] ||= { competitors: [], total_urls: 0 });
    if (!c.competitors.includes(row.competitor)) {
      c.competitors.push(row.competitor);
      c.total_urls += row.total_urls || 0;
    }
  }

  return {
    rank: rankBlock.summary,
    backlinks: backlinkSummary,
    llm,
    freshness,
    competitors,
    biggest_mover: rankBlock.mover,
  };
}

// ------------------------------------------------------------------ /api/rank
async function propDays(env, property) {
  const rows = await sbFetchAll(
    env,
    `/rank_snapshots?select=day&property=eq.${encodeURIComponent(property)}&order=day.desc`
  );
  if (!rows.length) return [];
  const counts = {};
  for (const r of rows) counts[r.day] = (counts[r.day] || 0) + 1;
  const days = Object.entries(counts)
    .map(([day, count]) => ({ day, count }))
    .sort((a, b) => b.day.localeCompare(a.day));
  const fullest = Math.max(...days.map((d) => d.count));
  return days.filter((d) => d.count >= fullest / 2).map((d) => d.day);
}

async function handleRank(env, url) {
  const property = url.searchParams.get("property") || "vantagecircle";
  const days = await propDays(env, property);
  if (!days.length) {
    return { property, keywords: [], latest_day: null, previous_day: null };
  }

  const latestDay = days[0];
  const previousDay = days.length > 1 ? days[1] : null;
  const histDays = days.slice(0, 8);

  const [rankRows, prevRows, metaRows, histRows] = await Promise.all([
    sbFetch(
      env,
      `/rank_snapshots?select=keyword,position,url,serp_features&property=eq.${encodeURIComponent(property)}&day=eq.${latestDay}`
    ),
    previousDay
      ? sbFetch(
          env,
          `/rank_snapshots?select=keyword,position&property=eq.${encodeURIComponent(property)}&day=eq.${previousDay}`
        )
      : Promise.resolve([]),
    sbFetch(env, `/keyword_meta?select=*&property=eq.${encodeURIComponent(property)}`),
    histDays.length > 1
      ? sbFetchAll(
          env,
          `/rank_snapshots?select=keyword,position,day&property=eq.${encodeURIComponent(property)}&day=in.(${histDays.join(",")})`
        )
      : Promise.resolve([]),
  ]);

  const meta = {};
  for (const r of metaRows) meta[r.keyword] = r;
  const prev = {};
  for (const r of prevRows) prev[r.keyword] = r.position;

  // Per-keyword position history, newest first, for sparklines.
  const historyByKw = {};
  for (const r of histRows) {
    const byDay = (historyByKw[r.keyword] ||= {});
    byDay[r.day] = r.position;
  }
  const historyList = {};
  for (const [kw, byDay] of Object.entries(historyByKw)) {
    historyList[kw] = histDays.map((d) => (d in byDay ? byDay[d] : null));
  }

  const keywords = rankRows.map((r) => {
    const m = meta[r.keyword] || {};
    return {
      keyword: r.keyword,
      position: r.position,
      previous_position: prev[r.keyword] !== undefined ? prev[r.keyword] : null,
      history: historyList[r.keyword] || [],
      url: r.url,
      serp_features: r.serp_features,
      tag: m.tag || "",
      volume: m.volume,
      kd: m.kd,
      cpc: m.cpc,
      intent: m.intent,
      traffic_cur: m.traffic_cur,
      traffic_prev: m.traffic_prev,
      branded: m.branded,
    };
  });

  keywords.sort((a, b) => {
    const aRank = a.position !== null && a.position !== undefined;
    const bRank = b.position !== null && b.position !== undefined;
    if (aRank && !bRank) return -1;
    if (!aRank && bRank) return 1;
    const ap = a.position === null ? 999 : a.position;
    const bp = b.position === null ? 999 : b.position;
    if (ap !== bp) return ap - bp;
    return a.keyword.localeCompare(b.keyword);
  });

  return {
    property,
    keywords,
    latest_day: latestDay,
    previous_day: previousDay,
    meta: {
      total: keywords.length,
      tags: [...new Set(keywords.map((k) => k.tag).filter(Boolean))].sort(),
    },
  };
}

// -------------------------------------------------------------- /api/backlinks
async function handleBacklinks(env) {
  const [snapshots, events] = await Promise.all([
    sbFetch(env, "/backlink_snapshots?select=*&order=day.desc&limit=8"),
    sbFetch(env, "/refdomain_events?select=*&order=day.desc&limit=40"),
  ]);

  // Latest expanded snapshot day per property (snapshots are already ordered by day desc)
  const latestByProp = {};
  for (const r of snapshots) {
    if (!latestByProp[r.property]) latestByProp[r.property] = r.day;
  }

  const details = {};
  const domains = {};
  const anchors = {};
  const pages = {};
  await Promise.all(
    Object.entries(latestByProp).map(async ([prop, day]) => {
      const p = `&property=eq.${encodeURIComponent(prop)}`;
      const [d, dom, a, pg] = await Promise.all([
        sbFetchAll(env, `/backlink_details?select=*&day=eq.${day}${p}&order=rank.desc,source_url`),
        sbFetchAll(env, `/referring_domains?select=*&day=eq.${day}${p}&order=rank.desc,domain`),
        sbFetchAll(env, `/anchor_distribution?select=*&day=eq.${day}${p}&order=backlinks.desc,anchor`),
        sbFetchAll(env, `/backlink_pages?select=*&day=eq.${day}${p}&order=backlinks.desc,url`),
      ]);
      details[prop] = { day, rows: d };
      domains[prop] = { day, rows: dom };
      anchors[prop] = { day, rows: a };
      pages[prop] = { day, rows: pg };
    })
  );

  return { snapshots, events, details, domains, anchors, pages };
}

// ------------------------------------------------------------------- /api/llm
async function handleLlm(env, url) {
  const property = url.searchParams.get("property") || "vantagecircle";
  const cfg = PROPERTIES[property] || PROPERTIES.vantagecircle;
  const brands = cfg.brands;
  const p = `&property=eq.${encodeURIComponent(property)}`;

  // Trend only needs day+mentions; skip prompt/answer (the heavy columns)
  // and cap history at 180 days to keep the payload small.
  const cutoff = new Date(Date.now() - 180 * 86400000).toISOString().split("T")[0];
  const allRows = await sbFetch(
    env,
    `/llm_snapshots?select=day,mentions&day=gte.${cutoff}${p}&order=day.desc`
  );

  const trend = {};
  for (const r of allRows) {
    const day = r.day;
    trend[day] ||= { day, total: 0 };
    for (const b of brands) {
      trend[day][b] ||= 0;
    }
    const m = JSON.parse(r.mentions || "{}");
    trend[day].total += 1;
    for (const b of brands) {
      if (m[b]) trend[day][b] += 1;
    }
  }
  const trendArray = Object.values(trend).sort((a, b) => b.day.localeCompare(a.day));

  const dayRows = await sbFetch(
    env,
    `/llm_snapshots?select=day&property=eq.${encodeURIComponent(property)}&order=day.desc&limit=1`
  );
  let latest = [];
  let latestDay = null;
  if (dayRows.length) {
    latestDay = dayRows[0].day;
    latest = await sbFetch(
      env,
      `/llm_snapshots?select=day,platform,prompt,mentions,cited_mine,answer&day=eq.${latestDay}${p}&order=prompt,platform`
    );
  }

  const byPrompt = {};
  for (const r of latest) {
    byPrompt[r.prompt] ||= [];
    byPrompt[r.prompt].push(r);
  }

  const volDayRow = await sbFetch(
    env,
    `/volumes?select=day&property=eq.${encodeURIComponent(property)}&order=day.desc&limit=1`
  );
  let volumes = [];
  if (volDayRow.length) {
    volumes = await sbFetch(
      env,
      `/volumes?select=keyword,ai_search_volume,trend_json&day=eq.${volDayRow[0].day}${p}&order=ai_search_volume.desc&limit=200`
    );
  }

  const discovered = await sbFetch(
    env,
    `/discovered?select=query,platform,ai_search_volume,seed,prev_volume,volume_delta&property=eq.${encodeURIComponent(property)}&order=ai_search_volume.desc&limit=40`
  );

  const silentDayRow = await sbFetch(
    env,
    `/silent?select=day&property=eq.${encodeURIComponent(property)}&order=day.desc&limit=1`
  );
  let silent = { day: null, count: 0, previous_count: 0, rows: [] };
  if (silentDayRow.length) {
    const day = silentDayRow[0].day;
    const prevDayRow = await sbFetch(
      env,
      `/silent?select=day&property=eq.${encodeURIComponent(property)}&order=day.desc&limit=2`
    );
    let previousCount = 0;
    if (prevDayRow.length > 1 && prevDayRow[1].day !== day) {
      const prevRows = await sbFetch(
        env,
        `/silent?select=query&day=eq.${prevDayRow[1].day}${p}`
      );
      previousCount = prevRows.length;
    }
    const rows = await sbFetch(
      env,
      `/silent?select=query,platform,ai_search_volume&day=eq.${day}${p}&order=ai_search_volume.desc`
    );
    silent = { day, count: rows.length, previous_count: previousCount, rows };
  }

  return {
    property,
    label: cfg.label,
    domain: cfg.domain,
    brands,
    you: cfg.you,
    trend: trendArray,
    latest_day: latestDay,
    by_prompt: byPrompt,
    volumes,
    discovered,
    silent,
  };
}

// --------------------------------------------------------------- /api/freshness
async function handleFreshness(env, url) {
  const property = url.searchParams.get("property");
  const action = url.searchParams.get("action");

  const dayRow = await sbFetch(env, "/freshness_scores?select=day&order=day.desc&limit=1");
  if (!dayRow.length) return { day: null, rows: [] };

  const day = dayRow[0].day;
  let path = `/freshness_scores?select=*&day=eq.${day}`;
  if (property) path += `&property=eq.${encodeURIComponent(property)}`;
  if (action) path += `&action=eq.${encodeURIComponent(action)}`;
  path += "&order=priority_score.desc";

  const rows = await sbFetch(env, path);
  return { day, rows };
}

// ------------------------------------------------------------- /api/competitor
async function handleCompetitor(env, url) {
  const property = url.searchParams.get("property") || "vantagecircle";
  const cfg = PROPERTIES[property] || PROPERTIES.vantagecircle;

  const since = new Date();
  since.setDate(since.getDate() - 90);
  const sinceIso = since.toISOString();

  const [changes, snapshots] = await Promise.all([
    sbFetch(
      env,
      `/competitor_changes?select=*&property=eq.${encodeURIComponent(property)}&timestamp=gte.${encodeURIComponent(sinceIso)}&order=timestamp.desc&limit=2000`
    ),
    sbFetch(
      env,
      `/competitor_snapshots?select=*&property=eq.${encodeURIComponent(property)}&order=day.desc&limit=200`
    ),
  ]);

  const latestSnap = {};
  for (const row of snapshots) {
    if (!latestSnap[row.competitor] || row.day > latestSnap[row.competitor].day) {
      latestSnap[row.competitor] = row;
    }
  }

  const competitors = {};
  for (const row of Object.values(latestSnap)) {
    competitors[row.domain] = {
      name: row.competitor,
      total_urls: row.total_urls || 0,
      last_successful_crawl: row.last_successful_crawl || "",
    };
  }
  for (const c of changes) {
    if (!competitors[c.domain]) {
      competitors[c.domain] = {
        name: c.competitor,
        total_urls: 0,
        last_successful_crawl: "",
      };
    }
  }

  return {
    property,
    label: cfg.label,
    self_domain: cfg.domain,
    changes,
    snapshots: Object.values(latestSnap),
    competitors,
  };
}

// --------------------------------------------------------------- /api/snapshots
async function handleSnapshots(env, url) {
  const bucket = env.R2_SNAPSHOTS;
  if (!bucket) return jsonError("R2 snapshot binding not configured", 503);

  const date = url.searchParams.get("date");
  const table = url.searchParams.get("table");

  if (!table) {
    const obj = await bucket.get("snapshots/latest.json");
    if (!obj) return jsonError("Latest manifest not found", 404);
    return new Response(obj.body, {
      headers: { "Content-Type": "application/json", "X-Cache": "MISS" },
    });
  }

  let key;
  if (date) {
    key = `snapshots/${date}/${table}.json`;
  } else {
    const manifestObj = await bucket.get("snapshots/latest.json");
    if (!manifestObj) return jsonError("Latest manifest not found", 404);
    const manifest = await manifestObj.json();
    key = `snapshots/${manifest.date}/${table}.json`;
  }

  const obj = await bucket.get(key);
  if (!obj) return jsonError(`Snapshot not found: ${key}`, 404);
  return new Response(obj.body, {
    headers: { "Content-Type": "application/json", "X-Cache": "MISS" },
  });
}

// ------------------------------------------------------------------ Upstash cache
const CACHE_TTL = {
  summary: 300,
  rank: 3600,
  backlinks: 3600,
  llm: 3600,
  freshness: 1800,
  competitor: 1800,
  snapshots: 3600,
  actions: 300,
  cannibalization: 1800,
  annotations: 60,
  freshness_queue: 60,
  llm_gaps: 1800,
  llm_prompts: 1800,
  gsc_llm_queries: 1800,
  content_inventory: 1800,
  content_pipeline: 300,
  content_clusters: 1800,
  content_performance: 1800,
  content_decay: 1800,
  content_links: 1800,
  content_authors: 1800,
};

function cacheEnabled(env) {
  return env.UPSTASH_REDIS_REST_URL && env.UPSTASH_REDIS_REST_TOKEN;
}

async function cacheGet(env, key) {
  if (!cacheEnabled(env)) return null;
  const res = await fetch(`${env.UPSTASH_REDIS_REST_URL}/get/${encodeURIComponent(key)}`, {
    headers: { Authorization: `Bearer ${env.UPSTASH_REDIS_REST_TOKEN}` },
  });
  if (!res.ok) return null;
  const data = await res.json();
  if (!data.result) return null;
  try {
    return JSON.parse(data.result);
  } catch (e) {
    return null;
  }
}

async function cacheSet(env, key, value, ttl) {
  if (!cacheEnabled(env)) return;
  // Single SET with EX — no separate EXPIRE round-trip.
  await fetch(`${env.UPSTASH_REDIS_REST_URL}/set/${encodeURIComponent(key)}?EX=${ttl}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.UPSTASH_REDIS_REST_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(value),
  });
}

async function rankDropActions(env) {
  const cutoff = daysAgoISO(14);
  const actions = [];
  for (const prop of Object.keys(PROPERTIES)) {
    const rows = await sbFetchAll(
      env,
      `/rank_snapshots?select=keyword,position,url,day&property=eq.${encodeURIComponent(prop)}&day=gte.${cutoff}&order=day.desc`
    );
    const byDay = {};
    for (const r of rows) {
      byDay[r.day] ||= [];
      byDay[r.day].push(r);
    }
    const days = Object.entries(byDay)
      .map(([day, arr]) => ({ day, count: arr.length }))
      .sort((a, b) => b.day.localeCompare(a.day));
    if (days.length < 2) continue;
    const fullest = Math.max(...days.map((d) => d.count));
    const valid = days.filter((d) => d.count >= fullest / 2).map((d) => d.day);
    const latest = valid[0];
    const previous = valid[1];
    if (!latest || !previous) continue;
    const prev = {};
    for (const r of byDay[previous]) prev[r.keyword] = r.position;
    for (const r of byDay[latest]) {
      const p = prev[r.keyword];
      if (p === undefined) continue;
      const curPos = r.position === null ? NOT_FOUND : r.position;
      const prevPos = p === null ? NOT_FOUND : p;
      const delta = prevPos - curPos; // positive = moved up, negative = dropped
      const fellOutOfTop10 = prevPos <= 10 && curPos > 10;
      const bigDrop = delta <= -10;
      if (fellOutOfTop10 || bigDrop) {
        actions.push({
          type: "rank_drop",
          priority: fellOutOfTop10 ? 100 : 85,
          title: `“${r.keyword}” fell ${Math.abs(delta)} positions`,
          detail: `${PROPERTIES[prop].label}: ${prevPos === NOT_FOUND ? ">100" : prevPos} → ${curPos === NOT_FOUND ? ">100" : curPos}${r.url ? " · " + r.url : ""}`,
          link: `#/rank/${prop}`,
          data: { property: prop, keyword: r.keyword, previous: prevPos, current: curPos, url: r.url },
        });
      }
    }
  }
  return actions;
}

async function freshnessActions(env) {
  const dayRow = await sbFetch(env, "/freshness_scores?select=day&order=day.desc&limit=1");
  if (!dayRow.length) return [];
  const day = dayRow[0].day;
  const rows = await sbFetch(
    env,
    `/freshness_scores?select=url,property,action,reason,decay_risk,priority_score,target_keyword,position,volume,traffic_drop_pct&day=eq.${day}&action=neq.MONITOR&decay_risk=in.(high,medium)&order=priority_score.desc&limit=8`
  );
  return rows.map((r) => ({
    type: "freshness",
    priority: Math.round(r.priority_score || 50),
    title: `${r.action} · ${r.url.replace(/^https?:\/\//, "").replace(/\/$/, "").slice(0, 60)}`,
    detail: `${r.reason}${r.target_keyword ? " · keyword: " + r.target_keyword : ""}${r.traffic_drop_pct ? " · traffic " + Math.round(r.traffic_drop_pct) + "%" : ""}`,
    link: "#/freshness",
    data: r,
  }));
}

async function llmLossActions(env) {
  const actions = [];
  for (const [prop, cfg] of Object.entries(PROPERTIES)) {
    const dayRows = await sbFetch(
      env,
      `/llm_snapshots?select=day&property=eq.${encodeURIComponent(prop)}&order=day.desc&limit=2`
    );
    if (dayRows.length < 2) continue;
    const [latestDay, prevDay] = [dayRows[0].day, dayRows[1].day];
    const [latest, prev] = await Promise.all([
      sbFetch(env, `/llm_snapshots?select=prompt,mentions&day=eq.${latestDay}&property=eq.${encodeURIComponent(prop)}`),
      sbFetch(env, `/llm_snapshots?select=prompt,mentions&day=eq.${prevDay}&property=eq.${encodeURIComponent(prop)}`),
    ]);
    const you = cfg.you;
    const wasMentioned = {};
    for (const r of prev) {
      let m = {};
      try { m = JSON.parse(r.mentions || "{}"); } catch (e) {}
      if (m[you]) wasMentioned[r.prompt] = true;
    }
    const nowMentioned = new Set();
    for (const r of latest) {
      let m = {};
      try { m = JSON.parse(r.mentions || "{}"); } catch (e) {}
      if (m[you]) nowMentioned.add(r.prompt);
    }
    for (const prompt of Object.keys(wasMentioned)) {
      if (!nowMentioned.has(prompt)) {
        actions.push({
          type: "llm_loss",
          priority: 75,
          title: `AI answers stopped mentioning ${cfg.label}`,
          detail: `Prompt: “${prompt}”`,
          link: `#/llm/${prop}`,
          data: { property: prop, prompt },
        });
      }
    }
  }
  return actions;
}

async function backlinkLossActions(env) {
  const rows = await sbFetch(
    env,
    `/refdomain_events?select=day,domain,rank&event=eq.lost&day=gte.${daysAgoISO(14)}&order=rank.desc&limit=10`
  );
  return rows.map((r) => ({
    type: "backlink_lost",
    priority: 60 + (r.rank || 0) / 20,
    title: `Lost referring domain: ${r.domain}`,
    detail: `DR ${r.rank || "—"} · ${r.day}`,
    link: "#/backlinks",
    data: r,
  }));
}

async function competitorChangeActions(env) {
  const rows = await sbFetch(
    env,
    `/competitor_changes?select=timestamp,property,competitor,url,change_type,title&change_type=in.(title_change,h1_change,meta_change)&order=timestamp.desc&limit=5`
  );
  return rows.map((r) => ({
    type: "competitor_change",
    priority: 55,
    title: `${PROPERTIES[r.property]?.label || r.property} competitor changed ${r.change_type.replace("_", " ")}`,
    detail: `${r.competitor} · ${r.title || r.url}`,
    link: `#/competitor/${r.property}`,
    data: r,
  }));
}

async function handleActions(env) {
  const [rankDrops, fresh, llmLoss, lostRefs, compChanges] = await Promise.all([
    rankDropActions(env),
    freshnessActions(env),
    llmLossActions(env),
    backlinkLossActions(env),
    competitorChangeActions(env),
  ]);
  const all = [...rankDrops, ...fresh, ...llmLoss, ...lostRefs, ...compChanges];
  all.sort((a, b) => b.priority - a.priority);
  return { actions: all.slice(0, 20), generated_at: new Date().toISOString() };
}

// ---------------------------------------------------------------- /api/cannibalization
async function handleCannibalization(env, url) {
  const property = url.searchParams.get("property") || "vantagecircle";
  const cutoff = daysAgoISO(14);
  const rows = await sbFetchAll(
    env,
    `/rank_snapshots?select=keyword,position,url,day&property=eq.${encodeURIComponent(property)}&day=gte.${cutoff}&order=day.desc`
  );
  const byDay = {};
  for (const r of rows) {
    byDay[r.day] ||= [];
    byDay[r.day].push(r);
  }
  const days = Object.entries(byDay)
    .map(([day, arr]) => ({ day, count: arr.length }))
    .sort((a, b) => b.day.localeCompare(a.day));
  if (!days.length) return { property, dilution: [], url_flips: [], missing_url: [] };
  const fullest = Math.max(...days.map((d) => d.count));
  const valid = days.filter((d) => d.count >= fullest / 2).map((d) => d.day);
  const latest = valid[0];
  const previous = valid[1];
  const latestRows = byDay[latest] || [];

  // URL dilution: same URL ranking for 5+ keywords
  const byUrl = {};
  for (const r of latestRows) {
    if (!r.url) continue;
    byUrl[r.url] ||= [];
    byUrl[r.url].push(r.keyword);
  }
  const dilution = Object.entries(byUrl)
    .filter(([_, kws]) => kws.length >= 5)
    .map(([u, kws]) => ({ url: u, keyword_count: kws.length, keywords: kws }))
    .sort((a, b) => b.keyword_count - a.keyword_count);

  // Keyword URL flips between latest and previous
  const urlFlips = [];
  const missingUrl = [];
  if (previous) {
    const prevByKw = {};
    for (const r of byDay[previous]) if (r.url) prevByKw[r.keyword] = r.url;
    for (const r of latestRows) {
      const prevUrl = prevByKw[r.keyword];
      if (!prevUrl) continue;
      if (r.url && r.url !== prevUrl) {
        urlFlips.push({ keyword: r.keyword, previous_url: prevUrl, current_url: r.url });
      } else if (!r.url && prevUrl) {
        missingUrl.push({ keyword: r.keyword, previous_url: prevUrl });
      }
    }
  }

  return { property, latest_day: latest, previous_day: previous, dilution, url_flips: urlFlips, missing_url: missingUrl };
}

// ---------------------------------------------------------------- /api/annotations
async function handleAnnotations(env, request) {
  if (request.method === "GET") {
    const url = new URL(request.url);
    const days = parseInt(url.searchParams.get("days") || "90", 10);
    const since = daysAgoISO(days);
    const rows = await sbFetch(env, `/annotations?select=*&day=gte.${since}&order=day.desc`);
    return { annotations: rows };
  }
  if (request.method === "POST") {
    const body = await request.json();
    const row = {
      day: body.day || todayISO(),
      label: body.label || "",
      note: body.note || "",
      created_at: new Date().toISOString(),
    };
    const inserted = await sbPost(env, "annotations", row);
    return { inserted };
  }
  return jsonError("Method not allowed", 405);
}

// ---------------------------------------------------------------- /api/freshness_queue
async function handleFreshnessQueue(env, request, url) {
  if (request.method === "GET") {
    const property = url.searchParams.get("property");
    const dayRow = await sbFetch(env, "/freshness_scores?select=day&order=day.desc&limit=1");
    if (!dayRow.length) return { property, queue: [] };
    const day = dayRow[0].day;
    let path = `/freshness_scores?select=url,property,action,reason,decay_risk,priority_score,target_keyword,position,volume,traffic_drop_pct,title&day=eq.${day}&action=neq.MONITOR`;
    if (property) path += `&property=eq.${encodeURIComponent(property)}`;
    path += "&order=priority_score.desc&limit=100";
    const rows = await sbFetch(env, path);
    const urls = rows.map((r) => r.url).filter(Boolean);
    let statusByUrl = {};
    if (urls.length) {
      const statusPath = `/freshness_status?select=url,status,owner,note,updated_at&url=in.(${urls.map(encodeURIComponent).join(",")})`;
      const statusRows = await sbFetch(env, statusPath);
      for (const s of statusRows) statusByUrl[s.url] = s;
    }
    const queue = rows.map((r) => ({ ...r, status: statusByUrl[r.url] || null }));
    return { property, day, queue };
  }
  if (request.method === "PATCH") {
    const body = await request.json();
    if (!body.url) return jsonError("url required", 400);
    const updates = {};
    if (body.status !== undefined) updates.status = body.status;
    if (body.owner !== undefined) updates.owner = body.owner;
    if (body.note !== undefined) updates.note = body.note;
    updates.updated_at = new Date().toISOString();
    // Upsert via resolution=merge-duplicates on conflict of primary key
    await sbPost(env, "freshness_status", { url: body.url, ...updates }, "resolution=merge-duplicates");
    return { ok: true };
  }
  return jsonError("Method not allowed", 405);
}

// ---------------------------------------------------------------- /api/llm_gaps
async function handleLlmGaps(env, url) {
  const property = url.searchParams.get("property") || "vantagecircle";
  const cfg = PROPERTIES[property] || PROPERTIES.vantagecircle;
  const you = cfg.you;
  const competitorBrands = cfg.brands.filter((b) => b !== you);

  const dayRows = await sbFetch(
    env,
    `/llm_snapshots?select=day&property=eq.${encodeURIComponent(property)}&order=day.desc&limit=1`
  );
  if (!dayRows.length) return { property, gaps: [] };
  const day = dayRows[0].day;
  const rows = await sbFetch(
    env,
    `/llm_snapshots?select=prompt,platform,mentions,answer,cited_mine&day=eq.${day}&property=eq.${encodeURIComponent(property)}`
  );

  // Load discovered volume hints for these prompts
  const prompts = [...new Set(rows.map((r) => r.prompt))];
  const volByQuery = {};
  if (prompts.length) {
    const disc = await sbFetch(
      env,
      `/discovered?select=query,ai_search_volume,volume_delta&property=eq.${encodeURIComponent(property)}&query=in.(${prompts.map(encodeURIComponent).join(",")})`
    );
    for (const d of disc) volByQuery[d.query] = d;
  }

  const byPrompt = {};
  for (const r of rows) {
    byPrompt[r.prompt] ||= [];
    byPrompt[r.prompt].push(r);
  }

  const gaps = [];
  for (const [prompt, entries] of Object.entries(byPrompt)) {
    let youMentioned = false;
    const competitorsMentioned = new Set();
    const platforms = new Set();
    let sampleAnswer = "";
    for (const e of entries) {
      platforms.add(e.platform);
      if (!sampleAnswer && e.answer) sampleAnswer = e.answer.slice(0, 300);
      let m = {};
      try { m = JSON.parse(e.mentions || "{}"); } catch (err) {}
      if (m[you]) youMentioned = true;
      for (const b of competitorBrands) if (m[b]) competitorsMentioned.add(b);
    }
    if (!youMentioned && competitorsMentioned.size) {
      const v = volByQuery[prompt] || {};
      gaps.push({
        prompt,
        platforms: [...platforms],
        competitors_mentioned: [...competitorsMentioned],
        estimated_volume: v.ai_search_volume || null,
        volume_delta: v.volume_delta || null,
        sample_answer: sampleAnswer,
      });
    }
  }
  gaps.sort((a, b) => (b.estimated_volume || 0) - (a.estimated_volume || 0));
  return { property, day, you, gaps: gaps.slice(0, 50) };
}

// ---------------------------------------------------------------- /api/llm_prompts
async function handleLlmPrompts(env, url) {
  const property = url.searchParams.get("property") || "vantagecircle";
  const cfg = PROPERTIES[property] || PROPERTIES.vantagecircle;
  const you = cfg.you;
  const competitorBrands = cfg.brands.filter((b) => b !== you);

  const dayRows = await sbFetch(
    env,
    `/llm_snapshots?select=day&property=eq.${encodeURIComponent(property)}&order=day.desc&limit=1`
  );
  if (!dayRows.length) return { property, day: null, prompts: [] };
  const day = dayRows[0].day;
  const rows = await sbFetch(
    env,
    `/llm_snapshots?select=prompt,platform,mentions,cited_mine&day=eq.${day}&property=eq.${encodeURIComponent(property)}`
  );

  const byPrompt = {};
  for (const r of rows) {
    byPrompt[r.prompt] ||= [];
    byPrompt[r.prompt].push(r);
  }

  const prompts = [];
  for (const [prompt, entries] of Object.entries(byPrompt)) {
    let youMentioned = false;
    const competitorsMentioned = new Set();
    const platforms = [];
    let citedCount = 0;
    for (const e of entries) {
      platforms.push(e.platform);
      if (e.cited_mine) citedCount++;
      let m = {};
      try { m = JSON.parse(e.mentions || "{}"); } catch (err) {}
      if (m[you]) youMentioned = true;
      for (const b of competitorBrands) if (m[b]) competitorsMentioned.add(b);
    }
    prompts.push({
      prompt,
      platforms: [...new Set(platforms)],
      you_mentioned: youMentioned,
      competitors_mentioned: [...competitorsMentioned],
      cited_count: citedCount,
      total_answers: entries.length,
    });
  }
  prompts.sort((a, b) => a.prompt.localeCompare(b.prompt));
  return { property, day, you, prompts };
}

// ---------------------------------------------------------------- /api/gsc_llm_queries
async function handleGscLlmQueries(env, url) {
  const property = url.searchParams.get("property") || "vantagecircle";

  const dayRows = await sbFetch(
    env,
    `/gsc_llm_queries?select=day&property=eq.${encodeURIComponent(property)}&order=day.desc&limit=1`
  );
  if (!dayRows.length) return { property, day: null, queries: [], total_clicks: 0, total_impressions: 0 };
  const day = dayRows[0].day;

  const rows = await sbFetchAll(
    env,
    `/gsc_llm_queries?select=query,page,clicks,impressions,ctr,position,llm_score,llm_signals&day=eq.${day}&property=eq.${encodeURIComponent(property)}&order=llm_score.desc,clicks.desc`
  );

  let totalClicks = 0;
  let totalImpressions = 0;
  for (const r of rows) {
    r.ctr = r.ctr != null ? Math.round(r.ctr * 1000) / 10 : 0;
    r.position = r.position != null ? Math.round(r.position * 10) / 10 : 0;
    let signals = [];
    try { signals = JSON.parse(r.llm_signals || "[]"); } catch (err) {}
    r.signals = signals;
    totalClicks += r.clicks || 0;
    totalImpressions += r.impressions || 0;
  }

  return {
    property,
    day,
    queries: rows,
    total_clicks: totalClicks,
    total_impressions: totalImpressions,
  };
}

// ---------------------------------------------------------------- /api/content_inventory
async function handleContentInventory(env, url) {
  const property = url.searchParams.get("property") || "all";
  const lang = url.searchParams.get("lang") || "all";
  const contentType = url.searchParams.get("type") || "all";
  const status = url.searchParams.get("status") || "all";
  const author = (url.searchParams.get("author") || "").toLowerCase();
  const tag = (url.searchParams.get("tag") || "").toLowerCase();
  const search = (url.searchParams.get("search") || "").toLowerCase();
  const limit = parseInt(url.searchParams.get("limit") || "5000", 10);

  let rows = [];
  try {
    rows = await sbFetchAll(env, `/content_inventory?select=*&order=updated_date.desc&limit=${limit}`);
  } catch (e) {
    const msg = e.message || "";
    if (msg.includes("content_inventory") && (msg.includes("does not exist") || msg.includes("Not found"))) {
      return { rows: [], summary: {} };
    }
    throw e;
  }

  const summary = { total: 0, by_type: {}, by_lang: {}, by_status: {}, by_author: {}, by_tag: {} };

  function safeList(v) {
    try {
      const parsed = JSON.parse(v || "[]");
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      return [];
    }
  }

  try {
    for (const r of rows) {
      summary.total++;
      summary.by_type[r.content_type] = (summary.by_type[r.content_type] || 0) + 1;
      summary.by_lang[r.lang] = (summary.by_lang[r.lang] || 0) + 1;
      summary.by_status[r.status] = (summary.by_status[r.status] || 0) + 1;
      for (const a of safeList(r.authors)) summary.by_author[a] = (summary.by_author[a] || 0) + 1;
      for (const t of safeList(r.tags)) summary.by_tag[t] = (summary.by_tag[t] || 0) + 1;
    }

    const filtered = rows.filter((r) => {
      if (property !== "all" && r.property !== property) return false;
      if (lang !== "all" && r.lang !== lang) return false;
      if (contentType !== "all" && r.content_type !== contentType) return false;
      if (status !== "all" && r.status !== status) return false;
      if (author && !safeList(r.authors).some((a) => a.toLowerCase().includes(author))) return false;
      if (tag && !safeList(r.tags).some((t) => t.toLowerCase().includes(tag))) return false;
      if (search) {
        const hay = `${r.title || ""} ${r.meta_title || ""} ${r.meta_description || ""} ${r.slug || ""} ${r.url || ""} ${r.excerpt || ""}`.toLowerCase();
        if (!hay.includes(search)) return false;
      }
      return true;
    });

    return { rows: filtered, summary };
  } catch (err) {
    return { error: err.message, stack: err.stack };
  }
}

// ---------------------------------------------------------------- /api/content_pipeline
async function handleContentPipeline(env, request, url) {
  if (request.method === "POST") {
    let body;
    try {
      body = await request.json();
    } catch (e) {
      return jsonError("Invalid JSON body", 400);
    }
    const allowed = ["title", "property", "content_type", "stage", "owner", "due_date", "published_date", "target_keyword", "cluster", "notes", "url", "lang", "brief_goal", "brief_outline", "brief_word_count", "brief_keywords", "brief_competitors"];
    const row = {};
    for (const k of allowed) {
      if (body[k] !== undefined) row[k] = body[k];
    }
    if (!row.title || !row.stage) return jsonError("title and stage are required", 400);
    row.updated_at = new Date().toISOString();
    try {
      if (body.id) {
        await sbPatch(env, "content_pipeline", { id: body.id }, row);
        return { ok: true };
      }
      const inserted = await sbPost(env, "content_pipeline", row, "return=representation");
      return { ok: true, row: inserted && inserted[0] ? inserted[0] : inserted };
    } catch (e) {
      return jsonError(e.message);
    }
  }

  // GET
  const property = url.searchParams.get("property") || "all";
  let rows = [];
  try {
    rows = await sbFetchAll(env, "/content_pipeline?select=*&order=due_date.asc.nullslast");
  } catch (e) {
    const msg = e.message || "";
    if (msg.includes("content_pipeline") && (msg.includes("does not exist") || msg.includes("Not found"))) {
      return { rows: [] };
    }
    throw e;
  }
  if (property !== "all") rows = rows.filter((r) => r.property === property);

  const byStage = {};
  const stages = ["idea", "brief", "draft", "review", "scheduled", "published", "refresh", "prune"];
  stages.forEach((s) => (byStage[s] = []));
  rows.forEach((r) => {
    if (!byStage[r.stage]) byStage[r.stage] = [];
    byStage[r.stage].push(r);
  });
  return { rows, by_stage: byStage, stages };
}

// ---------------------------------------------------------------- /api/content_clusters
async function handleContentClusters(env, url) {
  const property = url.searchParams.get("property") || "all";
  let clusters = [];
  let inventory = [];
  try {
    clusters = await sbFetchAll(env, "/content_clusters?select=*&order=cluster.asc");
  } catch (e) {
    const msg = e.message || "";
    if (msg.includes("content_clusters") && (msg.includes("does not exist") || msg.includes("Not found"))) {
      return { clusters: [], inventory: [] };
    }
    throw e;
  }
  try {
    inventory = await sbFetchAll(env, "/content_inventory?select=url,property,content_type,title,tags&limit=5000");
  } catch (e) {
    inventory = [];
  }
  if (property !== "all") {
    clusters = clusters.filter((c) => c.property === property);
    inventory = inventory.filter((r) => r.property === property);
  }

  // tag-based cluster membership (fall back to target_keywords)
  const clusterMap = {};
  clusters.forEach((c) => {
    clusterMap[c.id] = { ...c, items: [], keywords: [] };
    const kw = (c.target_keywords || "").split(",").map((k) => k.trim().toLowerCase()).filter(Boolean);
    clusterMap[c.id].keywords = kw;
  });

  inventory.forEach((item) => {
    const itemTags = [];
    try {
      itemTags.push(...JSON.parse(item.tags || "[]").map((t) => String(t).toLowerCase()));
    } catch (e) {}
    Object.values(clusterMap).forEach((c) => {
      const match = c.keywords.some((k) => itemTags.includes(k) || (item.title || "").toLowerCase().includes(k));
      if (match) c.items.push(item);
    });
  });

  return { clusters: Object.values(clusterMap), inventory };
}

function nearestDay(days, target, maxWindow = 7) {
  const targetTs = new Date(target).getTime();
  let best = null, bestDiff = Infinity;
  for (const d of days) {
    const diff = Math.abs(new Date(d).getTime() - targetTs) / 86400000;
    if (diff < bestDiff && diff <= maxWindow) {
      best = d; bestDiff = diff;
    }
  }
  return best;
}

function trendPct(current, previous) {
  if (!previous || previous === 0) return current > 0 ? 100 : 0;
  return Math.round(((current - previous) / previous) * 1000) / 10;
}

// ---------------------------------------------------------------- /api/content_performance
async function handleContentPerformance(env, url) {
  const property = url.searchParams.get("property") || "all";
  const clusterFilter = url.searchParams.get("cluster") || "";
  const contentType = url.searchParams.get("type") || "all";
  const minClicks = parseInt(url.searchParams.get("min_clicks") || "0", 10);

  // 1. inventory
  let inventory = [];
  try {
    inventory = await sbFetchAll(env, "/content_inventory?select=*&order=updated_date.desc&limit=5000");
  } catch (e) {
    const msg = e.message || "";
    if (msg.includes("content_inventory") && (msg.includes("does not exist") || msg.includes("Not found"))) {
      return { rows: [], summary: {} };
    }
    throw e;
  }

  // 2. GSC page stats (latest + history for trends)
  let gscStats = [];
  try {
    gscStats = await sbFetchAll(env, "/gsc_page_stats?select=*&order=day.desc&limit=10000");
  } catch (e) {
    gscStats = [];
  }
  const gscDays = [...new Set(gscStats.map((r) => r.day))].sort((a, b) => b.localeCompare(a));
  const latestGscDay = gscDays[0] || null;
  const prev7 = latestGscDay ? nearestDay(gscDays, daysAgoISO(7)) : null;
  const prev28 = latestGscDay ? nearestDay(gscDays, daysAgoISO(28)) : null;
  const prev90 = latestGscDay ? nearestDay(gscDays, daysAgoISO(90)) : null;

  const gscByPage = {};
  const gscByPage7 = {};
  const gscByPage28 = {};
  const gscByPage90 = {};
  gscStats.forEach((r) => {
    const base = { clicks: r.clicks || 0, impressions: r.impressions || 0, ctr: r.ctr || 0, position: r.position || 0 };
    if (r.day === latestGscDay) gscByPage[r.page] = base;
    if (r.day === prev7) gscByPage7[r.page] = base;
    if (r.day === prev28) gscByPage28[r.page] = base;
    if (r.day === prev90) gscByPage90[r.page] = base;
  });

  // 3. latest rank snapshots (best position per URL)
  let ranks = [];
  try {
    ranks = await sbFetchAll(env, "/rank_snapshots?select=url,position,keyword,day&order=day.desc&limit=10000");
  } catch (e) {
    ranks = [];
  }
  const latestRankDay = ranks.length ? ranks[0].day : null;
  const rankByUrl = {};
  ranks.forEach((r) => {
    if (r.day !== latestRankDay) return;
    if (!rankByUrl[r.url] || (r.position || 999) < (rankByUrl[r.url].position || 999)) {
      rankByUrl[r.url] = { position: r.position, keyword: r.keyword };
    }
  });

  // 4. clusters
  let clusters = [];
  try {
    clusters = await sbFetchAll(env, "/content_clusters?select=*&order=cluster.asc");
  } catch (e) {
    clusters = [];
  }
  const clusterKeywords = {};
  clusters.forEach((c) => {
    const kws = (c.target_keywords || "").split(",").map((k) => k.trim().toLowerCase()).filter(Boolean);
    clusterKeywords[c.cluster] = { property: c.property, keywords: kws };
  });

  // 5. latest backlink pages
  let backlinkStats = [];
  try {
    backlinkStats = await sbFetchAll(env, "/backlink_pages?select=*&order=day.desc&limit=5000");
  } catch (e) {
    backlinkStats = [];
  }
  const latestBacklinkDay = backlinkStats.length ? backlinkStats[0].day : null;
  const blByUrl = {};
  backlinkStats.forEach((r) => {
    if (r.day !== latestBacklinkDay) return;
    blByUrl[r.url] = {
      backlinks: r.backlinks || 0,
      refdomains: r.refdomains || 0,
      dofollow_backlinks: r.dofollow_backlinks || 0,
      broken_backlinks: r.broken_backlinks || 0,
    };
  });

  function assignCluster(item) {
    const tags = [];
    try {
      tags.push(...JSON.parse(item.tags || "[]").map((t) => String(t).toLowerCase()));
    } catch (e) {}
    const title = (item.title || "").toLowerCase();
    for (const [name, meta] of Object.entries(clusterKeywords)) {
      if (meta.property !== item.property) continue;
      const match = meta.keywords.some((k) => tags.includes(k) || title.includes(k));
      if (match) return name;
    }
    return null;
  }

  const rows = inventory.map((item) => {
    const gsc = gscByPage[item.url] || { clicks: 0, impressions: 0, ctr: 0, position: 0 };
    const gsc7 = gscByPage7[item.url];
    const gsc28 = gscByPage28[item.url];
    const gsc90 = gscByPage90[item.url];
    const rank = rankByUrl[item.url] || { position: null, keyword: null };
    const cluster = assignCluster(item);
    const bl = blByUrl[item.url] || { backlinks: 0, refdomains: 0, dofollow_backlinks: 0, broken_backlinks: 0 };

    const trends = {
      clicks_7d: trendPct(gsc.clicks, gsc7?.clicks),
      clicks_28d: trendPct(gsc.clicks, gsc28?.clicks),
      clicks_90d: trendPct(gsc.clicks, gsc90?.clicks),
      impressions_7d: trendPct(gsc.impressions, gsc7?.impressions),
      impressions_28d: trendPct(gsc.impressions, gsc28?.impressions),
      impressions_90d: trendPct(gsc.impressions, gsc90?.impressions),
    };

    let action = "monitor";
    let reason = "";
    if (gsc.clicks === 0 && gsc.impressions > 100) {
      action = "optimize";
      reason = "impressions but no clicks";
    } else if (rank.position && rank.position > 20 && gsc.clicks > 0) {
      action = "improve";
      reason = "page 3+ with traffic";
    } else if (gsc.clicks > 50 && rank.position && rank.position <= 10) {
      action = "expand";
      reason = "strong performer";
    } else if (gsc.impressions === 0 && !rank.position) {
      action = "audit";
      reason = "no search visibility";
    }

    return {
      ...item,
      cluster,
      clicks: gsc.clicks,
      impressions: gsc.impressions,
      ctr: gsc.ctr,
      gsc_position: gsc.position,
      rank_position: rank.position,
      rank_keyword: rank.keyword,
      backlinks: bl.backlinks,
      refdomains: bl.refdomains,
      dofollow_backlinks: bl.dofollow_backlinks,
      broken_backlinks: bl.broken_backlinks,
      trends,
      action,
      reason,
    };
  });

  const filtered = rows.filter((r) => {
    if (property !== "all" && r.property !== property) return false;
    if (contentType !== "all" && r.content_type !== contentType) return false;
    if (clusterFilter && r.cluster !== clusterFilter) return false;
    if (minClicks && (r.clicks || 0) < minClicks) return false;
    return true;
  });

  const summary = {
    total: filtered.length,
    total_clicks: filtered.reduce((s, r) => s + (r.clicks || 0), 0),
    total_impressions: filtered.reduce((s, r) => s + (r.impressions || 0), 0),
    total_backlinks: filtered.reduce((s, r) => s + (r.backlinks || 0), 0),
    total_refdomains: filtered.reduce((s, r) => s + (r.refdomains || 0), 0),
    avg_position: 0,
    with_traffic: filtered.filter((r) => (r.clicks || 0) > 0).length,
    without_visibility: filtered.filter((r) => (r.impressions || 0) === 0 && !r.rank_position).length,
  };
  const posRows = filtered.filter((r) => r.rank_position);
  summary.avg_position = posRows.length ? Math.round(posRows.reduce((s, r) => s + r.rank_position, 0) / posRows.length * 10) / 10 : 0;

  return {
    rows: filtered,
    summary,
    latest_gsc_day: latestGscDay,
    latest_rank_day: latestRankDay,
    latest_backlink_day: latestBacklinkDay,
    trend_days: { prev7, prev28, prev90 },
  };
}

// ---------------------------------------------------------------- /api/content_decay
async function handleContentDecay(env, url) {
  const property = url.searchParams.get("property") || "all";
  const risk = url.searchParams.get("risk") || "all";
  const limit = parseInt(url.searchParams.get("limit") || "200", 10);

  // Reuse the same join logic as content_performance
  let inventory = [];
  try {
    inventory = await sbFetchAll(env, "/content_inventory?select=*&order=updated_date.desc&limit=5000");
  } catch (e) {
    const msg = e.message || "";
    if (msg.includes("content_inventory") && (msg.includes("does not exist") || msg.includes("Not found"))) {
      return { rows: [], summary: {} };
    }
    throw e;
  }

  let gscStats = [];
  try {
    gscStats = await sbFetchAll(env, "/gsc_page_stats?select=*&order=day.desc&limit=5000");
  } catch (e) {
    gscStats = [];
  }
  const latestGscDay = gscStats.length ? gscStats[0].day : null;
  const gscByPage = {};
  gscStats.forEach((r) => {
    if (r.day !== latestGscDay) return;
    gscByPage[r.page] = { clicks: r.clicks || 0, impressions: r.impressions || 0, ctr: r.ctr || 0, position: r.position || 0 };
  });

  let ranks = [];
  try {
    ranks = await sbFetchAll(env, "/rank_snapshots?select=url,position,keyword,day&order=day.desc&limit=10000");
  } catch (e) {
    ranks = [];
  }
  const latestRankDay = ranks.length ? ranks[0].day : null;
  const rankByUrl = {};
  ranks.forEach((r) => {
    if (r.day !== latestRankDay) return;
    if (!rankByUrl[r.url] || (r.position || 999) < (rankByUrl[r.url].position || 999)) {
      rankByUrl[r.url] = { position: r.position, keyword: r.keyword };
    }
  });

  let clusters = [];
  try {
    clusters = await sbFetchAll(env, "/content_clusters?select=*&order=cluster.asc");
  } catch (e) {
    clusters = [];
  }
  const clusterKeywords = {};
  clusters.forEach((c) => {
    const kws = (c.target_keywords || "").split(",").map((k) => k.trim().toLowerCase()).filter(Boolean);
    clusterKeywords[c.cluster] = { property: c.property, keywords: kws };
  });

  function assignCluster(item) {
    const tags = [];
    try {
      tags.push(...JSON.parse(item.tags || "[]").map((t) => String(t).toLowerCase()));
    } catch (e) {}
    const title = (item.title || "").toLowerCase();
    for (const [name, meta] of Object.entries(clusterKeywords)) {
      if (meta.property !== item.property) continue;
      const match = meta.keywords.some((k) => tags.includes(k) || title.includes(k));
      if (match) return name;
    }
    return null;
  }

  const today = new Date();
  const oneYearAgo = new Date(today.getTime() - 365 * 86400000);
  const twoYearsAgo = new Date(today.getTime() - 730 * 86400000);

  const rows = inventory.map((item) => {
    const gsc = gscByPage[item.url] || { clicks: 0, impressions: 0, ctr: 0, position: 0 };
    const rank = rankByUrl[item.url] || { position: null, keyword: null };
    const cluster = assignCluster(item);
    const updated = item.updated_date ? new Date(item.updated_date) : null;
    const published = item.published_date ? new Date(item.published_date) : null;

    const isStale = updated ? updated < oneYearAgo : (published ? published < oneYearAgo : false);
    const isVeryStale = updated ? updated < twoYearsAgo : (published ? published < twoYearsAgo : false);
    const noVisibility = gsc.impressions === 0 && !rank.position;
    const pageThreePlus = rank.position && rank.position > 20 && gsc.clicks > 0;
    const highImpressionsNoClicks = gsc.impressions > 200 && gsc.clicks === 0;

    let riskLevel = "healthy";
    let action = "monitor";
    let reason = "";
    let score = 0;

    if (isVeryStale && (noVisibility || (rank.position && rank.position > 30))) {
      riskLevel = "critical";
      action = "refresh";
      reason = "very stale + no visibility";
      score = 100;
    } else if (isStale && (noVisibility || pageThreePlus)) {
      riskLevel = "high";
      action = isStale ? "refresh" : "improve";
      reason = isStale ? "stale + underperforming" : "underperforming";
      score = 75;
    } else if (isStale || highImpressionsNoClicks) {
      riskLevel = "medium";
      action = isStale ? "update" : "optimize";
      reason = isStale ? "content is stale" : "impressions but no clicks";
      score = 50;
    } else if (!cluster) {
      riskLevel = "low";
      action = "cluster";
      reason = "orphan page, assign cluster";
      score = 25;
    }

    return {
      ...item,
      cluster,
      clicks: gsc.clicks,
      impressions: gsc.impressions,
      ctr: gsc.ctr,
      gsc_position: gsc.position,
      rank_position: rank.position,
      rank_keyword: rank.keyword,
      risk: riskLevel,
      action,
      reason,
      score,
      days_since_updated: updated ? Math.floor((today - updated) / 86400000) : null,
    };
  });

  let filtered = rows;
  if (property !== "all") filtered = filtered.filter((r) => r.property === property);
  if (risk !== "all") filtered = filtered.filter((r) => r.risk === risk);
  filtered = filtered.filter((r) => r.score > 0);
  filtered.sort((a, b) => b.score - a.score);
  filtered = filtered.slice(0, limit);

  const summary = {
    total: filtered.length,
    critical: filtered.filter((r) => r.risk === "critical").length,
    high: filtered.filter((r) => r.risk === "high").length,
    medium: filtered.filter((r) => r.risk === "medium").length,
    low: filtered.filter((r) => r.risk === "low").length,
  };

  return { rows: filtered, summary };
}

// ---------------------------------------------------------------- /api/content_links
async function handleContentLinks(env, url) {
  const property = url.searchParams.get("property") || "all";
  const clusterFilter = url.searchParams.get("cluster") || "";
  const limit = parseInt(url.searchParams.get("limit") || "150", 10);

  let inventory = [];
  try {
    inventory = await sbFetchAll(env, "/content_inventory?select=url,property,content_type,title,tags,internal_links&limit=2000");
  } catch (e) {
    const msg = e.message || "";
    if (msg.includes("content_inventory") && (msg.includes("does not exist") || msg.includes("Not found"))) {
      return { suggestions: [] };
    }
    throw e;
  }
  if (property !== "all") inventory = inventory.filter((r) => r.property === property);

  let clusters = [];
  try {
    clusters = await sbFetchAll(env, "/content_clusters?select=*&order=cluster.asc");
  } catch (e) {
    clusters = [];
  }
  const clusterKeywords = {};
  clusters.forEach((c) => {
    const kws = (c.target_keywords || "").split(",").map((k) => k.trim().toLowerCase()).filter(Boolean);
    clusterKeywords[c.cluster] = { property: c.property, keywords: kws };
  });

  function assignCluster(item) {
    const tags = [];
    try {
      const parsed = JSON.parse(item.tags || "[]");
      if (Array.isArray(parsed)) tags.push(...parsed.map((t) => String(t).toLowerCase()));
    } catch (e) {}
    const title = (item.title || "").toLowerCase();
    for (const [name, meta] of Object.entries(clusterKeywords)) {
      if (meta.property !== item.property) continue;
      const match = meta.keywords.some((k) => tags.includes(k) || title.includes(k));
      if (match) return name;
    }
    return null;
  }

  const items = inventory.map((item) => ({ ...item, cluster: clusterFilter || assignCluster(item) }));

  const byCluster = {};
  items.forEach((item) => {
    const c = item.cluster || "(none)";
    if (!byCluster[c]) byCluster[c] = [];
    byCluster[c].push(item);
  });

  const suggestions = [];
  Object.entries(byCluster).forEach(([cluster, clusterItems]) => {
    if (clusterItems.length < 2 || clusterItems.length > 80) return;
    clusterItems.forEach((source) => {
      if ((source.internal_links || 0) >= 10) return;
      const sourceTitle = (source.title || "").toLowerCase();
      const candidates = [];
      for (const target of clusterItems) {
        if (target.url === source.url) continue;
        let score = 0;
        const targetTitle = (target.title || "").toLowerCase();
        try {
          const parsed = JSON.parse(target.tags || "[]");
          if (Array.isArray(parsed) && sourceTitle) {
            if (parsed.some((t) => sourceTitle.includes(String(t).toLowerCase()))) score += 3;
          }
        } catch (e) {}
        if (sourceTitle && targetTitle.includes(sourceTitle.split(" ")[0])) score += 1;
        if ((target.internal_links || 0) < 3) score += 1;
        if (score > 0) candidates.push({ target, score });
      }
      candidates.sort((a, b) => b.score - a.score);
      const top = candidates.slice(0, 2);

      if (top.length) {
        suggestions.push({
          source_url: source.url,
          source_title: source.title,
          source_property: source.property,
          cluster,
          internal_links: source.internal_links || 0,
          targets: top.map((c) => ({
            url: c.target.url,
            title: c.target.title,
            score: c.score,
          })),
        });
      }
    });
  });

  const flat = suggestions
    .sort((a, b) => a.internal_links - b.internal_links || b.targets[0].score - a.targets[0].score)
    .slice(0, limit);
  return { suggestions: flat, clusters: Object.keys(byCluster) };
}

// ---------------------------------------------------------------- /api/content_authors
async function handleContentAuthors(env, url) {
  const property = url.searchParams.get("property") || "all";

  let inventory = [];
  try {
    inventory = await sbFetchAll(env, "/content_inventory?select=*&order=updated_date.desc&limit=5000");
  } catch (e) {
    const msg = e.message || "";
    if (msg.includes("content_inventory") && (msg.includes("does not exist") || msg.includes("Not found"))) {
      return { authors: [] };
    }
    throw e;
  }

  let gscStats = [];
  try {
    gscStats = await sbFetchAll(env, "/gsc_page_stats?select=*&order=day.desc&limit=5000");
  } catch (e) {
    gscStats = [];
  }
  const latestGscDay = gscStats.length ? gscStats[0].day : null;
  const gscByPage = {};
  gscStats.forEach((r) => {
    if (r.day !== latestGscDay) return;
    gscByPage[r.page] = { clicks: r.clicks || 0, impressions: r.impressions || 0 };
  });

  let ranks = [];
  try {
    ranks = await sbFetchAll(env, "/rank_snapshots?select=url,position,day&order=day.desc&limit=10000");
  } catch (e) {
    ranks = [];
  }
  const latestRankDay = ranks.length ? ranks[0].day : null;
  const rankByUrl = {};
  ranks.forEach((r) => {
    if (r.day !== latestRankDay) return;
    if (!rankByUrl[r.url] || (r.position || 999) < (rankByUrl[r.url].position || 999)) {
      rankByUrl[r.url] = { position: r.position };
    }
  });

  let backlinkStats = [];
  try {
    backlinkStats = await sbFetchAll(env, "/backlink_pages?select=*&order=day.desc&limit=5000");
  } catch (e) {
    backlinkStats = [];
  }
  const latestBacklinkDay = backlinkStats.length ? backlinkStats[0].day : null;
  const blByUrl = {};
  backlinkStats.forEach((r) => {
    if (r.day !== latestBacklinkDay) return;
    blByUrl[r.url] = { backlinks: r.backlinks || 0, refdomains: r.refdomains || 0 };
  });

  const byAuthor = {};
  inventory.forEach((item) => {
    if (property !== "all" && item.property !== property) return;
    let authors = [];
    try {
      const parsed = JSON.parse(item.authors || "[]");
      authors = Array.isArray(parsed) ? parsed : [item.authors];
    } catch (e) {
      authors = item.authors ? [item.authors] : [];
    }
    if (!authors.length) authors = ["(no author)"];
    authors.forEach((name) => {
      const key = String(name).trim();
      if (!key) return;
      if (!byAuthor[key]) {
        byAuthor[key] = { name: key, pages: 0, clicks: 0, impressions: 0, backlinks: 0, refdomains: 0, top10: 0, avg_position: 0, positions: [] };
      }
      const gsc = gscByPage[item.url] || {};
      const rank = rankByUrl[item.url] || {};
      const bl = blByUrl[item.url] || {};
      byAuthor[key].pages += 1;
      byAuthor[key].clicks += gsc.clicks || 0;
      byAuthor[key].impressions += gsc.impressions || 0;
      byAuthor[key].backlinks += bl.backlinks || 0;
      byAuthor[key].refdomains += bl.refdomains || 0;
      if (rank.position && rank.position <= 10) byAuthor[key].top10 += 1;
      if (rank.position) byAuthor[key].positions.push(rank.position);
    });
  });

  const authors = Object.values(byAuthor).map((a) => {
    a.avg_position = a.positions.length ? Math.round(a.positions.reduce((s, p) => s + p, 0) / a.positions.length * 10) / 10 : 0;
    delete a.positions;
    return a;
  }).sort((a, b) => b.clicks - a.clicks);

  return { authors, latest_gsc_day: latestGscDay, latest_rank_day: latestRankDay, latest_backlink_day: latestBacklinkDay };
}

function cacheKey(request, route) {
  const url = new URL(request.url);
  const qs = url.searchParams.toString();
  return `v15:seo-suite:${route}${qs ? ":" + qs : ""}`;
}

// ---------------------------------------------------------------------- router
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/api/")) {
      try {
        const route = url.pathname.slice(5).replace(/\/$/, "") || "summary";
        if (!CACHE_TTL[route]) return jsonError("Not found", 404);

        // X-Cache-Enabled makes it possible to tell from curl whether the
        // Upstash env vars are configured at all (vs. silently uncached).
        const cacheHeaders = {
          "X-Cache-Enabled": cacheEnabled(env) ? "true" : "false",
        };

        const key = cacheKey(request, route);
        const cached = await cacheGet(env, key);
        if (cached) {
          return Response.json(cached, { headers: { ...cacheHeaders, "X-Cache": "HIT" } });
        }

        let result;
        if (route === "summary") result = await handleSummary(env);
        else if (route === "rank") result = await handleRank(env, url);
        else if (route === "backlinks") result = await handleBacklinks(env);
        else if (route === "llm") result = await handleLlm(env, url);
        else if (route === "freshness") result = await handleFreshness(env, url);
        else if (route === "competitor") result = await handleCompetitor(env, url);
        else if (route === "snapshots") return await handleSnapshots(env, url);
        else if (route === "actions") result = await handleActions(env);
        else if (route === "cannibalization") result = await handleCannibalization(env, url);
        else if (route === "annotations") result = await handleAnnotations(env, request);
        else if (route === "freshness_queue") result = await handleFreshnessQueue(env, request, url);
        else if (route === "llm_gaps") result = await handleLlmGaps(env, url);
        else if (route === "llm_prompts") result = await handleLlmPrompts(env, url);
        else if (route === "gsc_llm_queries") result = await handleGscLlmQueries(env, url);
        else if (route === "content_inventory") result = await handleContentInventory(env, url);
        else if (route === "content_pipeline") result = await handleContentPipeline(env, request, url);
        else if (route === "content_clusters") result = await handleContentClusters(env, url);
        else if (route === "content_performance") result = await handleContentPerformance(env, url);
        else if (route === "content_decay") result = await handleContentDecay(env, url);
        else if (route === "content_links") result = await handleContentLinks(env, url);
        else if (route === "content_authors") result = await handleContentAuthors(env, url);
        else return jsonError("Not found", 404);

        ctx.waitUntil(cacheSet(env, key, result, CACHE_TTL[route]));
        return Response.json(result, { headers: { ...cacheHeaders, "X-Cache": "MISS" } });
      } catch (e) {
        return jsonError(e.message);
      }
    }

    return env.ASSETS.fetch(request);
  },
};
