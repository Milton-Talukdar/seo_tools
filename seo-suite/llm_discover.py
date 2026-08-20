#!/usr/bin/env python3
"""
llm_discover.py — monthly discovery job (runs alongside the weekly tracker).

Port of llm-keyword-tracker/discover.py writing into the shared seo_suite.db.
Runs per project (Vantage Circle / Vantage Fit — see LLM_PROPERTIES in
common.py), each with its own seeds file.

1. Snapshots AI search volume for each seed keyword in the project's seeds CSV
   (AI Keyword Data API — one call, ~$0.01).
2. Mines the LLM Mentions database for the REAL questions people ask AI tools
   about those seeds, each with its AI search volume
   (LLM Mentions API — ~$0.15 per seed).

Self-throttling: skips if it already ran in the last 25 days, so it is safe to
call from the weekly GitHub Action. Use --force to override.

Usage:
    python3 llm_discover.py                        # Vantage Circle (default), if due
    python3 llm_discover.py --property vantagefit  # Vantage Fit, if due
    python3 llm_discover.py --property all         # both projects
    python3 llm_discover.py --force                # run now regardless
"""
import argparse
import json
import re
from datetime import date, timedelta
from pathlib import Path

from common import LLM_PROPERTIES, dfs_post, init_db, load_env, supabase_upsert

HERE = Path(__file__).parent
THROTTLE_DAYS = 25
MENTIONS_LIMIT = 50          # rows per seed
STOPWORDS = {"what", "are", "the", "best", "for", "and", "how", "to", "of",
             "in", "a", "an", "is", "which", "top", "software", "tool",
             "tools", "platform", "platforms", "vs"}


def check_silent_citations(con, cfg, prop, today):
    """Answers that source your domain but never name your brand (~$0.20)."""
    result = dfs_post("/ai_optimization/llm_mentions/search_mentions/live", [{
        "language_name": "English", "location_code": 2840,
        "target": [{"domain": cfg["domain"]}],
        "limit": 100}])
    items = (result[0].get("items") if result else []) or []
    rows = []
    kept = 0
    brand = cfg["you"]                       # e.g. "vantage circle"
    bare = cfg["domain"].split(".")[0]       # e.g. "vantagecircle"
    for it in items:
        srcs = json.dumps(it.get("sources") or []).lower()
        text = ((it.get("question") or "") + " " + (it.get("answer") or ""))
        text = text.lower().replace(".", "")
        named = brand in text or bare in text
        if cfg["domain"] in srcs and not named:
            row = {
                "day": today,
                "query": (it.get("question") or "").strip(),
                "platform": it.get("platform") or "?",
                "ai_search_volume": it.get("ai_search_volume") or 0,
                "property": prop,
            }
            con.execute("INSERT OR REPLACE INTO silent VALUES (?,?,?,?,?)",
                        (row["day"], row["query"], row["platform"],
                         row["ai_search_volume"], prop))
            rows.append(row)
            kept += 1
    return kept, rows


def due(con, prop):
    row = con.execute("SELECT MAX(day) FROM volumes WHERE property=?",
                      (prop,)).fetchone()
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


def snapshot_volumes(con, seeds, prop, today):
    result = dfs_post("/ai_optimization/ai_keyword_data/keywords_search_volume/live",
                      [{"language_name": "English", "location_code": 2840,
                        "keywords": seeds}])
    items = (result[0].get("items") if result else []) or []
    rows = []
    for it in items:
        row = {
            "day": today,
            "keyword": it["keyword"],
            "ai_search_volume": it.get("ai_search_volume") or 0,
            "trend_json": json.dumps(it.get("ai_monthly_searches") or []),
            "property": prop,
        }
        con.execute("INSERT OR REPLACE INTO volumes VALUES (?,?,?,?,?)",
                    (row["day"], row["keyword"], row["ai_search_volume"],
                     row["trend_json"], prop))
        rows.append(row)
    return len(items), rows


def mine_questions(con, seeds, prop, today):
    kept = 0
    rows = []
    for seed in seeds:
        result = dfs_post("/ai_optimization/llm_mentions/search_mentions/live", [{
            "language_name": "English", "location_code": 2840,
            "target": [{"keyword": seed, "search_scope": ["question", "answer"]}],
            "limit": MENTIONS_LIMIT}])
        items = (result[0].get("items") if result else []) or []
        for it in items:
            q = (it.get("question") or "").strip()
            if not q or not is_relevant(q, seed):
                continue
            vol = it.get("ai_search_volume") or 0
            platform = it.get("platform") or "?"
            existing = con.execute(
                "SELECT ai_search_volume, first_seen FROM discovered "
                "WHERE query=? AND property=?", (q, prop)).fetchone()
            if existing:
                first_seen = existing[1]
                prev = existing[0] or 0
                new_vol = max(existing[0], vol)
                delta = new_vol - prev
                con.execute("UPDATE discovered SET ai_search_volume=?, prev_volume=?, "
                            "volume_delta=?, last_seen=? WHERE query=? AND property=?",
                            (new_vol, prev, delta, today, q, prop))
            else:
                first_seen = today
                prev = 0
                delta = vol
                con.execute("INSERT INTO discovered VALUES (?,?,?,?,?,?,?,?,?)",
                            (q, platform, vol, seed, today, today, prop, prev, delta))
            rows.append({
                "query": q,
                "platform": platform,
                "ai_search_volume": vol,
                "seed": seed,
                "first_seen": first_seen,
                "last_seen": today,
                "property": prop,
                "prev_volume": prev,
                "volume_delta": delta,
            })
            kept += 1
    return kept, rows


def run_property(con, prop, args):
    cfg = LLM_PROPERTIES[prop]
    if not args.only and not args.force and not due(con, prop):
        print(f"{cfg['label']}: discovery ran within the last {THROTTLE_DAYS} "
              f"days — skipping (use --force to override).")
        return

    seeds_csv = HERE / cfg["seeds_csv"]
    seeds = [l.strip() for l in open(seeds_csv, encoding="utf-8")
             if l.strip() and not l.startswith("#")]
    today = date.today().isoformat()
    print(f"\n### {cfg['label']} ({prop}) — {len(seeds)} seeds")

    if args.only in (None, "volumes"):
        n_vol, vol_rows = snapshot_volumes(con, seeds, prop, today)
        print(f"volumes: {n_vol} keywords snapshotted")
        supabase_upsert("volumes", vol_rows)
    if args.only in (None, "mentions"):
        n_q, discovered_rows = mine_questions(con, seeds, prop, today)
        print(f"discovered: {n_q} relevant real-user questions stored")
        supabase_upsert("discovered", discovered_rows)
    if args.only in (None, "silent"):
        n_s, silent_rows = check_silent_citations(con, cfg, prop, today)
        print(f"silent citations: {n_s} answers source your site without naming you")
        supabase_upsert("silent", silent_rows)
    con.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--property", choices=list(LLM_PROPERTIES) + ["all"],
                    default="vantagecircle")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", choices=["volumes", "mentions", "silent"],
                    help="run a single job (ignores the throttle)")
    args = ap.parse_args()

    con = init_db()
    load_env()
    props = list(LLM_PROPERTIES) if args.property == "all" else [args.property]
    for prop in props:
        run_property(con, prop, args)


if __name__ == "__main__":
    main()
