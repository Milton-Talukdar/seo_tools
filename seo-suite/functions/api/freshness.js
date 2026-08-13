/**
 * GET /api/freshness?property=&action=
 * Latest-day freshness scores, optionally filtered by property and action.
 */
import { sbFetch, jsonError } from "./_supabase.js";

export async function onRequestGet(context) {
  try {
    const { searchParams } = new URL(context.request.url);
    const property = searchParams.get("property");
    const action = searchParams.get("action");

    const dayRow = await sbFetch(
      context.env,
      "/freshness_scores?select=day&order=day.desc&limit=1"
    );
    if (!dayRow.length) return Response.json({ day: null, rows: [] });

    const day = dayRow[0].day;
    let path = `/freshness_scores?select=*&day=eq.${day}`;
    if (property) path += `&property=eq.${encodeURIComponent(property)}`;
    if (action) path += `&action=eq.${encodeURIComponent(action)}`;
    path += "&order=priority_score.desc";

    const rows = await sbFetch(context.env, path);
    return Response.json({ day, rows });
  } catch (e) {
    return jsonError(e.message);
  }
}
