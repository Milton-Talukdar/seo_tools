#!/usr/bin/env python3
"""
rank_track.py — weekly Google rank tracker for vantagecircle.com.

Reads keywords.csv, fetches the live US top-100 SERP for each keyword via the
DataForSEO SERP API, records our first organic position + ranking URL + the
SERP features present, and stores dated snapshots in seo_suite.db.

Usage:
    python3 rank_track.py              # track all keywords, save + report
    python3 rank_track.py --dry-run    # show what would run; no API calls, no cost
    python3 rank_track.py --limit 3    # only the first 3 keywords (cheap smoke test)
    python3 rank_track.py --report     # no API calls; movers + top-3/10/50 counts
"""
import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

from common import DB_PATH, dfs_post, init_db, load_env

HERE = Path(__file__).parent
KEYWORDS_CSV = HERE / "keywords.csv"

# ---- edit these ------------------------------------------------------------
TARGET_DOMAIN = "vantagecircle.com"   # first organic hit containing this wins
LOCATION_CODE = 2840                  # 2840 = United States
LANGUAGE = "en"
DEPTH = 100                           # how deep into the SERP to look
DELAY_SECONDS = 1                     # pause between API calls
COST_PER_KEYWORD = 0.0006             # live Google SERP at depth 100
# -----------------------------------------------------------------------------

NOT_FOUND = DEPTH + 1                 # sentinel used when comparing positions


def track_keyword(keyword):
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
        if TARGET_DOMAIN in (it.get("domain") or url):
            return it.get("rank_absolute") or it.get("rank_group"), url, features
    return None, "", features


def fmt(pos):
    return str(pos) if pos is not None and pos < NOT_FOUND else "—"


def report(con):
    days = [r[0] for r in con.execute(
        "SELECT DISTINCT day FROM rank_snapshots ORDER BY day DESC LIMIT 2")]
    if not days:
        print("No rank data yet. Run the tracker first.")
        return
    latest = days[0]
    rows = con.execute(
        "SELECT keyword, position FROM rank_snapshots WHERE day=?",
        (latest,)).fetchall()
    ranked = [p for _, p in rows if p is not None]
    print(f"\n=== {latest} — {len(ranked)}/{len(rows)} keywords ranking in "
          f"top {DEPTH} ===")
    print(f"  top 3: {sum(p <= 3 for p in ranked)}   "
          f"top 10: {sum(p <= 10 for p in ranked)}   "
          f"top 50: {sum(p <= 50 for p in ranked)}")
    if len(days) < 2:
        print("  first run — movers appear from the second run on")
        return
    prev = dict(con.execute(
        "SELECT keyword, position FROM rank_snapshots WHERE day=?",
        (days[1],)).fetchall())
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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    con = init_db()
    if args.report:
        report(con)
        return

    keywords = [l.strip() for l in open(KEYWORDS_CSV, encoding="utf-8")
                if l.strip() and not l.startswith("#")]
    if args.limit:
        keywords = keywords[:args.limit]
    print(f"{len(keywords)} keywords = {len(keywords)} API calls"
          f"  (~${len(keywords) * COST_PER_KEYWORD:.3f})")
    if args.dry_run:
        for k in keywords:
            print("  -", k)
        return

    load_env()
    today = date.today().isoformat()
    done = 0
    for keyword in keywords:
        try:
            position, url, features = track_keyword(keyword)
        except Exception as e:
            print(f"ERROR {keyword[:40]}: {e}", file=sys.stderr)
            continue
        con.execute("INSERT OR REPLACE INTO rank_snapshots VALUES (?,?,?,?,?)",
                    (today, keyword, position, url, json.dumps(features)))
        con.commit()
        done += 1
        print(f"[{done}/{len(keywords)}] {keyword[:45]:45s} pos: {fmt(position):>3s}"
              f"{'  ' + url[:60] if url else ''}")
        time.sleep(DELAY_SECONDS)
    print(f"\nSaved {done}/{len(keywords)} results to {DB_PATH.name}")
    report(con)


if __name__ == "__main__":
    main()
