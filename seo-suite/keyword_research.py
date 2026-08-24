#!/usr/bin/env python3
"""
keyword_research.py — seed and enrich the keywords table.

Usage:
  python keyword_research.py --import-rank
  python keyword_research.py --import-gsc
  python keyword_research.py --discover "employee engagement" --country us --property vantagecircle
  python keyword_research.py --enrich
"""
import argparse
import os
import sys
from urllib.parse import quote

from common import dfs_post, supabase_upsert, supabase_client


def normalize_keyword(kw):
    return " ".join(str(kw).lower().split())


def fetch_rank_keywords(property_filter=None):
    client = supabase_client()
    if not client:
        print("[keyword_research] Supabase not configured")
        return []
    q = client.table("rank_snapshots").select("property, keyword").neq("keyword", None)
    if property_filter:
        q = q.eq("property", property_filter)
    rows = q.execute().data or []
    out = {}
    for r in rows:
        key = (r["property"], normalize_keyword(r["keyword"]))
        out[key] = {"property": r["property"], "keyword": key[1], "source": "rank", "status": "targeting"}
    return list(out.values())


def fetch_gsc_keywords(property_filter=None):
    client = supabase_client()
    if not client:
        return []
    q = client.table("gsc_llm_queries").select("property, query")
    if property_filter:
        q = q.eq("property", property_filter)
    rows = q.execute().data or []
    out = {}
    for r in rows:
        key = (r.get("property", "vantagecircle"), normalize_keyword(r["query"]))
        out[key] = {"property": key[0], "keyword": key[1], "source": "gsc", "status": "idea"}
    return list(out.values())


def discover_dataforseo(seed, country="us", property="vantagecircle", limit=100):
    """Use DataForSEO keyword suggestions for a seed keyword."""
    if not os.environ.get("DATAFORSEO_LOGIN"):
        print("[keyword_research] DATAFORSEO_LOGIN not set")
        return []
    payload = [{
        "keyword": seed,
        "location_code": 2840 if country == "us" else 2826,  # US / UK fallback
        "language_code": "en",
        "depth": min(limit, 100),
    }]
    res = dfs_post("/keywords_data/google/search_volume/live", payload)
    if not res or res[0].get("status_code") != 20000:
        print("[keyword_research] DataForSEO error:", res[0] if res else "empty")
        return []
    tasks = res[0].get("tasks", [])
    if not tasks:
        return []
    items = tasks[0].get("result", [])
    out = []
    for item in (items or []):
        for kw in item.get("keywords", []):
            out.append({
                "property": property,
                "keyword": normalize_keyword(kw.get("keyword", "")),
                "country": country,
                "search_volume": kw.get("search_volume") or 0,
                "cpc": kw.get("cpc") or 0,
                "competition": kw.get("competition") or 0,
                "keyword_difficulty": kw.get("keyword_difficulty"),
                "search_intent": kw.get("search_intent"),
                "source": "dataforseo",
                "status": "idea",
            })
    return out


def enrich_keywords(property_filter=None):
    """Fetch metrics for keywords that have no search_volume yet."""
    client = supabase_client()
    if not client:
        return
    q = client.table("keywords").select("*").eq("search_volume", 0).limit(100)
    if property_filter:
        q = q.eq("property", property_filter)
    rows = q.execute().data or []
    if not rows:
        print("[keyword_research] no keywords to enrich")
        return
    payload = [{
        "keywords": [r["keyword"] for r in rows],
        "location_code": 2840,
        "language_code": "en",
    }]
    res = dfs_post("/keywords_data/google/search_volume/live", payload)
    if not res or res[0].get("status_code") != 20000:
        print("[keyword_research] enrich error:", res[0] if res else "empty")
        return
    tasks = res[0].get("tasks", [])
    enriched = []
    for task in (tasks or []):
        for item in (task.get("result", []) or []):
            for kw in item.get("keywords", []):
                enriched.append({
                    "keyword": normalize_keyword(kw.get("keyword", "")),
                    "country": "us",
                    "search_volume": kw.get("search_volume") or 0,
                    "cpc": kw.get("cpc") or 0,
                    "competition": kw.get("competition") or 0,
                    "keyword_difficulty": kw.get("keyword_difficulty"),
                    "search_intent": kw.get("search_intent"),
                    "last_updated": "now()",
                })
    # Update via upsert
    if enriched:
        supabase_upsert("keywords", enriched)
        print(f"[keyword_research] enriched {len(enriched)} keywords")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-rank", action="store_true")
    parser.add_argument("--import-gsc", action="store_true")
    parser.add_argument("--discover", help="Seed keyword for DataForSEO suggestions")
    parser.add_argument("--country", default="us")
    parser.add_argument("--property", default="vantagecircle")
    parser.add_argument("--enrich", action="store_true")
    args = parser.parse_args()

    all_rows = []
    if args.import_rank:
        rows = fetch_rank_keywords(args.property)
        print(f"[keyword_research] rank keywords: {len(rows)}")
        all_rows.extend(rows)
    if args.import_gsc:
        rows = fetch_gsc_keywords(args.property)
        print(f"[keyword_research] gsc keywords: {len(rows)}")
        all_rows.extend(rows)
    if args.discover:
        rows = discover_dataforseo(args.discover, args.country, args.property)
        print(f"[keyword_research] discovered: {len(rows)}")
        all_rows.extend(rows)

    if all_rows:
        supabase_upsert("keywords", all_rows)
        print(f"[keyword_research] upserted {len(all_rows)} keywords")

    if args.enrich:
        enrich_keywords(args.property)

    if not any([args.import_rank, args.import_gsc, args.discover, args.enrich]):
        parser.print_help()


if __name__ == "__main__":
    main()
