#!/usr/bin/env python3
"""
gsc_llm_queries.py — pull GSC query data and identify probable LLM / AI searches.

Run manually or on a schedule:
    python3 gsc_llm_queries.py
    python3 gsc_llm_queries.py --days 28 --dry-run

Requirements:
    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
    GSC_SERVICE_ACCOUNT_JSON environment variable set (service account JSON)
    SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY for upserts
"""

import argparse
import json
import os
import re
from datetime import datetime, timedelta

from common import LLM_PROPERTIES, load_env, supabase_upsert

# Same read-only scope used by freshness.py
GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

# Map each property to its exact Search Console site URL.
# Domain properties (sc-domain:...) are preferred because they cover all subdomains.
GSC_SITE_URLS = {
    "vantagecircle": "sc-domain:vantagecircle.com",
    "vantagefit": "sc-domain:vantagefit.io",
}

# Heuristic signals that a query is likely an LLM / conversational / AI search.
# Each signal adds 1 to llm_score. Queries need score >= 2 to be stored.
LLM_SIGNALS = [
    ("question_word", re.compile(r"^(what|how|why|when|where|who|which|can|should|is it|are there|do i|does)\b", re.I)),
    ("comparison", re.compile(r"\b(vs\.?|versus|compare|comparison|or|alternative|like)\b", re.I)),
    ("best_top", re.compile(r"\b(best|top|leading|highest rated|most popular)\b", re.I)),
    ("long_tail", re.compile(r"\b(software|platform|tool|app|solution|program|system)\b", re.I)),
    ("conversational", re.compile(r"\b(for me|for my|i need|we need|our company|my team|small business|mid size)\b", re.I)),
]

# Filters that drop low-quality / AI-generated prompt dumps.
AI_PERSONA_PATTERNS = [
    # Multiple age ranges: "18-24 or 25-34 or 35-44"
    re.compile(r"\b\d{1,2}[-–]\d{1,2}\s+or\s+\d{1,2}[-–]\d{1,2}"),
    # "i am a ... or ... or ..." repeated alternatives
    re.compile(r"\bi am a\b.*\bor\b.*\bor\b.*\bor\b", re.I),
    # AI prompt injection prefixes
    re.compile(r"^(answer the user request|user request:|prompt:|as an ai|you are a)"),
]

MIN_WORDS = 4
MIN_SCORE = 2
MAX_QUERY_CHARS = 200
MAX_QUERY_WORDS = 35
MAX_WORDS_FOR_SHORT_BONUS = 6


def gsc_service_account_credentials():
    """Return credentials if GSC_SERVICE_ACCOUNT_JSON is set."""
    raw = os.environ.get("GSC_SERVICE_ACCOUNT_JSON")
    if not raw:
        return None
    try:
        import google.auth.transport.requests
        from google.oauth2 import service_account

        info = json.loads(raw)
        return service_account.Credentials.from_service_account_info(
            info, scopes=GSC_SCOPES
        )
    except Exception as e:
        print(f"GSC credentials error: {e}")
        return None


def fetch_gsc_queries(credentials, site_url, start_date, end_date):
    """Yield (query, clicks, impressions, ctr, position) rows from GSC."""
    try:
        from googleapiclient.discovery import build
    except ImportError:
        print("google-api-python-client not installed; skipping GSC")
        return

    service = build("webmasters", "v3", credentials=credentials, cache_discovery=False)
    row_limit = 10000
    start_row = 0

    while True:
        req = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": ["query"],
            "rowLimit": row_limit,
            "startRow": start_row,
        }
        resp = service.searchanalytics().query(siteUrl=site_url, body=req).execute()
        rows = resp.get("rows", [])
        if not rows:
            break

        for row in rows:
            keys = row.get("keys", [])
            query = keys[0] if keys else ""
            yield {
                "query": query,
                "clicks": int(row.get("clicks", 0)),
                "impressions": int(row.get("impressions", 0)),
                "ctr": float(row.get("ctr", 0.0)),
                "position": float(row.get("position", 0.0)),
            }

        if len(rows) < row_limit:
            break
        start_row += row_limit


def is_junk_query(query):
    """Return True for AI persona dumps / prompt injection / excessive length."""
    if len(query) > MAX_QUERY_CHARS:
        return True
    words = query.split()
    if len(words) > MAX_QUERY_WORDS:
        return True
    for pattern in AI_PERSONA_PATTERNS:
        if pattern.search(query):
            return True
    return False


def score_query(query):
    """Return (score, signals[]) for a query. Return (0, []) for junk."""
    words = query.split()
    if len(words) < MIN_WORDS:
        return 0, []
    if is_junk_query(query):
        return 0, []

    signals = []
    for name, pattern in LLM_SIGNALS:
        if pattern.search(query):
            signals.append(name)

    # Long-tail bonus: very specific multi-word queries are more LLM-like.
    if len(words) >= 8:
        signals.append("very_long")
    elif len(words) >= MAX_WORDS_FOR_SHORT_BONUS:
        signals.append("long")

    return len(signals), signals


def run(property_key, days=28, dry_run=False):
    cfg = LLM_PROPERTIES[property_key]
    site_url = GSC_SITE_URLS.get(property_key)
    if not site_url:
        print(f"[{property_key}] No GSC site URL configured; skipping.")
        return

    end = datetime.utcnow().date()
    start = end - timedelta(days=days - 1)
    start_str = start.isoformat()
    end_str = end.isoformat()
    day_str = end_str

    print(f"[{property_key}] Fetching GSC queries for {site_url} ({start_str} to {end_str})")

    creds = gsc_service_account_credentials()
    if not creds:
        print("GSC_SERVICE_ACCOUNT_JSON not configured; nothing to do.")
        return

    rows = []
    for r in fetch_gsc_queries(creds, site_url, start_str, end_str):
        score, signals = score_query(r["query"])
        if score >= MIN_SCORE:
            rows.append({
                "property": property_key,
                "day": day_str,
                "query": r["query"],
                "clicks": r["clicks"],
                "impressions": r["impressions"],
                "ctr": round(r["ctr"], 4),
                "position": round(r["position"], 2),
                "llm_score": score,
                "llm_signals": json.dumps(signals),
            })

    rows.sort(key=lambda x: (-x["llm_score"], -x["clicks"], x["query"]))
    print(f"[{property_key}] Found {len(rows)} probable LLM queries (score >= {MIN_SCORE})")

    if dry_run:
        for r in rows[:10]:
            print(f"  score={r['llm_score']} clicks={r['clicks']} pos={r['position']} q={r['query']}")
        return

    supabase_upsert("gsc_llm_queries", rows)


def main():
    load_env()
    parser = argparse.ArgumentParser(description="Pull probable LLM queries from GSC")
    parser.add_argument("--days", type=int, default=28, help="Lookback window (default 28)")
    parser.add_argument("--dry-run", action="store_true", help="Preview, do not write to Supabase")
    parser.add_argument("--property", choices=list(LLM_PROPERTIES.keys()), help="Run one property")
    args = parser.parse_args()

    props = [args.property] if args.property else list(LLM_PROPERTIES.keys())
    for key in props:
        run(key, days=args.days, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
