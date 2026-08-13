/**
 * GET /api/backlinks
 * Latest backlink snapshots + latest refdomain events.
 */
import { sbFetch, jsonError } from "./_supabase.js";

export async function onRequestGet(context) {
  try {
    const [snapshots, events] = await Promise.all([
      sbFetch(context.env, "/backlink_snapshots?select=*&order=day.desc&limit=8"),
      sbFetch(context.env, "/refdomain_events?select=*&order=day.desc&limit=40"),
    ]);
    return Response.json({ snapshots, events });
  } catch (e) {
    return jsonError(e.message);
  }
}
