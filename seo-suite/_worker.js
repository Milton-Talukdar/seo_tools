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

async function sbFetch(env, path) {
  const url = `${env.SUPABASE_URL}/rest/v1${path}`;
  const res = await fetch(url, { headers: sbHeaders(env) });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Supabase ${res.status}: ${text}`);
  }
  return res.json();
}

function jsonError(message, status = 500) {
  return Response.json({ error: message }, { status, headers: { "Content-Type": "application/json" } });
}

const YOU = "vantage circle";
const NOT_FOUND = 101;
const BRANDS = [
  "vantage circle",
  "bonusly",
  "kudos",
  "achievers",
  "awardco",
  "nectar",
  "motivosity",
  "o.c. tanner",
  "workhuman",
];
const PROPERTIES = {
  vantagecircle: { label: "Vantage Circle", domain: "vantagecircle.com" },
  vantagefit: { label: "Vantage Fit", domain: "vantagefit.io" },
};

// ---------------------------------------------------------------- /api/summary
async function latestRankByProperty(env) {
  const rows = await sbFetch(
    env,
    "/rank_snapshots?select=property,day&order=day.desc,property&limit=1000"
  );
  const latest = {};
  for (const r of rows) {
    if (!latest[r.property]) latest[r.property] = r.day;
  }
  const result = {};
  for (const [prop, day] of Object.entries(latest)) {
    const snaps = await sbFetch(
      env,
      `/rank_snapshots?select=keyword,position&property=eq.${encodeURIComponent(prop)}&day=eq.${day}`
    );
    const ranked = snaps.filter((s) => s.position !== null && s.position !== undefined);
    result[prop] = {
      latest_day: day,
      count: snaps.length,
      ranked: ranked.length,
      top3: ranked.filter((s) => s.position <= 3).length,
      top10: ranked.filter((s) => s.position <= 10).length,
      top50: ranked.filter((s) => s.position <= 50).length,
    };
  }
  return result;
}

async function previousRankDays(env, rankSummary) {
  for (const prop of Object.keys(rankSummary)) {
    const rows = await sbFetch(
      env,
      `/rank_snapshots?select=day&property=eq.${encodeURIComponent(prop)}&order=day.desc&limit=1000`
    );
    const counts = {};
    for (const r of rows) counts[r.day] = (counts[r.day] || 0) + 1;
    const days = Object.entries(counts)
      .map(([day, count]) => ({ day, count }))
      .sort((a, b) => b.day.localeCompare(a.day));
    if (days.length > 1) {
      const fullest = Math.max(...days.map((d) => d.count));
      const valid = days.filter((d) => d.count >= fullest / 2);
      rankSummary[prop].previous_day = valid.length > 1 ? valid[1].day : null;
    } else {
      rankSummary[prop].previous_day = null;
    }
  }
}

async function biggestMover(env, rankSummary) {
  let best = null;
  for (const [prop, info] of Object.entries(rankSummary)) {
    if (!info.previous_day) continue;
    const prevRows = await sbFetch(
      env,
      `/rank_snapshots?select=keyword,position&property=eq.${encodeURIComponent(prop)}&day=eq.${info.previous_day}`
    );
    const prev = {};
    for (const r of prevRows) prev[r.keyword] = r.position;
    const curRows = await sbFetch(
      env,
      `/rank_snapshots?select=keyword,position&property=eq.${encodeURIComponent(prop)}&day=eq.${info.latest_day}`
    );
    for (const r of curRows) {
      const p = prev[r.keyword];
      if (p === undefined) continue;
      const prevVal = p === null ? NOT_FOUND : p;
      const curVal = r.position === null ? NOT_FOUND : r.position;
      const delta = prevVal - curVal;
      if (!best || delta > best.delta) {
        best = { keyword: r.keyword, property: prop, delta, previous: p, current: r.position };
      }
    }
  }
  return best;
}

async function handleSummary(env) {
  const rank = await latestRankByProperty(env);
  await previousRankDays(env, rank);

  const backlinkRows = await sbFetch(env, "/backlink_snapshots?select=*&order=day.desc&limit=2");

  const llmDayRow = await sbFetch(env, "/llm_snapshots?select=day&order=day.desc&limit=1");
  let llm = { day: null, count: 0, sov: 0 };
  if (llmDayRow.length) {
    const day = llmDayRow[0].day;
    const answers = await sbFetch(env, `/llm_snapshots?select=mentions&day=eq.${day}`);
    let you = 0;
    for (const a of answers) {
      const m = JSON.parse(a.mentions || "{}");
      if (m[YOU]) you++;
    }
    llm = { day, count: answers.length, sov: answers.length ? Math.round((you / answers.length) * 100) : 0 };
  }

  const freshDayRow = await sbFetch(env, "/freshness_scores?select=day&order=day.desc&limit=1");
  let freshness = { day: null, total: 0, counts: {} };
  if (freshDayRow.length) {
    const day = freshDayRow[0].day;
    const rows = await sbFetch(env, `/freshness_scores?select=action&day=eq.${day}`);
    const counts = {};
    for (const r of rows) counts[r.action] = (counts[r.action] || 0) + 1;
    freshness = { day, total: rows.length, counts };
  }

  const compSnaps = await sbFetch(
    env,
    "/competitor_snapshots?select=property,competitor,total_urls&order=day.desc&limit=200"
  );
  const competitors = {};
  for (const row of compSnaps) {
    const c = (competitors[row.property] ||= { competitors: [], total_urls: 0 });
    if (!c.competitors.includes(row.competitor)) {
      c.competitors.push(row.competitor);
      c.total_urls += row.total_urls || 0;
    }
  }

  const mover = await biggestMover(env, rank);

  return {
    rank,
    backlinks: { latest: backlinkRows[0] || null, previous: backlinkRows[1] || null },
    llm,
    freshness,
    competitors,
    biggest_mover: mover,
  };
}

// ------------------------------------------------------------------ /api/rank
async function propDays(env, property) {
  const rows = await sbFetch(
    env,
    `/rank_snapshots?select=day&property=eq.${encodeURIComponent(property)}&order=day.desc&limit=1000`
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

  const [rankRows, prevRows, metaRows] = await Promise.all([
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
  ]);

  const meta = {};
  for (const r of metaRows) meta[r.keyword] = r;
  const prev = {};
  for (const r of prevRows) prev[r.keyword] = r.position;

  const keywords = rankRows.map((r) => {
    const m = meta[r.keyword] || {};
    return {
      keyword: r.keyword,
      position: r.position,
      previous_position: prev[r.keyword] !== undefined ? prev[r.keyword] : null,
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
  return { snapshots, events };
}

// ------------------------------------------------------------------- /api/llm
async function handleLlm(env) {
  const allRows = await sbFetch(
    env,
    "/llm_snapshots?select=day,platform,prompt,mentions,cited_mine,answer&order=day.desc"
  );

  const trend = {};
  for (const r of allRows) {
    const day = r.day;
    trend[day] ||= { day, total: 0 };
    for (const b of BRANDS) {
      trend[day][b] ||= 0;
    }
    const m = JSON.parse(r.mentions || "{}");
    trend[day].total += 1;
    for (const b of BRANDS) {
      if (m[b]) trend[day][b] += 1;
    }
  }
  const trendArray = Object.values(trend).sort((a, b) => b.day.localeCompare(a.day));

  const dayRows = await sbFetch(env, "/llm_snapshots?select=day&order=day.desc&limit=1");
  let latest = [];
  let latestDay = null;
  if (dayRows.length) {
    latestDay = dayRows[0].day;
    latest = await sbFetch(
      env,
      `/llm_snapshots?select=day,platform,prompt,mentions,cited_mine,answer&day=eq.${latestDay}&order=prompt,platform`
    );
  }

  const byPrompt = {};
  for (const r of latest) {
    byPrompt[r.prompt] ||= [];
    byPrompt[r.prompt].push(r);
  }

  const volDayRow = await sbFetch(env, "/volumes?select=day&order=day.desc&limit=1");
  let volumes = [];
  if (volDayRow.length) {
    volumes = await sbFetch(
      env,
      `/volumes?select=keyword,ai_search_volume,trend_json&day=eq.${volDayRow[0].day}&order=ai_search_volume.desc&limit=200`
    );
  }

  const discovered = await sbFetch(
    env,
    "/discovered?select=query,platform,ai_search_volume,seed&order=ai_search_volume.desc&limit=40"
  );

  const silentDayRow = await sbFetch(env, "/silent?select=day&order=day.desc&limit=1");
  let silent = { day: null, count: 0, previous_count: 0, rows: [] };
  if (silentDayRow.length) {
    const day = silentDayRow[0].day;
    const prevDayRow = await sbFetch(env, `/silent?select=day&order=day.desc&limit=2`);
    let previousCount = 0;
    if (prevDayRow.length > 1 && prevDayRow[1].day !== day) {
      const prevRows = await sbFetch(env, `/silent?select=query&day=eq.${prevDayRow[1].day}`);
      previousCount = prevRows.length;
    }
    const rows = await sbFetch(
      env,
      `/silent?select=query,platform,ai_search_volume&day=eq.${day}&order=ai_search_volume.desc`
    );
    silent = { day, count: rows.length, previous_count: previousCount, rows };
  }

  return {
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
  debug: 60,
};

async function handleDebug(env) {
  const summary = await handleSummary(env);
  return {
    ok: true,
    ts: new Date().toISOString(),
    summaryType: typeof summary,
    summaryKeys: summary ? Object.keys(summary) : null,
    summaryIsString: typeof summary === "string",
    firstChars: typeof summary === "string" ? summary.slice(0, 50) : null,
  };
}

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
  const headers = { Authorization: `Bearer ${env.UPSTASH_REDIS_REST_TOKEN}` };
  const serialized = JSON.stringify(value);
  await fetch(`${env.UPSTASH_REDIS_REST_URL}/set/${encodeURIComponent(key)}`, {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify(serialized),
  });
  await fetch(`${env.UPSTASH_REDIS_REST_URL}/expire/${encodeURIComponent(key)}/${ttl}`, {
    headers,
  });
}

function cacheKey(request, route) {
  const url = new URL(request.url);
  const qs = url.searchParams.toString();
  return `v3:seo-suite:${route}${qs ? ":" + qs : ""}`;
}

// ---------------------------------------------------------------------- router
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/api/")) {
      try {
        const route = url.pathname.slice(5).replace(/\/$/, "") || "summary";
        if (!CACHE_TTL[route]) return jsonError("Not found", 404);

        const key = cacheKey(request, route);
        const cached = await cacheGet(env, key);
        if (cached) {
          return Response.json(cached, { headers: { "X-Cache": "HIT" } });
        }

        let result;
        if (route === "summary") result = await handleSummary(env);
        else if (route === "rank") result = await handleRank(env, url);
        else if (route === "backlinks") result = await handleBacklinks(env);
        else if (route === "llm") result = await handleLlm(env);
        else if (route === "freshness") result = await handleFreshness(env, url);
        else if (route === "competitor") result = await handleCompetitor(env, url);
        else if (route === "snapshots") return await handleSnapshots(env, url);
        else if (route === "debug") result = await handleDebug(env);
        else return jsonError("Not found", 404);

        ctx.waitUntil(cacheSet(env, key, result, CACHE_TTL[route]));
        return Response.json(result, { headers: { "X-Cache": "MISS" } });
      } catch (e) {
        return jsonError(e.message);
      }
    }

    return env.ASSETS.fetch(request);
  },
};
