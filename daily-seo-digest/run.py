#!/usr/bin/env python3
"""
Daily SEO News Digest — Main Runner

Usage:
    python run.py              # Run once, generate today's report
    python run.py --dry-run    # Fetch news but don't save report
    python run.py --open       # Open today's report after generating
"""

import argparse
import subprocess
import sys
import os

import fetch_news
import generate_report


def main():
    parser = argparse.ArgumentParser(description="Daily SEO News Digest")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but don't save")
    parser.add_argument("--open", action="store_true", help="Open report after generating (macOS)")
    args = parser.parse_args()
    
    print("=" * 60)
    print("📰 Daily SEO News Digest")
    print("=" * 60)
    print()
    
    # Load config
    config = fetch_news.load_config()
    
    # Fetch news
    articles = fetch_news.fetch_all_news(config)
    
    if not articles:
        print("\n⚠️  No articles found. Sources may be down or all articles are older than 7 days.")
        sys.exit(1)
    
    # Generate report
    print("\n📝 Generating report...")
    report_md = generate_report.generate_report(articles, config)
    
    if args.dry_run:
        print("\n--- DRY RUN ---")
        print(report_md[:2000])
        print("...\n[Report not saved]")
        return
    
    # Save report
    output_dir = config.get("report", {}).get("output_dir", "reports")
    filepath = generate_report.save_report(report_md, output_dir)
    print(f"✅ Report saved: {filepath}")
    
    # Stats
    from generate_report import categorize_article
    counts = {"action": 0, "watch": 0, "learn": 0, "fyi": 0}
    for a in articles:
        counts[categorize_article(a)] += 1
    
    print(f"\n📊 Summary:")
    print(f"   🔴 Action: {counts['action']}")
    print(f"   🟡 Watch:  {counts['watch']}")
    print(f"   🟢 Learn:  {counts['learn']}")
    print(f"   📰 FYI:    {counts['fyi']}")
    
    # Open report (macOS)
    if args.open and sys.platform == "darwin":
        subprocess.run(["open", filepath])
        print(f"\n📂 Opened: {filepath}")
    
    print("\n✨ Done!")


if __name__ == "__main__":
    main()
