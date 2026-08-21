#!/usr/bin/env python3
"""
backlinks.py — monthly expanded backlink snapshot for Vantage Circle + Vantage Fit.

Pulls from DataForSEO:
  - /backlinks/summary/live          -> totals + DFS rank
  - /backlinks/bulk_new_lost_referring_domains/live -> new/lost refdomain counts
  - /backlinks/backlinks/live        -> top 1,000 individual backlinks
  - /backlinks/referring_domains/live-> top 1,000 referring domains
  - /backlinks/anchors/live          -> top 100 anchor texts

Stores to SQLite (seo_suite.db) and Supabase.

Usage:
    python3 backlinks.py            # run all properties
    python3 backlinks.py --property vantagecircle --dry-run
    python3 backlinks.py --report
"""
import argparse
from datetime import date

from common import DB_PATH, LLM_PROPERTIES, dfs_post, init_db, load_env, supabase_upsert

# Maximum rows to pull per endpoint per property.
LIMITS = {
    "backlinks": 1000,
    "referring_domains": 1000,
    "anchors": 100,
}

AGGREGATE = "(total)"


def pick(obj, *names):
    """First numeric value for any of `names` found anywhere in a nested result."""
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


def dfs_items(result):
    """Yield items from a DataForSEO result that may be wrapped in task metadata."""
    if isinstance(result, list):
        for block in result:
            if isinstance(block, dict):
                if "items" in block and isinstance(block["items"], list):
                    for item in block["items"]:
                        yield item
                else:
                    yield block
    elif isinstance(result, dict):
        if "items" in result and isinstance(result["items"], list):
            for item in result["items"]:
                yield item
        else:
            yield result


def fetch_summary(target):
    result = dfs_post("/backlinks/summary/live", [{"target": target}])
    for item in dfs_items(result):
        return {
            "backlinks": int(pick(item, "backlinks") or 0),
            "refdomains": int(pick(item, "referring_domains", "referring_main_domains") or 0),
            "rank": int(pick(item, "rank") or 0),
        }
    return {"backlinks": 0, "refdomains": 0, "rank": 0}


def fetch_new_lost(target):
    """Return ({new, lost}, [event_rows]) for the trailing ~30 days."""
    result = dfs_post("/backlinks/bulk_new_lost_referring_domains/live",
                      [{"targets": [target]}])
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
    rows = []
    for event, domain, rank in domains:
        rows.append({"event": event, "domain": domain, "rank": rank})
    for event in ("new", "lost"):
        if event in counts:
            rows.append({"event": event, "domain": AGGREGATE, "rank": counts[event]})
    return counts, rows


def fetch_backlinks(target, limit=LIMITS["backlinks"]):
    """Return top N individual backlinks."""
    result = dfs_post("/backlinks/backlinks/live", [{"target": target, "limit": limit}])
    rows = []
    for item in dfs_items(result):
        if item.get("type") != "backlink":
            continue
        anchor = item.get("anchor") or ""
        if item.get("item_type") == "image":
            anchor = item.get("alt") or "[image]"
        rows.append({
            "source_url": item.get("url_from", ""),
            "target_url": item.get("url_to", ""),
            "domain": item.get("domain_from", ""),
            "anchor": anchor,
            "dofollow": bool(item.get("dofollow", True)),
            "first_seen": item.get("first_seen", "")[:10] or None,
            "rank": int(item.get("rank") or 0),
        })
    return rows


def fetch_referring_domains(target, limit=LIMITS["referring_domains"]):
    """Return top N referring domains."""
    result = dfs_post("/backlinks/referring_domains/live",
                      [{"target": target, "limit": limit, "mode": "subdomains"}])
    rows = []
    for item in dfs_items(result):
        if item.get("type") != "backlinks_referring_domain":
            continue
        rows.append({
            "domain": item.get("domain", ""),
            "backlinks": int(pick(item, "backlinks") or 0),
            "ref_ips": int(pick(item, "referring_ips") or 0),
            "rank": int(pick(item, "rank") or 0),
        })
    return rows


