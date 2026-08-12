#!/usr/bin/env python3
"""
migrate_to_supabase.py — one-time migration from local SQLite to Supabase.

Prerequisites:
1. Run supabase_schema.sql in Supabase Dashboard → SQL Editor
2. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY as environment variables
   or in seo-suite/.env

Usage:
    python3 migrate_to_supabase.py --dry-run   # preview counts, no writes
    python3 migrate_to_supabase.py             # migrate all tables
    python3 migrate_to_supabase.py --table freshness_scores  # migrate one table
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

from supabase import create_client

from common import DB_PATH, load_env

HERE = Path(__file__).parent
ENV_PATH = HERE / ".env"

# Map SQLite table names to column lists for explicit ordering
TABLES = {
    "rank_snapshots": ["day", "keyword", "property", "position", "url", "serp_features"],
    "keyword_meta": ["property", "keyword", "tag", "volume", "kd", "cpc", "intent",
                     "branded", "serp_features", "traffic_prev", "traffic_cur"],
    "backlink_snapshots": ["day", "backlinks", "refdomains", "rank"],
    "refdomain_events": ["day", "event", "domain", "rank"],
    "llm_snapshots": ["day", "platform", "prompt", "mentions", "cited_mine", "links", "answer"],
    "volumes": ["day", "keyword", "ai_search_volume", "trend_json"],
    "discovered": ["query", "platform", "ai_search_volume", "seed", "first_seen", "last_seen"],
    "silent": ["day", "query", "platform", "ai_search_volume"],
    "keyword_research": ["seed", "source", "keyword", "volume", "kd", "cpc",
                         "competition", "intent", "serp_features", "parent_topic", "fetched"],
    "seed_overview": ["seed", "volume", "kd", "cpc", "competition", "intent",
                      "serp_features", "fetched"],
    "competitor_pages": ["property", "competitor", "domain", "url", "last_seen",
                         "title", "meta", "h1", "schemas", "word_count",
                         "content_hash", "first_seen"],
    "competitor_changes": ["id", "timestamp", "property", "competitor", "domain",
                           "url", "change_type", "title", "details_json"],
    "competitor_snapshots": ["day", "property", "competitor", "domain", "total_urls",
                             "last_crawl", "last_successful_crawl", "pages_hashed", "hash_failures"],
    "freshness_scores": ["day", "url", "property", "page_type", "title", "h1",
                         "published_date", "modified_date", "age_days", "word_count",
                         "internal_links", "external_links", "schema_types", "status_code",
                         "canonical", "freshness_score", "depth_score", "decay_risk",
                         "target_keyword", "position", "volume", "rank_drop_30d",
                         "rank_drop_60d", "rank_drop_90d", "traffic_28d", "traffic_prev_28d",
                         "traffic_drop_pct", "decay_score", "priority_score", "action",
                         "reason", "last_crawled"],
}

BATCH_SIZE = 500


def load_credentials():
    load_env()  # from common.py: reads .env and sets os.environ
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.")
        print("Add them to seo-suite/.env or set as environment variables.")
        sys.exit(1)
    return url, key


def sqlite_rows(con, table, columns):
    cur = con.execute(f"SELECT {','.join(columns)} FROM {table}")
    rows = cur.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def clean_row(row):
    """Remove None values and convert dates/bytes for Supabase."""
    out = {}
    for k, v in row.items():
        if v is None:
            continue
        if isinstance(v, bytes):
            v = v.decode("utf-8", errors="ignore")
        out[k] = v
    return out


def migrate_table(supabase, con, table, dry_run=False):
    columns = TABLES[table]
    rows = sqlite_rows(con, table, columns)
    print(f"[{table}] {len(rows)} rows from SQLite")
    if dry_run:
        return
    if not rows:
        return

    cleaned = [clean_row(r) for r in rows]
    total = 0
    for i in range(0, len(cleaned), BATCH_SIZE):
        batch = cleaned[i:i + BATCH_SIZE]
        try:
            result = supabase.table(table).insert(batch).execute()
            total += len(batch)
            print(f"  inserted {total}/{len(cleaned)}")
        except Exception as e:
            print(f"  ERROR inserting batch {i}: {e}")
            raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--table", help="Migrate only this table")
    args = ap.parse_args()

    url, key = load_credentials()
    supabase = create_client(url, key)
    con = sqlite3.connect(DB_PATH)

    tables = [args.table] if args.table else list(TABLES.keys())
    if args.table and args.table not in TABLES:
        print(f"Unknown table: {args.table}")
        sys.exit(1)

    for table in tables:
        migrate_table(supabase, con, table, dry_run=args.dry_run)

    con.close()
    print("\nMigration complete." if not args.dry_run else "\nDry run complete.")


if __name__ == "__main__":
    main()
