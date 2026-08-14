#!/usr/bin/env python3
"""
Export key Supabase tables to Cloudflare R2 as dated JSON snapshots.
Designed to run from GitHub Actions on a monthly schedule.
"""
import json
import os
import sys
from datetime import datetime, timezone

import boto3
from botocore.config import Config
from supabase import create_client

TABLES = [
    "rank_snapshots",
    "backlink_snapshots",
    "llm_snapshots",
    "freshness_scores",
    "competitor_snapshots",
    "competitor_changes",
    "keyword_meta",
    "refdomain_events",
    "volumes",
    "discovered",
    "silent",
]

CHUNK_SIZE = 1000


def get_env(name):
    value = os.environ.get(name)
    if not value:
        print(f"Missing environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{get_env('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=get_env("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=get_env("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
        config=Config(retries={"max_attempts": 3}),
    )


def fetch_table(supabase, table):
    rows = []
    start = 0
    while True:
        page = (
            supabase.table(table)
            .select("*")
            .range(start, start + CHUNK_SIZE - 1)
            .execute()
            .data
        )
        if not page:
            break
        rows.extend(page)
        if len(page) < CHUNK_SIZE:
            break
        start += CHUNK_SIZE
    return rows


def main():
    supabase = create_client(get_env("SUPABASE_URL"), get_env("SUPABASE_SERVICE_ROLE_KEY"))
    s3 = r2_client()
    bucket = get_env("R2_BUCKET_NAME")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prefix = f"snapshots/{today}"

    total_rows = 0
    for table in TABLES:
        print(f"Snapshotting {table}...")
        rows = fetch_table(supabase, table)
        key = f"{prefix}/{table}.json"
        body = json.dumps(rows, default=str).encode("utf-8")
        s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")
        print(f"  -> {key} ({len(rows)} rows, {len(body)} bytes)")
        total_rows += len(rows)

    # Latest pointer for easy dashboard access
    manifest = {
        "date": today,
        "tables": TABLES,
        "total_rows": total_rows,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    s3.put_object(
        Bucket=bucket,
        Key="snapshots/latest.json",
        Body=json.dumps(manifest).encode("utf-8"),
        ContentType="application/json",
    )
    print(f"Manifest -> snapshots/latest.json")
    print(f"Done. Total rows exported: {total_rows}")


if __name__ == "__main__":
    main()
