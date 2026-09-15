"""
Fetch SEO news from RSS feeds.
Handles parsing, deduplication, and basic relevance scoring.
"""

import feedparser
import yaml
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from typing import List, Dict
import hashlib
import re
import json
import requests
from difflib import SequenceMatcher


def load_config(path: str = "config.yaml") -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalize_title(title: str) -> str:
    """Normalize title for fuzzy deduplication."""
    title = title.lower()
    title = re.sub(r'[^\w\s]', '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    return title


def title_similarity(a: str, b: str) -> float:
    """Check if two titles are ~the same story."""
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


def fetch_google_status() -> List[Dict]:
    """Fetch Google Search Status Dashboard incidents."""
    try:
        resp = requests.get(
            "https://status.search.google.com/incidents.json",
            timeout=15,
            headers={"User-Agent": "SEO-Digest-Bot/1.0"}
        )
        resp.raise_for_status()
        data = resp.json()
        
        articles = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        
        for incident in data:
            # Parse dates
            begin_str = incident.get("begin", incident.get("created", ""))
            if not begin_str:
                continue
            
            try:
                begin = datetime.fromisoformat(begin_str.replace("Z", "+00:00"))
            except ValueError:
                continue
            
            if begin < cutoff:
                continue
            
            title = incident.get("external_desc", "Google Search Incident")
            latest = incident.get("most_recent_update", {})
            text = latest.get("text", "")
            service = incident.get("service_name", "Search")
            status = latest.get("status", "UNKNOWN")
            
            # Build a meaningful title
            status_emoji = "🔴" if status in ["SERVICE_DISRUPTION", "OUTAGE"] else "🟡" if status == "SERVICE_INFORMATION" else "🟢"
            full_title = f"{status_emoji} [{service}] {title}"
            
            article = {
                "title": full_title,
                "link": "https://status.search.google.com/",
                "summary": text,
                "published": begin.isoformat(),
                "source": "Google Search Status",
                "author": "Google",
                "source_type": "status",
                "hash": hashlib.md5(f"{full_title}{begin.isoformat()}".encode()).hexdigest()[:12],
            }
            articles.append(article)
        
        return articles
    except Exception as e:
        print(f"  ⚠️  Failed to fetch Google Status: {e}")
        return []


def fetch_feed(url: str, name: str, max_articles: int = 5, source_type: str = "blog") -> List[Dict]:
    """Fetch and parse a single RSS feed."""
    try:
        feed = feedparser.parse(url)
        articles = []
        
        for entry in feed.entries[:max_articles]:
            # Parse published date
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                published = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
            else:
                published = datetime.now(timezone.utc)
            
            # Social posts: only keep last 24h (fresher)
            if source_type == "social":
                cutoff = datetime.now(timezone.utc) - timedelta(days=1)
            else:
                cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            
            if published < cutoff:
                continue
            
            # Extract title — social feeds sometimes have weird formatting
            title = getattr(entry, "title", "")
            if not title:
                # For Reddit, use the entry title directly
                title = getattr(entry, "title", "Untitled")
            
            # Clean up Twitter RSSHub titles (they prefix with "RT @user: ")
            if source_type == "social" and name.startswith("Twitter"):
                title = re.sub(r'^RT\s+@[\w_]+:\s*', '', title)
            
            # Extract summary/description
            summary = getattr(entry, "summary", getattr(entry, "description", ""))
            if not summary and source_type == "social":
                summary = title  # For tweets, the title IS the content
            
            article = {
                "title": title,
                "link": getattr(entry, "link", ""),
                "summary": summary,
                "published": published.isoformat(),
                "source": name,
                "author": getattr(entry, "author", name),
                "source_type": source_type,
            }
            
            # Create unique hash for deduplication
            article["hash"] = hashlib.md5(
                f"{article['title']}{article['link']}".encode()
            ).hexdigest()[:12]
            
            articles.append(article)
        
        return articles
    except Exception as e:
        print(f"  ⚠️  Failed to fetch {name}: {e}")
        return []


def score_relevance(article: Dict, keywords: List[str]) -> int:
    """Score article relevance based on keyword matches in title + summary."""
    text = f"{article['title']} {article['summary']}".lower()
    score = 0
    matched = []
    
    for kw in keywords:
        if kw.lower() in text:
            score += 1
            matched.append(kw)
    
    return score, matched


def fetch_all_news(config: Dict) -> List[Dict]:
    """Fetch news from all configured sources with fuzzy deduplication."""
    sources = config.get("sources", [])
    keywords = config.get("relevance_keywords", [])
    max_per_source = config.get("articles_per_source", 5)
    
    all_articles = []
    seen_hashes = set()
    seen_titles = []  # For fuzzy deduplication
    
    print(f"📡 Fetching from {len(sources)} sources...")
    
    for source in sources:
        name = source["name"]
        url = source["url"]
        priority = source.get("priority", "medium")
        source_type = source.get("type", "blog")
        
        print(f"  → {name}...", end=" ")
        
        source_limit = source.get("limit", max_per_source)
        
        if source_type == "status":
            articles = fetch_google_status()
        else:
            articles = fetch_feed(url, name, source_limit, source_type)
        
        print(f"{len(articles)} articles")
        
        for article in articles:
            # Exact deduplication by hash
            if article["hash"] in seen_hashes:
                continue
            
            # Fuzzy deduplication: skip if very similar to a known article
            is_duplicate = False
            for existing_title in seen_titles:
                if title_similarity(article["title"], existing_title) > 0.82:
                    is_duplicate = True
                    break
            
            if is_duplicate:
                continue
            
            seen_hashes.add(article["hash"])
            seen_titles.append(article["title"])
            
            # Score relevance
            score, matched = score_relevance(article, keywords)
            
            # Boost scores for featured sources
            if "Search Engine Journal" in name:
                score += 2  # Featured source — higher visibility
            
            # Boost scores for high-priority social accounts
            if source_type == "social":
                if "John Mueller" in name or "Search Liaison" in name:
                    score += 3  # Google's own voices = high signal
                elif "Barry Schwartz" in name:
                    score += 2  # Breaking news source
                elif "Danny Sullivan" in name:
                    score += 2
            
            article["relevance_score"] = score
            article["matched_keywords"] = matched
            article["priority"] = priority
            
            all_articles.append(article)
    
    # Sort by relevance score (desc), then by date (desc)
    all_articles.sort(key=lambda x: (-x["relevance_score"], x["published"]), reverse=False)
    
    print(f"\n✅ Total unique articles: {len(all_articles)}")
    return all_articles


if __name__ == "__main__":
    config = load_config()
    articles = fetch_all_news(config)
    
    # Show top 5 most relevant
    print("\n🏆 Top 5 most relevant articles:")
    for a in articles[:5]:
        print(f"  [{a['relevance_score']}] {a['title'][:70]}... ({a['source']})")
