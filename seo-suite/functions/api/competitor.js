/**
 * GET /api/competitor?property=vantagecircle
 * Recent competitor changes (last 90 days), snapshot summary, self domain.
 */
import { sbFetch, jsonError } from "./_supabase.js";

const PROPERTIES = {
  vantagecircle: { label: "Vantage Circle", domain: "vantagecircle.com" },
  vantagefit: { label: "Vantage Fit", domain: "vantagefit.io" },
};

export async function onRequestGet(context) {
  try {
    const { searchParams } = new URL(context.request.url);
    const property = searchParams.get("property") || "vantagecircle";
    const cfg = PROPERTIES[property] || PROPERTIES.vantagecircle;

    const since = new Date();
    since.setDate(since.getDate() - 90);
    const sinceIso = since.toISOString(); // e.g. 2026-05-15T10:47:48.254Z

    const [changes, snapshots] = await Promise.all([
      sbFetch(
        context.env,
        `/competitor_changes?select=*&property=eq.${encodeURIComponent(property)}&timestamp=gte.${encodeURIComponent(sinceIso)}&order=timestamp.desc&limit=2000`
      ),
      sbFetch(
        context.env,
        `/competitor_snapshots?select=*&property=eq.${encodeURIComponent(property)}&order=day.desc&limit=200`
      ),
    ]);

    // Deduplicate snapshots to latest per competitor
    const latestSnap = {};
    for (const row of snapshots) {
      if (!latestSnap[row.competitor] || row.day > latestSnap[row.competitor].day) {
        latestSnap[row.competitor] = row;
      }
    }

    // Build competitors map
    const competitors = {};
    for (const row of Object.values(latestSnap)) {
      competitors[row.domain] = {
        name: row.competitor,
        total_urls: row.total_urls || 0,
        last_successful_crawl: row.last_successful_crawl || "",
      };
    }
    // Ensure any competitor referenced in changes has an entry
    for (const c of changes) {
      if (!competitors[c.domain]) {
        competitors[c.domain] = {
          name: c.competitor,
          total_urls: 0,
          last_successful_crawl: "",
        };
      }
    }

    return Response.json({
      property,
      label: cfg.label,
      self_domain: cfg.domain,
      changes,
      snapshots: Object.values(latestSnap),
      competitors,
    });
  } catch (e) {
    return jsonError(e.message);
  }
}
