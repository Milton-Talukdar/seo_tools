"""
AI-powered article summarization using Cloudflare Workers AI.
Caches results to avoid re-summarizing the same article.
"""

import os
import json
import hashlib
import re
from typing import Optional
import requests

# Cloudflare Workers AI config
CF_TOKEN = os.getenv("CLOUDFLARE_AI_TOKEN")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")

# Model selection:
# @cf/meta/llama-3.1-8b-instruct  -> fast, good quality, default
# @cf/meta/llama-3.3-70b-instruct -> slower, best quality
MODEL = "@cf/meta/llama-3.1-8b-instruct"

CACHE_PATH = "cache/summaries.json"


def _cache_key(article: dict) -> str:
    """Generate a stable cache key from article URL."""
    return hashlib.md5(article["link"].encode()).hexdigest()[:12]


def _load_cache() -> dict:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def _extract_json(text: str) -> Optional[dict]:
    """Extract JSON object from LLM response text."""
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


def summarize_article(article: dict) -> Optional[dict]:
    """
    Summarize a single article using Cloudflare Workers AI.
    Returns {"headline": str, "summary": str, "tags": list} or None.
    """
    cache = _load_cache()
    key = _cache_key(article)
    if key in cache:
        return cache[key]

    # Graceful fallback if credentials not configured
    if not CF_TOKEN or not CF_ACCOUNT_ID:
        return None

    url = (
        f"https://api.cloudflare.com/client/v4/accounts/"
        f"{CF_ACCOUNT_ID}/ai/run/{MODEL}"
    )

    system_prompt = (
        "You are a senior SEO strategist writing concise intelligence briefs "
        "for experienced SEO professionals. Be direct, specific, and actionable. "
        "Avoid generic phrases like 'in the world of SEO' or 'game-changing'. "
        "Focus on what practitioners should do differently based on this news."
    )

    # Truncate content to stay within token limits
    raw_content = article.get("summary", article.get("description", ""))
    raw_content = re.sub(r"<[^>]+>", "", raw_content)  # strip HTML
    content_snippet = raw_content[:1200].strip()

    user_prompt = f"""Article Title: {article['title']}
Source: {article.get('source', 'Unknown')}
Content Snippet: {content_snippet}

Respond ONLY with valid JSON in this exact format:
{{
  "headline": "One sentence explaining why this matters to SEOs",
  "summary": "Two sentences on the practical impact and what to do",
  "tags": ["Algorithm", "AI", "Content", "Technical", "Local", "Links", "Analytics", "Industry"]
}}"""

    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {CF_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 300,
                "temperature": 0.2,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()

        result_text = data.get("result", {}).get("response", "")
        parsed = _extract_json(result_text)

        if parsed and isinstance(parsed, dict):
            # Normalize tags to valid options
            valid_tags = {"Algorithm", "AI", "Content", "Technical", "Local", "Links", "Analytics", "Industry"}
            raw_tags = parsed.get("tags", [])
            parsed["tags"] = [t for t in raw_tags if t in valid_tags][:2]

            cache[key] = parsed
            _save_cache(cache)
            return parsed

    except Exception as e:
        print(f"⚠️  AI summary failed for {article['link'][:60]}...: {e}")

    return None


def batch_summarize(articles: list) -> dict:
    """
    Summarize multiple articles. Returns a dict mapping cache keys to summaries.
    Useful for pre-computing summaries before report generation.
    """
    results = {}
    for article in articles:
        summary = summarize_article(article)
        if summary:
            results[_cache_key(article)] = summary
    return results


if __name__ == "__main__":
    # Quick test
    test_article = {
        "title": "Google Confirms March 2024 Core Update Rolling Out",
        "link": "https://example.com/test",
        "source": "Search Engine Journal",
        "summary": "Google has confirmed that a new broad core algorithm update is now rolling out. The update is expected to take two weeks to complete. Site owners may see ranking fluctuations.",
    }
    result = summarize_article(test_article)
    print(json.dumps(result, indent=2) if result else "No result (check credentials)")
