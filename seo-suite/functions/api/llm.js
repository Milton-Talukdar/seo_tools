/**
 * GET /api/llm
 * LLM share-of-voice trend, latest run grouped by prompt/platform,
 * AI search volumes, discovered prompts, and silent citations.
 */
import { sbFetch, jsonError } from "./_supabase.js";

const YOU = "vantage circle";
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

export async function onRequestGet(context) {
  try {
    // Historical trend: all snapshots (weekly runs are small)
    const allRows = await sbFetch(
      context.env,
      "/llm_snapshots?select=day,platform,prompt,mentions,cited_mine,answer&order=day.desc"
    );

    // Aggregate SOV by day
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

    // Latest day snapshots
    const dayRows = await sbFetch(
      context.env,
      "/llm_snapshots?select=day&order=day.desc&limit=1"
    );
    let latest = [];
    let latestDay = null;
    if (dayRows.length) {
      latestDay = dayRows[0].day;
      latest = await sbFetch(
        context.env,
        `/llm_snapshots?select=day,platform,prompt,mentions,cited_mine,answer&day=eq.${latestDay}&order=prompt,platform`
      );
    }

    // Group latest by prompt
    const byPrompt = {};
    for (const r of latest) {
      byPrompt[r.prompt] ||= [];
      byPrompt[r.prompt].push(r);
    }

    // Latest volumes
    const volDayRow = await sbFetch(
      context.env,
      "/volumes?select=day&order=day.desc&limit=1"
    );
    let volumes = [];
    if (volDayRow.length) {
      volumes = await sbFetch(
        context.env,
        `/volumes?select=keyword,ai_search_volume,trend_json&day=eq.${volDayRow[0].day}&order=ai_search_volume.desc&limit=200`
      );
    }

    // Discovered prompts
    const discovered = await sbFetch(
      context.env,
      "/discovered?select=query,platform,ai_search_volume,seed&order=ai_search_volume.desc&limit=40"
    );

    // Silent citations: latest day
    const silentDayRow = await sbFetch(
      context.env,
      "/silent?select=day&order=day.desc&limit=1"
    );
    let silent = { day: null, count: 0, previous_count: 0, rows: [] };
    if (silentDayRow.length) {
      const day = silentDayRow[0].day;
      const prevDayRow = await sbFetch(
        context.env,
        `/silent?select=day&order=day.desc&limit=2`
      );
      let previousCount = 0;
      if (prevDayRow.length > 1 && prevDayRow[1].day !== day) {
        const prevRows = await sbFetch(
          context.env,
          `/silent?select=count(*)&day=eq.${prevDayRow[1].day}`
        );
        previousCount = prevRows[0]?.count || 0;
      }
      const rows = await sbFetch(
        context.env,
        `/silent?select=query,platform,ai_search_volume&day=eq.${day}&order=ai_search_volume.desc`
      );
      silent = { day, count: rows.length, previous_count: previousCount, rows };
    }

    return Response.json({
      trend: trendArray,
      latest_day: latestDay,
      by_prompt: byPrompt,
      volumes,
      discovered,
      silent,
    });
  } catch (e) {
    return jsonError(e.message);
  }
}
