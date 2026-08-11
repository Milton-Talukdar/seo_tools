#!/usr/bin/env python3
"""
keyword_research.py — on-demand keyword ideas from DataForSEO Labs.

Fetches keyword ideas for a seed keyword and stores them so the dashboard's
"Keyword Research" tab can show them with search / filters. Run it whenever
you want to explore a new topic; results persist until you overwrite them
(same seed + source acts as primary key).

Usage:
    python3 keyword_research.py "workplace stress"          # fetch ideas
    python3 keyword_research.py "employee engagement" --limit 50
    python3 keyword_research.py --dry-run "workplace stress"  # preview payload
"""
import argparse
import json
import time
from datetime import date
from pathlib import Path

from common import dfs_post, init_db, load_env

# ---- edit these ------------------------------------------------------------
SOURCE = "ideas"                       # keep source label for future variants
LOCATION_CODE = 2840                   # 2840 = United States
LANGUAGE = "en"
DEFAULT_LIMIT = 100                    # DataForSEO Labs max per call is 1000
COST_HINT = 0.03                       # ~cost per 100-keyword idea call
# -----------------------------------------------------------------------------


def fetch_ideas(seed, limit=DEFAULT_LIMIT):
    result = dfs_post("/dataforseo_labs/google/keyword_ideas/live", [{
        "keywords": [seed],
        "location_code": LOCATION_CODE,
        "language_code": LANGUAGE,
        "limit": limit,
    }])
    items = (result[0].get("items") if result else []) or []
    return items


def fetch_seed_overview(seed):
    """Fetch the seed's own search volume, KD, CPC, etc."""
    result = dfs_post("/dataforseo_labs/google/keyword_overview/live", [{
        "keywords": [seed],
        "location_code": LOCATION_CODE,
        "language_code": LANGUAGE,
    }])
    items = (result[0].get("items") if result else []) or []
    if not items:
        return None
    it = items[0]
    info = it.get("keyword_info") or {}
    props = it.get("keyword_properties") or {}
    intent_obj = props.get("keyword_intent") or {}
    intent_label = ""
    if isinstance(intent_obj, dict):
        intent_label = max(intent_obj, key=intent_obj.get, default="")
    return {
        "volume": info.get("search_volume"),
        "kd": props.get("keyword_difficulty"),
        "cpc": info.get("cpc"),
        "competition": info.get("competition"),
        "intent": intent_label,
        "serp_features": None,
    }


def parse_item(it):
    """Extract a flat dict of fields we care about from a keyword_ideas item."""
    keyword = (it.get("keyword") or "").strip()
    info = it.get("keyword_info") or {}
    props = it.get("keyword_properties") or {}
    serp = it.get("serp_info") or {}

    # intent comes as a dict of {label: probability}; keep top label only
    intent_obj = props.get("keyword_intent") or {}
    intent_label = ""
    if isinstance(intent_obj, dict):
        # pick highest-probability label
        intent_label = max(intent_obj, key=intent_obj.get, default="")

    features = serp.get("item_types") or []
    if not features and isinstance(serp.get("items"), list):
        features = sorted({i.get("type") for i in serp["items"] if i.get("type")})

    return {
        "keyword": keyword,
        "volume": info.get("search_volume"),
        "kd": props.get("keyword_difficulty"),
        "cpc": info.get("cpc"),
        "competition": info.get("competition"),
        "intent": intent_label,
        "serp_features": json.dumps(features) if features else None,
        "parent_topic": (it.get("keyword") or "").strip(),  # DFS has no parent_topic; reuse seed concept
    }


def save(con, seed, rows):
    today = date.today().isoformat()
    n = 0
    for r in rows:
        if not r["keyword"]:
            continue
        con.execute(
            "INSERT OR REPLACE INTO keyword_research "
            "(seed, source, keyword, volume, kd, cpc, competition, intent, "
            " serp_features, parent_topic, fetched) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (seed, SOURCE, r["keyword"], r["volume"], r["kd"], r["cpc"],
             r["competition"], r["intent"] or None, r["serp_features"],
             r["parent_topic"], today))
        n += 1

    # Save the seed's own overview from the dedicated keyword overview API
    seed_overview = fetch_seed_overview(seed)
    if seed_overview is None:
        seed_overview = {"volume": None, "kd": None, "cpc": None,
                         "competition": None, "intent": None, "serp_features": None}
    con.execute(
        "INSERT OR REPLACE INTO seed_overview "
        "(seed, volume, kd, cpc, competition, intent, serp_features, fetched) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (seed, seed_overview["volume"], seed_overview["kd"], seed_overview["cpc"],
         seed_overview["competition"], seed_overview["intent"] or None,
         seed_overview["serp_features"], today))
    con.commit()
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("seed", help="seed keyword to explore")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help=f"max ideas to fetch (default {DEFAULT_LIMIT})")
    ap.add_argument("--dry-run", action="store_true",
                    help="print planned call without hitting the API")
    args = ap.parse_args()

    con = init_db()
    print(f"Keyword research: '{args.seed}' → up to {args.limit} ideas "
          f"(~${COST_HINT * (args.limit / 100):.2f})")
    if args.dry_run:
        print("dry run — no API call made")
        return

    load_env()
    items = fetch_ideas(args.seed, args.limit)
    rows = [parse_item(it) for it in items]
    # brief delay between any future calls (none here, but kept for consistency)
    time.sleep(1)
    n = save(con, args.seed, rows)
    print(f"saved {n} keyword ideas for '{args.seed}'")


if __name__ == "__main__":
    main()
