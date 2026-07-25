#!/usr/bin/env python3
"""
discover.py — monthly discovery job (runs alongside the weekly tracker).

1. Snapshots AI search volume for each seed keyword in seeds.csv
   (AI Keyword Data API — one call, ~$0.01).
2. Mines the LLM Mentions database for the REAL questions people ask AI tools
   about those seeds, each with its AI search volume
   (LLM Mentions API — ~$0.15 per seed).

Self-throttling: skips if it already ran in the last 25 days, so it is safe to
call from the weekly GitHub Action. Use --force to override.

Usage:
    python3 discover.py            # run if due, skip otherwise
    python3 discover.py --force    # run now regardless
"""
import argparse
import json
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from llm_track import DB_PATH, dfs_post, load_env

HERE = Path(__file__).parent
SEEDS_CSV = HERE / "seeds.csv"
THROTTLE_DAYS = 25
MENTIONS_LIMIT = 50          # rows per seed
STOPWORDS = {"what", "are", "the", "best", "for", "and", "how", "to", "of",
             "in", "a", "an", "is", "which", "top", "software", "tool",
             "tools", "platform", "platforms", "vs"}


def init_tables(con):
    con.execute("""CREATE TABLE IF NOT EXISTS volumes(
        day TEXT, keyword TEXT, ai_search_volume INTEGER, trend_json TEXT,
        PRIMARY KEY(day, keyword))""")
    con.execute("""CREATE TABLE IF NOT EXISTS discovered(
        query TEXT PRIMARY KEY, platform TEXT, ai_search_volume INTEGER,
        seed TEXT, first_seen TEXT, last_seen TEXT)""")


def due(con):
    row = con.execute("SELECT MAX(day) FROM volumes").fetchone()
    if not row or not row[0]:
        return True
    return date.fromisoformat(row[0]) <= date.today() - timedelta(days=THROTTLE_DAYS)


def is_relevant(question, seed):
    q = question.lower()
    toks = [t for t in re.findall(r"[a-z]+", seed.lower()) if t not in STOPWORDS]
    if not toks:
        return True
    hits = sum(1 for t in toks if t in q)
    need = len(toks) if len(toks) <= 2 else len(toks) - 1
    return hits >= need


def snapshot_volumes(con, seeds, today):
    result = dfs_post("/ai_keyword_data/keywords_search_volume/live",
                      [{"language_name": "English", "location_code": 2840,
                        "keywords": seeds}])
    items = (result[0].get("items") if result else []) or []
    for it in items:
        con.execute("INSERT OR REPLACE INTO volumes VALUES (?,?,?,?)",
                    (today, it["keyword"], it.get("ai_search_volume") or 0,
                     json.dumps(it.get("ai_monthly_searches") or [])))
    return len(items)


def mine_questions(con, seeds, today):
    kept = 0
    for seed in seeds:
        result = dfs_post("/llm_mentions/search_mentions/live", [{
            "language_name": "English", "location_code": 2840,
            "target": [{"keyword": seed, "search_scope": ["question", "answer"]}],
            "limit": MENTIONS_LIMIT}])
        items = (result[0].get("items") if result else []) or []
        for it in items:
            q = (it.get("question") or "").strip()
            if not q or not is_relevant(q, seed):
                continue
            vol = it.get("ai_search_volume") or 0
            row = con.execute("SELECT ai_search_volume, first_seen FROM discovered "
                              "WHERE query=?", (q,)).fetchone()
            if row:
                con.execute("UPDATE discovered SET ai_search_volume=?, last_seen=? "
                            "WHERE query=?", (max(row[0], vol), today, q))
            else:
                con.execute("INSERT INTO discovered VALUES (?,?,?,?,?,?)",
                            (q, it.get("platform") or "?", vol, seed, today, today))
            kept += 1
    return kept


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(DB_PATH)
    init_tables(con)
    if not args.force and not due(con):
        print(f"Discovery ran within the last {THROTTLE_DAYS} days — skipping "
              f"(use --force to override).")
        return

    seeds = [l.strip() for l in open(SEEDS_CSV, encoding="utf-8")
             if l.strip() and not l.startswith("#")]
    load_env()
    today = date.today().isoformat()

    n_vol = snapshot_volumes(con, seeds, today)
    print(f"volumes: {n_vol} keywords snapshotted")
    n_q = mine_questions(con, seeds, today)
    con.commit()
    print(f"discovered: {n_q} relevant real-user questions stored")


if __name__ == "__main__":
    main()
