#!/usr/bin/env python3
"""
enrich.py — monthly keyword-metadata refresh (runs alongside the weekly jobs).

Fills in keyword_meta for every tracked keyword across all properties:

1. Search volume + CPC   — /keywords_data/google_ads/search_volume/live
2. Keyword difficulty    — /dataforseo_labs/google/bulk_keyword_difficulty/live
3. Search intent         — /dataforseo_labs/google/search_intent/live

Self-throttling: skips if it already ran in the last 25 days, so it is safe to
call from the weekly GitHub Action. Use --force to override.

Usage:
    python3 enrich.py            # run if due, skip otherwise
    python3 enrich.py --force    # run now regardless
    python3 enrich.py --dry-run  # show call counts + cost; no API calls
"""
import argparse
import json
import time
from datetime import date, timedelta

from common import dfs_post, init_db, load_env, supabase_upsert
from rank_track import HERE, PROPERTIES, read_keywords

# ---- edit these ------------------------------------------------------------
LOCATION_CODE = 2840                 # 2840 = United States
LANGUAGE = "en"
THROTTLE_DAYS = 25
CHUNK = 1000                         # keywords per API call (endpoint max)
DELAY_SECONDS = 1
COST_PER_CALL = {"volume": 0.10, "difficulty": 0.25, "intent": 0.50}  # ~per 1000 kw
MAX_KW_LEN = 80                      # DFS keyword text limit for these endpoints
# -----------------------------------------------------------------------------


def all_keywords():
    """[(property, keyword), ...] across every property CSV (<= MAX_KW_LEN)."""
    out, skipped = [], 0
    for prop, cfg in PROPERTIES.items():
        for keyword, _ in read_keywords(HERE / cfg["csv"]):
            if len(keyword) > MAX_KW_LEN:
                skipped += 1
                continue
            out.append((prop, keyword))
    if skipped:
        print(f"note: skipped {skipped} keyword(s) over {MAX_KW_LEN} chars "
              f"(DFS endpoint limit)")
    return out


def due(con):
    con.execute("CREATE TABLE IF NOT EXISTS enrich_log(day TEXT PRIMARY KEY)")
    row = con.execute("SELECT MAX(day) FROM enrich_log").fetchone()
    if not row or not row[0]:
        return True
    return date.fromisoformat(row[0]) <= date.today() - timedelta(days=THROTTLE_DAYS)


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def update_meta(con, prop, keyword, rows, **fields):
    cols = ", ".join(["property", "keyword", *fields])
    marks = ",".join("?" * (2 + len(fields)))
    sets = ", ".join(f"{k}=excluded.{k}" for k in fields)
    con.execute(
        f"INSERT INTO keyword_meta({cols}) VALUES ({marks}) "
        f"ON CONFLICT(property, keyword) DO UPDATE SET {sets}",
        (prop, keyword, *fields.values()))
    rows.append({"property": prop, "keyword": keyword, **fields})


def enrich_volumes(con, pairs, rows):
    n = 0
    for group in chunks(pairs, CHUNK):
        result = dfs_post("/keywords_data/google_ads/search_volume/live",
                          [{"location_code": LOCATION_CODE, "language_code": LANGUAGE,
                            "keywords": [k for _, k in group]}])
        items = (result[0].get("items") if result else []) or []
        by_kw = {}
        for it in items:
            if isinstance(it, dict) and it.get("keyword"):
                by_kw[it["keyword"].lower()] = it
        for prop, keyword in group:
            it = by_kw.get(keyword.lower()) or {}
            update_meta(con, prop, keyword, rows,
                        volume=it.get("search_volume"),
                        cpc=it.get("cpc"))
        n += len(group)
        time.sleep(DELAY_SECONDS)
    return n


def enrich_difficulty(con, pairs, rows):
    n = 0
    for group in chunks(pairs, CHUNK):
        result = dfs_post("/dataforseo_labs/google/bulk_keyword_difficulty/live",
                          [{"location_code": LOCATION_CODE, "language_code": LANGUAGE,
                            "keywords": [k for _, k in group]}])
        items = (result[0].get("items") if result else []) or []
        by_kw = {}
        for it in items:
            if isinstance(it, dict) and it.get("keyword"):
                by_kw[it["keyword"].lower()] = it
        for prop, keyword in group:
            it = by_kw.get(keyword.lower()) or {}
            update_meta(con, prop, keyword, rows,
                        kd=it.get("keyword_difficulty"))
        n += len(group)
        time.sleep(DELAY_SECONDS)
    return n


INTENT_LABELS = {"informational": "informational", "navigational": "navigational",
                 "commercial": "commercial", "transactional": "transactional"}


def enrich_intent(con, pairs, rows):
    n = 0
    for group in chunks(pairs, CHUNK):
        result = dfs_post("/dataforseo_labs/google/search_intent/live",
                          [{"language_code": LANGUAGE,
                            "keywords": [k for _, k in group]}])
        items = (result[0].get("items") if result else []) or []
        by_kw = {}
        for it in items:
            if isinstance(it, dict) and it.get("keyword"):
                by_kw[it["keyword"].lower()] = it
        for prop, keyword in group:
            it = by_kw.get(keyword.lower()) or {}
            label = ((it.get("keyword_intent") or {}).get("label") or "").lower()
            intent = {INTENT_LABELS[label]: True} if label in INTENT_LABELS else {}
            update_meta(con, prop, keyword, rows, intent=json.dumps(intent))
        n += len(group)
        time.sleep(DELAY_SECONDS)
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    con = init_db()
    if not args.force and not args.dry_run and not due(con):
        print(f"Enrichment ran within the last {THROTTLE_DAYS} days — skipping "
              f"(use --force to override).")
        return

    pairs = all_keywords()
    calls = max(1, -(-len(pairs) // CHUNK))  # ceil
    cost = calls * sum(COST_PER_CALL.values())
    print(f"{len(pairs)} keywords = {calls * 3} API calls "
          f"(3 endpoints x {calls} chunk{'s' if calls > 1 else ''})  (~${cost:.2f})")
    if args.dry_run:
        for name, per in COST_PER_CALL.items():
            print(f"  - {name}: {calls} call{'s' if calls > 1 else ''} (~${calls * per:.2f})")
        return

    load_env()
    today = date.today().isoformat()
    meta_rows = []
    n = enrich_volumes(con, pairs, meta_rows)
    print(f"volumes: {n} keywords updated")
    supabase_upsert("keyword_meta", meta_rows)
    n = enrich_difficulty(con, pairs, meta_rows)
    print(f"difficulty: {n} keywords updated")
    supabase_upsert("keyword_meta", meta_rows)
    n = enrich_intent(con, pairs, meta_rows)
    print(f"intent: {n} keywords updated")
    supabase_upsert("keyword_meta", meta_rows)
    con.execute("INSERT OR REPLACE INTO enrich_log VALUES (?)", (today,))
    con.commit()
    supabase_upsert("enrich_log", [{"day": today}])
    print(f"keyword_meta refreshed for {len(pairs)} keywords "
          f"({len(PROPERTIES)} properties)")


if __name__ == "__main__":
    main()
