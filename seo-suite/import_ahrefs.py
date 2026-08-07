#!/usr/bin/env python3
"""
import_ahrefs.py — ONE-TIME history importer (run manually, then forget).

Four imports, all read-only on their sources:

  1. overview    — an Ahrefs Rank Tracker OVERVIEW export -> rank_snapshots
                   (previous + current positions) and keyword_meta
                   (tag, volume, KD, CPC, intent, branded, SERP features, traffic)
  2. ranks       — a plain Ahrefs Rank Tracker CSV export -> rank_snapshots backfill
  3. refdomains  — an Ahrefs lost-refdomains CSV          -> refdomain_events backfill
  4. llm-history — ../llm-keyword-tracker/llm_visibility.db "snapshots" table
                   -> llm_snapshots, so LLM trend history carries over

CSV column mapping is tolerant: headers are matched by name (case-insensitive)
against a list of candidates, so minor export variations still work.

Usage:
    python3 import_ahrefs.py overview ~/Downloads/vc-full-site_overview.csv
    python3 import_ahrefs.py overview ~/Downloads/fit_overview.csv --property vantagefit
    python3 import_ahrefs.py ranks ~/Downloads/ahrefs-rank-tracker.csv
    python3 import_ahrefs.py refdomains ~/Downloads/ahrefs-lost-refdomains.csv
    python3 import_ahrefs.py refdomains new-domains.csv --event new
    python3 import_ahrefs.py llm-history [path-to-llm_visibility.db]
"""
import argparse
import csv
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

from common import init_db

HERE = Path(__file__).parent
LLM_DB_SOURCE = HERE.parent / "llm-keyword-tracker" / "llm_visibility.db"
PROPERTIES = ("vantagecircle", "vantagefit")
UNRANKED = ("", "lost", "not found", "-", "—")
INTENT_COLS = (("navigational", "nav"), ("informational", "info"),
               ("commercial", "com"), ("transactional", "trans"))


def col(row, headers, *candidates):
    """Value of the first column whose header matches any candidate."""
    low = {h.strip().lower(): i for i, h in enumerate(headers)}
    for c in candidates:
        if c in low and low[c] < len(row):
            return row[low[c]].strip()
    return None


def to_num(value):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def to_int(value):
    v = to_num(value)
    return int(v) if v is not None else None


def to_pos(value):
    """Position cell -> int or None (empty / 'Lost' etc. = unranked)."""
    if (value or "").lower() in UNRANKED:
        return None
    return to_int(value)


def to_bool(value):
    return 1 if (value or "").strip().lower() in ("true", "yes", "1") else 0


def insert_snapshot(con, day, keyword, prop, position, url):
    con.execute(
        "INSERT OR REPLACE INTO rank_snapshots"
        "(day, keyword, property, position, url, serp_features) "
        "VALUES (?,?,?,?,?,?)",
        (day, keyword, prop, position, url, json.dumps([])))


def import_overview(con, path, prop):
    """Ahrefs Rank Tracker overview export -> rank_snapshots + keyword_meta."""
    n_snap = n_meta = n_skip = 0
    days = set()
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = next(reader, [])
        for row in reader:
            keyword = col(row, headers, "keyword")
            if not keyword:
                n_skip += 1
                continue
            prev_day = (col(row, headers, "previous update date")
                        or date.today().isoformat())[:10]
            cur_day = (col(row, headers, "current update date")
                       or date.today().isoformat())[:10]
            # snapshots: previous + current (empty position = tracked-unranked row)
            insert_snapshot(con, prev_day, keyword, prop,
                            to_pos(col(row, headers, "previous position")),
                            col(row, headers, "previous url") or "")
            insert_snapshot(con, cur_day, keyword, prop,
                            to_pos(col(row, headers, "current position")),
                            col(row, headers, "current url") or "")
            days.update((prev_day, cur_day))
            n_snap += 2
            # keyword_meta
            intent = {name: True for c, name in INTENT_COLS
                      if to_bool(col(row, headers, c))}
            features = [s.strip()
                        for s in (col(row, headers, "serp features") or "").split(",")
                        if s.strip()]
            con.execute(
                "INSERT OR REPLACE INTO keyword_meta VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (prop, keyword,
                 col(row, headers, "tags", "tag") or "",
                 to_int(col(row, headers, "volume")),
                 to_num(col(row, headers, "keyword difficulty", "kd")),
                 to_num(col(row, headers, "cost per click", "cpc")),
                 json.dumps(intent),
                 to_bool(col(row, headers, "branded")),
                 json.dumps(features),
                 to_num(col(row, headers, "previous traffic")),
                 to_num(col(row, headers, "current traffic"))))
            n_meta += 1
    con.commit()
    span = f"{min(days)} → {max(days)}" if days else "—"
    print(f"overview: imported {n_snap} rank snapshots + {n_meta} keyword_meta rows "
          f"for '{prop}' from {path} (dates {span}; skipped {n_skip} rows)")


