#!/usr/bin/env python3
"""
backlinks.py — weekly backlink profile snapshot for vantagecircle.com.

1. /backlinks/summary/live -> totals (backlinks, refdomains, DFS rank)
2. /backlinks/bulk_new_lost_referring_domains/live -> new/lost refdomain
   counts over the trailing ~30 days.

Snapshots go into seo_suite.db so the dashboard can trend the link profile.
Honest note: the DataForSEO link index is smaller than Ahrefs' — this covers
trend monitoring; deep forensic exports may still warrant Ahrefs (per-domain
new/lost detail comes from the one-time import_ahrefs.py backfill).

Usage:
    python3 backlinks.py            # run both calls, save + report
    python3 backlinks.py --dry-run  # show what would run; no API calls, no cost
    python3 backlinks.py --report   # no API calls; net change + notable losses
"""
import argparse
from datetime import date

from common import DB_PATH, dfs_post, init_db, load_env

# ---- edit these ------------------------------------------------------------
TARGET = "vantagecircle.com"
AGGREGATE = "(total)"      # domain sentinel for count-only rows from the API
DELAY_SECONDS = 1
EST_COST = 0.02            # summary + bulk call, give or take
# -----------------------------------------------------------------------------


def pick(obj, *names):
    """First numeric value for any of `names` found anywhere in a nested
    result (schema-tolerant, like llm_track.py's extract())."""
    if isinstance(obj, dict):
        for n in names:
            if isinstance(obj.get(n), (int, float)):
                return obj[n]
        for v in obj.values():
            got = pick(v, *names)
            if got is not None:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = pick(v, *names)
            if got is not None:
                return got
    return None


def snapshot_summary(con, today):
    result = dfs_post("/backlinks/summary/live", [{"target": TARGET}])
    backlinks = pick(result, "backlinks") or 0
    refdomains = pick(result, "referring_domains", "referring_main_domains") or 0
    rank = pick(result, "rank") or 0
    con.execute("INSERT OR REPLACE INTO backlink_snapshots VALUES (?,?,?,?)",
                (today, int(backlinks), int(refdomains), int(rank)))
    return int(backlinks), int(refdomains), int(rank)


def snapshot_new_lost(con, today):
    """New/lost refdomain counts. The bulk endpoint returns counts per target
    rather than domain lists, so aggregate rows use domain='(total)' with the
    count stored in the rank column; if a response variant ever includes
    per-domain items, those are stored row by row instead."""
    result = dfs_post("/backlinks/bulk_new_lost_referring_domains/live",
                      [{"targets": [TARGET]}])
    counts, domains = {}, []

    def walk(node):
        if isinstance(node, dict):
            new = node.get("new_referring_domains")
            lost = node.get("lost_referring_domains")
            if isinstance(new, (int, float)) or isinstance(lost, (int, float)):
                counts["new"] = max(counts.get("new", 0), int(new or 0))
                counts["lost"] = max(counts.get("lost", 0), int(lost or 0))
            if isinstance(node.get("domain"), str) and node.get("event") in ("new", "lost"):
                domains.append((node["event"], node["domain"],
                                node.get("rank") if isinstance(node.get("rank"), (int, float)) else None))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(result)
    for event, domain, rank in domains:
        con.execute("INSERT OR REPLACE INTO refdomain_events VALUES (?,?,?,?)",
                    (today, event, domain, rank))
    for event in ("new", "lost"):
        if event in counts:
            con.execute("INSERT OR REPLACE INTO refdomain_events VALUES (?,?,?,?)",
                        (today, event, AGGREGATE, counts[event]))
    return counts


def report(con):
    days = [r[0] for r in con.execute(
        "SELECT DISTINCT day FROM backlink_snapshots ORDER BY day DESC LIMIT 2")]
    if not days:
        print("No backlink data yet. Run the snapshot first.")
        return
    latest = con.execute(
        "SELECT backlinks, refdomains, rank FROM backlink_snapshots WHERE day=?",
        (days[0],)).fetchone()
    print(f"\n=== {days[0]} — {latest[0]:,} backlinks from "
          f"{latest[1]:,} refdomains (DFS rank {latest[2]}) ===")
    if len(days) > 1:
        prev = con.execute(
            "SELECT backlinks, refdomains FROM backlink_snapshots WHERE day=?",
            (days[1],)).fetchone()
        print(f"  net change vs {days[1]}: "
              f"{latest[0] - prev[0]:+,} backlinks, "
              f"{latest[1] - prev[1]:+,} refdomains")
    try:
        events = con.execute(
            "SELECT event, domain, rank FROM refdomain_events WHERE day=? "
            "ORDER BY event, rank DESC", (days[0],)).fetchall()
    except Exception:
        events = []
    for event in ("new", "lost"):
        rows = [(d, r) for e, d, r in events if e == event]
        agg_rows = [r for d, r in rows if d == AGGREGATE]
        if agg_rows:
            print(f"  {event} refdomains (30-day window): {agg_rows[0]}")
        named = [(d, r) for d, r in rows if d != AGGREGATE]
        if named:
            label = "notable new" if event == "new" else "notable lost"
            print(f"  {label} domains:")
            for d, r in named[:10]:
                print(f"    {d[:50]:50s} rank {r if r is not None else '—'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    con = init_db()
    if args.report:
        report(con)
        return

    print(f"2 API calls for {TARGET}  (~${EST_COST:.2f})")
    print("  - /backlinks/summary/live (totals)")
    print("  - /backlinks/bulk_new_lost_referring_domains/live (new/lost counts)")
    if args.dry_run:
        return

    load_env()
    today = date.today().isoformat()
    backlinks, refdomains, rank = snapshot_summary(con, today)
    print(f"totals: {backlinks:,} backlinks, {refdomains:,} refdomains, rank {rank}")
    counts = snapshot_new_lost(con, today)
    print(f"new/lost refdomains (30-day window): "
          f"+{counts.get('new', 0)} / -{counts.get('lost', 0)}")
    con.commit()
    print(f"\nSaved snapshot to {DB_PATH.name}")
    report(con)


if __name__ == "__main__":
    main()
