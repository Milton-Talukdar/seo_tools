#!/usr/bin/env python3
"""
gsc_page_performance.py — pull page-level GSC stats for the Content Engine.

Aggregates GSC query-page data by page and upserts to gsc_page_stats.
Run manually or on a schedule:
    python3 gsc_page_performance.py
    python3 gsc_page_performance.py --days 28 --dry-run

Requirements:
    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
    GSC_SERVICE_ACCOUNT_JSON environment variable set (service account JSON)
    SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY for upserts
"""
import argparse
import json
import os
from datetime import datetime, timedelta

from common import load_env, supabase_upsert

GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
GSC_SITE_URLS = {
    "vantagecircle": "sc-domain:vantagecircle.com",
    "vantagefit": "sc-domain:vantagefit.io",
}


def gsc_service_account_credentials():
    raw = os.environ.get("GSC_SERVICE_ACCOUNT_JSON")
    if not raw:
        return None
    try:
        import google.auth.transport.requests
        from google.oauth2 import service_account
        info = json.loads(raw)
        return service_account.Credentials.from_service_account_info(info, scopes=GSC_SCOPES)
    except Exception as e:
        print(f"GSC credentials error: {e}")
        return None


def fetch_gsc_query_pages(credentials, site_url, start_date, end_date):
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
            "dimensions": ["query", "page"],
            "rowLimit": row_limit,
            "startRow": start_row,
        }
        resp = service.searchanalytics().query(siteUrl=site_url, body=req).execute()
        rows = resp.get("rows", [])
        if not rows:
            break
        for row in rows:
            keys = row.get("keys", [])
            yield {
                "query": keys[0] if len(keys) > 0 else "",
                "page": keys[1] if len(keys) > 1 else "",
                "clicks": int(row.get("clicks", 0)),
                "impressions": int(row.get("impressions", 0)),
                "ctr": float(row.get("ctr", 0.0)),
                "position": float(row.get("position", 0.0)),
            }
        if len(rows) < row_limit:
            break
        start_row += row_limit


def aggregate_by_page(rows):
    pages = {}
    for r in rows:
        p = r["page"]
        if p not in pages:
            pages[p] = {"clicks": 0, "impressions": 0, "weighted_pos": 0.0}
        pages[p]["clicks"] += r["clicks"]
        pages[p]["impressions"] += r["impressions"]
        pages[p]["weighted_pos"] += r["position"] * r["impressions"]

    out = []
    for page, stats in pages.items():
        imp = stats["impressions"]
        pos = round(stats["weighted_pos"] / imp, 2) if imp > 0 else 0.0
        ctr = round(stats["clicks"] / imp, 4) if imp > 0 else 0.0
        out.append({
            "page": page,
            "clicks": stats["clicks"],
            "impressions": imp,
            "ctr": ctr,
            "position": pos,
        })
    return out


def sync_property(property, credentials, days, dry_run):
    site_url = GSC_SITE_URLS.get(property)
    if not site_url:
        print(f"[gsc] unknown property: {property}")
        return []

    end = datetime.now().date()
    start = end - timedelta(days=days - 1)
    end_str = end.isoformat()
    start_str = start.isoformat()
    print(f"[gsc] fetching {property} from {start_str} to {end_str}")

    raw = list(fetch_gsc_query_pages(credentials, site_url, start_str, end_str))
    print(f"[gsc] {property}: {len(raw)} query-page rows")
    pages = aggregate_by_page(raw)
    print(f"[gsc] {property}: {len(pages)} unique pages")

    rows = [
        {
            "property": property,
            "day": end_str,
            "page": p["page"],
            "clicks": p["clicks"],
            "impressions": p["impressions"],
            "ctr": p["ctr"],
            "position": p["position"],
        }
        for p in pages
    ]
    if dry_run:
        print(f"[gsc] would upsert {len(rows)} rows")
        return rows
    supabase_upsert("gsc_page_stats", rows)
    return rows


def main():
    parser = argparse.ArgumentParser(description="Pull page-level GSC stats")
    parser.add_argument("--days", type=int, default=28, help="Days to aggregate")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--property", choices=list(GSC_SITE_URLS.keys()), help="Sync one property")
    args = parser.parse_args()

    load_env()
    creds = gsc_service_account_credentials()
    if not creds:
        print("[gsc] GSC_SERVICE_ACCOUNT_JSON not set; skipping")
        return

    properties = [args.property] if args.property else list(GSC_SITE_URLS.keys())
    for prop in properties:
        sync_property(prop, creds, args.days, args.dry_run)


if __name__ == "__main__":
    main()