def import_ranks(con, path, prop):
    n = 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = next(reader, [])
        for row in reader:
            keyword = col(row, headers, "keyword")
            if not keyword:
                continue
            position = to_pos(col(row, headers, "current position", "position",
                                  "current pos", "pos"))
            day = (col(row, headers, "date", "last checked", "updated",
                       "check date") or date.today().isoformat())[:10]
            url = col(row, headers, "current url", "url", "serp url") or ""
            insert_snapshot(con, day, keyword, prop, position, url)
            n += 1
    con.commit()
    print(f"ranks: imported {n} rows from {path} into rank_snapshots "
          f"(property '{prop}')")


def import_refdomains(con, path, event):
    n = 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = next(reader, [])
        for row in reader:
            domain = col(row, headers, "domain", "referring domain", "refdomain",
                         "domain from")
            if not domain:
                continue
            rank = to_int(col(row, headers, "domain rating", "dr", "rank",
                              "domain rank"))
            day = (col(row, headers, "lost date", "date lost", "lost", "date",
                       "first seen", "last seen")
                   or date.today().isoformat())[:10]
            con.execute("INSERT OR REPLACE INTO refdomain_events VALUES (?,?,?,?)",
                        (day, event, domain, rank))
            n += 1
    con.commit()
    print(f"refdomains: imported {n} '{event}' rows from {path} into refdomain_events")


def import_llm_history(con, src):
    if not Path(src).exists():
        sys.exit(f"source DB not found: {src}")
    src_con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)  # read-only
    try:
        rows = src_con.execute(
            "SELECT day, platform, prompt, mentions, cited_mine, links, answer "
            "FROM snapshots").fetchall()
    except sqlite3.OperationalError:
        sys.exit(f"no 'snapshots' table in {src}")
    for r in rows:
        con.execute("INSERT OR REPLACE INTO llm_snapshots VALUES (?,?,?,?,?,?,?)", r)
    con.commit()
    src_con.close()
    days = len({r[0] for r in rows})
    print(f"llm-history: imported {len(rows)} rows spanning {days} run days "
          f"from {src} into llm_snapshots")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("overview",
                       help="import an Ahrefs Rank Tracker overview export")
    p.add_argument("csv_path")
    p.add_argument("--property", choices=PROPERTIES, default="vantagecircle")
    p = sub.add_parser("ranks", help="import an Ahrefs Rank Tracker CSV export")
    p.add_argument("csv_path")
    p.add_argument("--property", choices=PROPERTIES, default="vantagecircle")
    p = sub.add_parser("refdomains", help="import an Ahrefs refdomains CSV export")
    p.add_argument("csv_path")
    p.add_argument("--event", choices=["new", "lost"], default="lost")
    p = sub.add_parser("llm-history",
                       help="import snapshots from the old llm_visibility.db")
    p.add_argument("db_path", nargs="?", default=str(LLM_DB_SOURCE))
    args = ap.parse_args()

    con = init_db()
    if args.command == "overview":
        import_overview(con, args.csv_path, args.property)
    elif args.command == "ranks":
        import_ranks(con, args.csv_path, args.property)
    elif args.command == "refdomains":
        import_refdomains(con, args.csv_path, args.event)
    elif args.command == "llm-history":
        import_llm_history(con, args.db_path)


if __name__ == "__main__":
    main()
