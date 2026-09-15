"""
Generate a daily SEO digest report in Markdown format.
Categorizes articles into Action Required, Watch, Learn, and FYI.
"""

import os
from datetime import datetime, timezone
from typing import List, Dict
import yaml

from ai_summarize import summarize_article


# Action trigger keywords — if these appear in title/summary, flag as actionable
ACTION_TRIGGERS = [
    "update", "rollout", "launch", "released", "announced", "confirmed",
    "algorithm", "core update", "penalty", "manual action", "deindex",
    "nofollow", "ranking factor", "confirmed ranking", "mobile-first",
    "core web vitals", "page experience", "crawl", "indexing issue",
    "bug", "fixed", "deprecated", "sunset", "shutting down",
    "new feature", "now available", "introducing", "changes to",
]

# Learning trigger keywords
LEARN_TRIGGERS = [
    "how to", "guide", "tutorial", "best practices", "study",
    "research", "analysis", "case study", "benchmark", "data",
    "strategies", "tips", "techniques", "framework", "methodology",
    "AI overview", "SGE", "search generative", "E-E-A-T",
]

# Watch trigger keywords
WATCH_TRIGGERS = [
    "testing", "experiment", "pilot", "beta", "rumored",
    "speculated", "might", "could", "may", "potential",
    "watch", "monitor", "track", "pay attention",
]


def categorize_article(article: Dict) -> str:
    """Categorize a single article based on keyword triggers."""
    text = f"{article['title']} {article['summary']}".lower()
    
    # Check action triggers
    for trigger in ACTION_TRIGGERS:
        if trigger in text:
            return "action"
    
    # Check watch triggers
    for trigger in WATCH_TRIGGERS:
        if trigger in text:
            return "watch"
    
    # Check learn triggers
    for trigger in LEARN_TRIGGERS:
        if trigger in text:
            return "learn"
    
    # High relevance score = action or watch
    if article.get("relevance_score", 0) >= 2:
        return "action"
    
    return "fyi"


def format_article(article: Dict, use_ai: bool = True) -> str:
    """Format a single article as markdown. Optionally uses AI-enhanced summaries."""
    title = article["title"]
    link = article["link"]
    source = article["source"]
    matched = article.get("matched_keywords", [])
    
    # Try AI summary first
    ai_summary = None
    if use_ai:
        ai_summary = summarize_article(article)
    
    lines = [f"**[{title}]({link})** — *{source}*"]
    
    if ai_summary:
        # AI-enhanced formatting
        lines.append(f"> **{ai_summary['headline']}**")
        lines.append(f"> {ai_summary['summary']}")
        if ai_summary.get("tags"):
            tags = " · ".join([f"`{t}`" for t in ai_summary["tags"]])
            lines.append(f"> {tags}")
    else:
        # Fallback to raw summary
        summary = article.get("summary", "")
        # Clean up summary (strip HTML tags if present)
        import re
        summary = re.sub(r"<[^>]+>", " ", summary)
        summary = summary[:280] + "..." if len(summary) > 280 else summary
        
        if summary.strip():
            lines.append(f"> {summary.strip()}")
        
        if matched:
            tags = " · ".join([f"`{k}`" for k in matched[:5]])
            lines.append(f"> {tags}")
    
    return "\n".join(lines)


def generate_report(articles: List[Dict], config: Dict) -> str:
    """Generate the full daily digest report."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Categorize all articles
    categorized = {"action": [], "watch": [], "learn": [], "fyi": []}
    for article in articles:
        cat = categorize_article(article)
        categorized[cat].append(article)
    
    # Sort each category: Search Engine Journal articles first, then by relevance
    for cat in categorized:
        categorized[cat].sort(
            key=lambda a: (
                0 if "Search Engine Journal" in a.get("source", "") else 1,
                -a.get("relevance_score", 0)
            )
        )
    
    report_cfg = config.get("report", {})
    max_headlines = report_cfg.get("max_headlines", 15)
    max_action = report_cfg.get("max_action_items", 8)
    max_learn = report_cfg.get("max_learn_items", 5)
    
    lines = [
        f"# Daily SEO Digest — {today}",
        "",
        f"> 📡 Sources: {len(config.get('sources', []))} | 📰 Articles: {len(articles)} | 🔴 Action: {len(categorized['action'])} | 🟡 Watch: {len(categorized['watch'])} | 🟢 Learn: {len(categorized['learn'])}",
        "",
        "---",
        "",
    ]
    
    # Section: Action Required
    if categorized["action"]:
        lines.extend([
            "## 🔴 Action Required",
            "",
            "These require immediate attention or implementation.",
            "",
        ])
        for article in categorized["action"][:max_action]:
            lines.append(format_article(article, use_ai=True))
            lines.append("")
        lines.append("---")
        lines.append("")
    
    # Section: Watch This Week
    if categorized["watch"]:
        lines.extend([
            "## 🟡 Watch This Week",
            "",
            "Monitor these developments — they may become actionable soon.",
            "",
        ])
        for article in categorized["watch"][:max_action]:
            lines.append(format_article(article, use_ai=True))
            lines.append("")
        lines.append("---")
        lines.append("")
    
    # Section: Learn
    if categorized["learn"]:
        lines.extend([
            "## 🟢 Learn",
            "",
            "New concepts, techniques, or studies worth your time.",
            "",
        ])
        for article in categorized["learn"][:max_learn]:
            lines.append(format_article(article, use_ai=True))
            lines.append("")
        lines.append("---")
        lines.append("")
    
    # Section: FYI Headlines
    if categorized["fyi"]:
        lines.extend([
            "## 📰 FYI Headlines",
            "",
            "Everything else, summarized.",
            "",
        ])
        for article in categorized["fyi"][:max_headlines]:
            title = article["title"]
            link = article["link"]
            source = article["source"]
            lines.append(f"- **[{title}]({link})** — *{source}*")
        lines.append("")
        lines.append("---")
        lines.append("")
    
    # Footer
    lines.extend([
        "## 📝 How to Use This Report",
        "",
        "1. **🔴 Action Required** — Read fully. Decide if it affects your current projects. Add to your task list.",
        "2. **🟡 Watch This Week** — Skim. Set a reminder to check back in 3-7 days.",
        "3. **🟢 Learn** — Bookmark for your next learning block. Prioritize based on current projects.",
        "4. **📰 FYI** — Scan headlines. Click only if relevant to your work.",
        "",
        "---",
        "",
        f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
    ])
    
    return "\n".join(lines)


def save_report(report_md: str, output_dir: str = "reports") -> str:
    """Save the report to disk."""
    os.makedirs(output_dir, exist_ok=True)
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"{today}.md"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report_md)
    
    return filepath


if __name__ == "__main__":
    import fetch_news
    
    config = fetch_news.load_config()
    articles = fetch_news.fetch_all_news(config)
    report_md = generate_report(articles, config)
    filepath = save_report(report_md)
    print(f"\n📝 Report saved: {filepath}")
