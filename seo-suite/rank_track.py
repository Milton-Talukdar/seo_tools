#!/usr/bin/env python3
"""
rank_track.py — weekly Google rank tracker for the tracked properties.

Reads each property's keyword CSV (format: keyword,tag — one per line), fetches
the live US top-100 SERP for each keyword via the DataForSEO SERP API, records
the property's first organic position + ranking URL + the SERP features present,
and stores dated snapshots in seo_suite.db. Tags are upserted into keyword_meta
so the dashboard can group by them.

Usage:
    python3 rank_track.py                        # track all properties, save + report
    python3 rank_track.py --property vantagefit  # track just one property
    python3 rank_track.py --dry-run              # show what would run; no API calls
    python3 rank_track.py --limit 3              # only the first 3 keywords per property
    python3 rank_track.py --report               # no API calls; per-property overview
"""
import argparse
import csv
import json
import sys
import time
from datetime import date
from pathlib import Path

from common import DB_PATH, dfs_post, init_db, load_env

HERE = Path(__file__).parent

# ---- edit these ------------------------------------------------------------
PROPERTIES = {"vantagecircle": {"label": "Vantage Circle",
                                "domain": "vantagecircle.com",
                                "csv": "keywords.csv"},
              "vantagefit":    {"label": "Vantage Fit",
                                "domain": "vantagefit.io",
                                "csv": "keywords-fit.csv"}}
LOCATION_CODE = 2840                  # 2840 = United States
LANGUAGE = "en"
DEPTH = 100                           # how deep into the SERP to look
DELAY_SECONDS = 1                     # pause between API calls
COST_PER_KEYWORD = 0.0006             # live Google SERP at depth 100
# -----------------------------------------------------------------------------

NOT_FOUND = DEPTH + 1                 # sentinel used when comparing positions


def read_keywords(path):
    """[(keyword, tag), ...] from a 'keyword,tag' CSV; # lines are comments."""
    rows = []
    if not path.exists():
        return rows
    for rec in csv.reader(open(path, encoding="utf-8")):
        if not rec or rec[0].strip().startswith("#"):
            continue
        keyword = rec[0].strip()
        if keyword:
            rows.append((keyword, rec[1].strip() if len(rec) > 1 else ""))
    return rows


def upsert_tags(con, prop, keywords):
    for keyword, tag in keywords:
        con.execute(
            "INSERT INTO keyword_meta(property, keyword, tag) VALUES (?,?,?) "
            "ON CONFLICT(property, keyword) DO UPDATE SET tag=excluded.tag",
            (prop, keyword, tag))
    con.commit()


def track_keyword(domain, keyword):
    """Return (position, url, serp_features). position is None when not found."""
    task = {"keyword": keyword, "location_code": LOCATION_CODE,
            "language_code": LANGUAGE, "depth": DEPTH}
    result = dfs_post("/serp/google/organic/live/advanced", [task])
    serp = result[0] if result and isinstance(result[0], dict) else {}
    items = serp.get("items") or []
    features = serp.get("item_types") or sorted(
        {it.get("type") for it in items if isinstance(it, dict) and it.get("type")})
    for it in items:
        if not isinstance(it, dict) or it.get("type") != "organic":
            continue
        url = it.get("url") or ""
        if domain in (it.get("domain") or url):
            return it.get("rank_absolute") or it.get("rank_group"), url, features
    return None, "", features


def fmt(pos):
    return str(pos) if pos is not None and pos < NOT_FOUND else "—"