def fetch_anchors(target, limit=LIMITS["anchors"]):
    """Return top N anchor texts."""
    result = dfs_post("/backlinks/anchors/live", [{"target": target, "limit": limit}])
    rows = []
    for item in dfs_items(result):
        if item.get("type") != "backlinks_anchor":
            continue
        total = int(pick(item, "backlinks") or 0)
        nofollow = int(pick(item, "referring_domains_nofollow") or 0)
        rows.append({
            "anchor": item.get("anchor") or "[empty / image]",
            "backlinks": total,
            "dofollow_backlinks": max(0, total - nofollow),
        })
    return rows


def run(property_key, today, dry_run=False):
    cfg = LLM_PROPERTIES.get(property_key)
    if not cfg:
        print(f"[{property_key}] Unknown property; skipping.")
        return
    target = cfg["domain"]
    print(f"\n[{property_key}] Fetching backlink data for {target}")

    summary = fetch_summary(target)
    print(f"  summary: {summary['backlinks']:,} backlinks, "
          f"{summary['refdomains']:,} refdomains, rank {summary['rank']}")

    counts, event_domains = fetch_new_lost(target)
    print(f"  new/lost (30d): +{counts.get('new', 0)} / -{counts.get('lost', 0)}")

    backlinks = fetch_backlinks(target)
    print(f"  top backlinks: {len(backlinks)}")

    domains = fetch_referring_domains(target)
    print(f"  referring domains: {len(domains)}")

    anchors = fetch_anchors(target)
    print(f"  anchor texts: {len(anchors)}")

    if dry_run:
        return

    # SQLite
    con = init_db()
    con.execute(
        "INSERT OR REPLACE INTO backlink_snapshots(day, property, backlinks, refdomains, rank) VALUES (?,?,?,?,?)",
        (today, property_key, summary["backlinks"], summary["refdomains"], summary["rank"]))
    for ev in event_domains:
        con.execute(
            "INSERT OR REPLACE INTO refdomain_events(day, property, event, domain, rank) VALUES (?,?,?,?,?)",
            (today, property_key, ev["event"], ev["domain"], ev["rank"]))
    for b in backlinks:
        con.execute(
            "INSERT OR REPLACE INTO backlink_details VALUES (?,?,?,?,?,?,?,?,?)",
            (today, property_key, b["source_url"], b["target_url"], b["domain"],
             b["anchor"], b["dofollow"], b["first_seen"], b["rank"]))
    for d in domains:
        con.execute(
            "INSERT OR REPLACE INTO referring_domains VALUES (?,?,?,?,?,?)",
            (today, property_key, d["domain"], d["backlinks"], d["ref_ips"], d["rank"]))
    for a in anchors:
        con.execute(
            "INSERT OR REPLACE INTO anchor_distribution VALUES (?,?,?,?,?)",
            (today, property_key, a["anchor"], a["backlinks"], a["dofollow_backlinks"]))
    con.commit()
    print(f"  saved to {DB_PATH.name}")

    # Supabase
    supabase_upsert("backlink_snapshots", [{
        "day": today,
        "property": property_key,
        "backlinks": summary["backlinks"],
        "refdomains": summary["refdomains"],
        "rank": summary["rank"],
    }])
    supabase_upsert("refdomain_events", [
        {"day": today, "property": property_key, "event": ev["event"], "domain": ev["domain"], "rank": ev["rank"]}
        for ev in event_domains
    ])
    supabase_upsert("backlink_details", [
        {"day": today, "property": property_key, **b} for b in backlinks
    ])
    supabase_upsert("referring_domains", [
        {"day": today, "property": property_key, **d} for d in domains
    ])
    supabase_upsert("anchor_distribution", [
        {"day": today, "property": property_key, **a} for a in anchors
    ])


def report():
    con = init_db()
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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--property", choices=list(LLM_PROPERTIES.keys()),
                    help="Run one property")
    ap.add_argument("--dry-run", action="store_true", help="Preview, no writes")
    ap.add_argument("--report", action="store_true", help="Local report only")
    args = ap.parse_args()

    if args.report:
        report()
        return

    load_env()
    today = date.today().isoformat()
    props = [args.property] if args.property else list(LLM_PROPERTIES.keys())
    for key in props:
        run(key, today, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
