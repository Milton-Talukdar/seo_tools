/**
 * GET /api/summary
 * Latest rank days per property, backlink snapshot, LLM day, freshness counts,
 * competitor counts, and the biggest recent rank mover.
 */
import { sbFetch, jsonError } from "./_supabase.js";

const YOU = "vantage circle";
const NOT_FOUND = 101;

async function latestRankByProperty(env) {
  // Latest day with count per property
  const rows = await sbFetch(
    env,
    "/rank_snapshots?select=property,day,count(*)&group=property,day&order=day.desc,property&limit=40"
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
      const delta = prevVal - curVal; // positive = improved
      if (!best || delta > best.delta) {
        best = { keyword: r.keyword, property: prop, delta, previous: p, current: r.position };
      }
    }
  }
  return best;
}

async function previousRankDays(env, rankSummary) {
  for (const prop of Object.keys(rankSummary)) {
    const rows = await sbFetch(
      env,
      `/rank_snapshots?select=day,count(*)&property=eq.${encodeURIComponent(prop)}&group=day&order=day.desc&limit=10`
    );
    if (rows.length > 1) {
      const counts = rows.map((r) => r.count);
      const fullest = Math.max(...counts);
      const valid = rows.filter((r) => r.count >= fullest / 2);
      rankSummary[prop].previous_day = valid.length > 1 ? valid[1].day : null;
    } else {
      rankSummary[prop].previous_day = null;
    }
  }
}

export async function onRequestGet(context) {
  try {
    const rank = await latestRankByProperty(context.env);
    await previousRankDays(context.env, rank);

    const backlinkRows = await sbFetch(
      context.env,
      "/backlink_snapshots?select=*&order=day.desc&limit=2"
    );

    const llmDayRow = await sbFetch(
      context.env,
      "/llm_snapshots?select=day&order=day.desc&limit=1"
    );
    let llm = { day: null, count: 0, sov: 0 };
    if (llmDayRow.length) {
      const day = llmDayRow[0].day;
      const answers = await sbFetch(context.env, `/llm_snapshots?select=mentions&day=eq.${day}`);
      let you = 0;
      for (const a of answers) {
        const m = JSON.parse(a.mentions || "{}");
        if (m[YOU]) you++;
      }
      llm = { day, count: answers.length, sov: answers.length ? Math.round((you / answers.length) * 100) : 0 };
    }

    const freshDayRow = await sbFetch(
      context.env,
      "/freshness_scores?select=day&order=day.desc&limit=1"
    );
    let freshness = { day: null, total: 0, counts: {} };
    if (freshDayRow.length) {
      const day = freshDayRow[0].day;
      const rows = await sbFetch(context.env, `/freshness_scores?select=action&day=eq.${day}`);
      const counts = {};
      for (const r of rows) counts[r.action] = (counts[r.action] || 0) + 1;
      freshness = { day, total: rows.length, counts };
    }

    const compSnaps = await sbFetch(
      context.env,
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

    const mover = await biggestMover(context.env, rank);

    return Response.json({
      rank,
      backlinks: {
        latest: backlinkRows[0] || null,
        previous: backlinkRows[1] || null,
      },
      llm,
      freshness,
      competitors,
      biggest_mover: mover,
    });
  } catch (e) {
    return jsonError(e.message);
  }
}