def report(con, properties=None):
    props = properties or list(PROPERTIES)
    any_data = False
    for prop in props:
        counts = con.execute(
            "SELECT day, COUNT(*) FROM rank_snapshots WHERE property=? "
            "GROUP BY day ORDER BY day DESC", (prop,)).fetchall()
        if not counts:
            continue
        # ignore partial days (e.g. --limit smoke tests): keep days covering
        # at least half of the fullest day's keywords
        fullest = max(c for _, c in counts)
        days = [d for d, c in counts if c >= fullest / 2][:2]
        if not days:
            continue
        any_data = True
        label = PROPERTIES.get(prop, {}).get("label", prop)
        latest = days[0]
        rows = con.execute(
            "SELECT keyword, position FROM rank_snapshots WHERE day=? AND property=?",
            (latest, prop)).fetchall()
        ranked = [p for _, p in rows if p is not None]
        print(f"\n=== {label} — {latest} — {len(ranked)}/{len(rows)} keywords "
              f"ranking in top {DEPTH} ===")
        print(f"  top 3: {sum(p <= 3 for p in ranked)}   "
              f"top 10: {sum(p <= 10 for p in ranked)}   "
              f"top 50: {sum(p <= 50 for p in ranked)}")
        if len(days) < 2:
            print("  first run — movers appear from the second run on")
            continue
        prev = dict(con.execute(
            "SELECT keyword, position FROM rank_snapshots WHERE day=? AND property=?",
            (days[1], prop)).fetchall())
        # positive delta = improved; unranked counts as NOT_FOUND
        movers = sorted(
            (((prev.get(k) or NOT_FOUND) - (p or NOT_FOUND), k, prev.get(k), p)
              for k, p in rows),
            key=lambda m: -m[0])
        ups = [m for m in movers if m[0] > 0][:10]
        downs = [m for m in movers if m[0] < 0][-10:][::-1]
        if ups:
            print(f"\n  biggest gains vs {days[1]}:")
            for d, k, old, new in ups:
                print(f"    +{d:3d}  {k[:45]:45s} {fmt(old):>3s} -> {fmt(new)}")
        if downs:
            print(f"\n  biggest drops vs {days[1]}:")
            for d, k, old, new in downs:
                print(f"    {d:4d}  {k[:45]:45s} {fmt(old):>3s} -> {fmt(new)}")
        if not ups and not downs:
            print("  no movement since the previous run")
    if not any_data:
        print("No rank data yet. Run the tracker first.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--property", choices=list(PROPERTIES),
                    help="track just one property")
    args = ap.parse_args()

    con = init_db()
    if args.report:
        report(con, [args.property] if args.property else None)
        return

    props = [args.property] if args.property else list(PROPERTIES)
    plan = []   # (prop, [(keyword, tag), ...])
    for prop in props:
        keywords = read_keywords(HERE / PROPERTIES[prop]["csv"])
        if not keywords:
            print(f"note: {PROPERTIES[prop]['csv']} has no keywords — "
                  f"skipping {PROPERTIES[prop]['label']}")
            continue
        if args.limit:
            keywords = keywords[:args.limit]
        plan.append((prop, keywords))

    total = sum(len(k) for _, k in plan)
    print(f"{total} keywords across {len(plan)} propert"
          f"{'y' if len(plan) == 1 else 'ies'} = {total} API calls"
          f"  (~${total * COST_PER_KEYWORD:.3f})")
    for prop, keywords in plan:
        print(f"  {PROPERTIES[prop]['label']}: {len(keywords)} keywords")
    if args.dry_run:
        for prop, keywords in plan:
            for k, tag in keywords:
                print(f"    - [{prop}] {k}{'  #' + tag if tag else ''}")
        return
    if not plan:
        print("Nothing to track — add keywords to a property CSV first.")
        return

    load_env()
    today = date.today().isoformat()
    done = 0
    for prop, keywords in plan:
        domain = PROPERTIES[prop]["domain"]
        upsert_tags(con, prop, keywords)
        for keyword, _ in keywords:
            try:
                position, url, features = track_keyword(domain, keyword)
            except Exception as e:
                print(f"ERROR {keyword[:40]}: {e}", file=sys.stderr)
                continue
            con.execute("INSERT OR REPLACE INTO rank_snapshots VALUES (?,?,?,?,?,?)",
                        (today, keyword, prop, position, url, json.dumps(features)))
            con.commit()
            done += 1
            print(f"[{done}/{total}] {prop:14s} {keyword[:40]:40s} "
                  f"pos: {fmt(position):>3s}{'  ' + url[:55] if url else ''}")
            time.sleep(DELAY_SECONDS)
    print(f"\nSaved {done}/{total} results to {DB_PATH.name}")
    report(con, props)


if __name__ == "__main__":
    main()
