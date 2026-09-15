"""
Generate a weekly summary report from the past 7 days of daily digests.
Aggregates stats, top stories, and trending topics.
"""

import os
import re
from datetime import datetime, timezone, timedelta
from collections import Counter
from typing import List, Dict


def parse_report(filepath: str) -> Dict:
    """Parse a single daily report file."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    date_str = os.path.basename(filepath).replace(".md", "")

    # Find section positions
    action_pos = content.find("## 🔴 Action Required")
    watch_pos = content.find("## 🟡 Watch This Week")
    learn_pos = content.find("## 🟢 Learn")
    fyi_pos = content.find("## 📰 FYI Headlines")
    fyi_end = content.find("## 📝 How to Use This Report")
    if fyi_end == -1:
        fyi_end = len(content)

    # Extract all articles with their positions
    articles = []
    for match in re.finditer(r"\*\*\[(.*?)\]\((.*?)\)\*\* — \*(.*?)\*", content):
        title, link, source = match.groups()
        pos = match.start()

        # Determine category by position
        category = "fyi"
        if action_pos != -1 and watch_pos != -1 and action_pos < pos < watch_pos:
            category = "action"
        elif watch_pos != -1 and learn_pos != -1 and watch_pos < pos < learn_pos:
            category = "watch"
        elif learn_pos != -1 and fyi_pos != -1 and learn_pos < pos < fyi_pos:
            category = "learn"
        elif fyi_pos != -1 and fyi_pos < pos < fyi_end:
            category = "fyi"

        # Extract summary if present
        after = content[match.end():match.end()+500]
        summary_match = re.search(r"> (.*?)(?:\n|$)", after)
        summary = summary_match.group(1).strip() if summary_match else ""
        summary = re.sub(r'<[^>]+>', '', summary)[:200]

        articles.append({
            "title": title.strip(),
            "link": link.strip(),
            "source": source.strip(),
            "summary": summary,
            "category": category,
            "date": date_str,
        })

    # Count by category
    action_count = sum(1 for a in articles if a["category"] == "action")
    watch_count = sum(1 for a in articles if a["category"] == "watch")
    learn_count = sum(1 for a in articles if a["category"] == "learn")
    fyi_count = sum(1 for a in articles if a["category"] == "fyi")

    # Extract tags
    tags = re.findall(r"`([^`]+)`", content)

    return {
        "date": date_str,
        "action": action_count,
        "watch": watch_count,
        "learn": learn_count,
        "fyi": fyi_count,
        "articles": articles,
        "tags": tags,
    }


def generate_weekly_summary(reports_dir: str = "reports") -> str:
    """Generate weekly summary from reports in the last 7 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    reports = []

    if not os.path.exists(reports_dir):
        return "# Weekly Summary\n\n>No reports found."

    for filename in sorted(os.listdir(reports_dir)):
        if not filename.endswith(".md") or filename.startswith("weekly"):
            continue

        date_str = filename.replace(".md", "")
        try:
            report_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        if report_date >= cutoff:
            filepath = os.path.join(reports_dir, filename)
            reports.append(parse_report(filepath))

    if not reports:
        return "# Weekly Summary\n\n>No reports from the last 7 days."

    # Aggregate stats
    total_action = sum(r["action"] for r in reports)
    total_watch = sum(r["watch"] for r in reports)
    total_learn = sum(r["learn"] for r in reports)
    total_fyi = sum(r["fyi"] for r in reports)
    total_articles = total_action + total_watch + total_learn + total_fyi

    # Collect all articles
    all_articles = []
    for r in reports:
        all_articles.extend(r["articles"])

    # Top stories: prioritize SEJ, then by category importance
    def article_rank(a):
        cat_score = {"action": 4, "watch": 3, "learn": 2, "fyi": 1}
        sej_boost = 10 if "Search Engine Journal" in a["source"] else 0
        return cat_score.get(a["category"], 0) + sej_boost

    top_stories = sorted(all_articles, key=article_rank, reverse=True)[:8]

    # Trending topics
    all_tags = []
    for r in reports:
        all_tags.extend(r["tags"])
    trending = Counter(all_tags).most_common(8)

    # Source breakdown
    sources = Counter(a["source"] for a in all_articles).most_common(5)

    # Week range
    dates = [r["date"] for r in reports]
    week_start = min(dates)
    week_end = max(dates)
    week_num = datetime.strptime(week_end, "%Y-%m-%d").isocalendar()[1]
    year = datetime.strptime(week_end, "%Y-%m-%d").year

    # Generate markdown
    lines = [
        f"# Week {week_num}, {year} Summary",
        "",
        f"**{week_start} → {week_end}** · {len(reports)} report{'s' if len(reports) > 1 else ''} · {total_articles} articles",
        "",
        f"> 🔴 {total_action} Action · 🟡 {total_watch} Watch · 🟢 {total_learn} Learn · 📰 {total_fyi} FYI",
        "",
        "---",
        "",
        "## 🔥 Top Stories",
        "",
        "The most important articles from the week, ranked by impact.",
        "",
    ]

    for i, article in enumerate(top_stories, 1):
        cat_emoji = {"action": "🔴", "watch": "🟡", "learn": "🟢", "fyi": "📰"}.get(article["category"], "📰")
        lines.append(f"{i}. **[{article['title']}]({article['link']})** {cat_emoji}")
        lines.append(f"   — *{article['source']}* · {article['date']}")
        if article["summary"]:
            lines.append(f"   > {article['summary']}...")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 📊 Source Breakdown",
        "",
    ])
    for source, count in sources:
        lines.append(f"- **{source}**: {count} articles")
    lines.append("")

    if trending:
        lines.extend([
            "---",
            "",
            "## 🏷️ Trending Topics",
            "",
        ])
        tags_str = " · ".join([f"`{tag}` ({count})" for tag, count in trending])
        lines.append(tags_str)
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 📅 What to Watch Next Week",
        "",
        "Based on this week's signals:",
        "",
        "- Check back Tuesday for the next digest",
        "- Monitor any 🔴 Action items you haven't addressed yet",
        "- Review 🟡 Watch items for updates",
        "",
        f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
    ])

    return "\n".join(lines)


def save_weekly_summary(markdown: str, reports_dir: str = "reports") -> str:
    """Save weekly summary to disk."""
    os.makedirs(reports_dir, exist_ok=True)
    filepath = os.path.join(reports_dir, "weekly-latest.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(markdown)
    return filepath


if __name__ == "__main__":
    summary = generate_weekly_summary()
    filepath = save_weekly_summary(summary)
    print(f"\n📅 Weekly summary saved: {filepath}")
    print(f"\n{summary[:600]}...")
