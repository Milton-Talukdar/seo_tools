/**
 * GET /api/rank?property=vantagecircle
 * Latest and previous rank snapshots joined with keyword_meta.
 */
import { sbFetch, jsonError } from "./_supabase.js";

async function propDays(env, property) {
  const rows = await sbFetch(
    env,
    `/rank_snapshots?select=day,count(*)&property=eq.${encodeURIComponent(property)}&group=day&order=day.desc&limit=10`
  );
  if (!rows.length) return [];
  const counts = rows.map((r) => r.count);
  const fullest = Math.max(...counts);
  return rows.filter((r) => r.count >= fullest / 2).map((r) => r.day);
}

export async function onRequestGet(context) {
  try {
    const { searchParams } = new URL(context.request.url);
    const property = searchParams.get("property") || "vantagecircle";
    const days = await propDays(context.env, property);
    if (!days.length) return Response.json({ property, keywords: [], latest_day: null, previous_day: null });

    const latestDay = days[0];
    const previousDay = days.length > 1 ? days[1] : null;

    const [rankRows, prevRows, metaRows] = await Promise.all([
      sbFetch(
        context.env,
        `/rank_snapshots?select=keyword,position,url,serp_features&property=eq.${encodeURIComponent(property)}&day=eq.${latestDay}`
      ),
      previousDay
        ? sbFetch(
            context.env,
            `/rank_snapshots?select=keyword,position&property=eq.${encodeURIComponent(property)}&day=eq.${previousDay}`
          )
        : Promise.resolve([]),
      sbFetch(
        context.env,
        `/keyword_meta?select=*&property=eq.${encodeURIComponent(property)}`
      ),
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

    // Default sort: ranking first, then position asc, then keyword
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

    return Response.json({
      property,
      keywords,
      latest_day: latestDay,
      previous_day: previousDay,
      meta: {
        total: keywords.length,
        tags: [...new Set(keywords.map((k) => k.tag).filter(Boolean))].sort(),
      },
    });
  } catch (e) {
    return jsonError(e.message);
  }
}
