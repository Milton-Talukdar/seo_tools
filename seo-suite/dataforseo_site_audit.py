#!/usr/bin/env python3
"""
dataforseo_site_audit.py — DataForSEO OnPage API provider for Orbit site health.

Uses the Basic crawl tier ($0.00015/page) to fetch technical SEO issues and
maps them into the existing site_audit_pages / site_audit_issues tables so the
dashboard can consume them without changes.

Reads: DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD from env.
Writes: site_audit_runs, site_audit_pages, site_audit_issues via save() in site_audit.py.
"""
import time
from datetime import date
from typing import List, Tuple
from urllib.parse import urlparse

from common import dfs_post

# ------------------------------------------------------------------------- config
MAX_CRAWL_PAGES = 2000
POLL_INTERVAL_SECONDS = 15
MAX_POLL_MINUTES = 30

ENDPOINTS = {
    "task_post": "/on_page/task_post",
    "summary": "/on_page/summary",
    "pages": "/on_page/pages",
    "duplicate_tags": "/on_page/duplicate_tags",
    "non_indexable": "/on_page/non_indexable",
    "redirect_chains": "/on_page/redirect_chains",
    "links": "/on_page/links",
}

ISSUE_SEVERITY = {
    "status_4xx": "critical",
    "status_5xx": "critical",
    "redirect_chain": "warning",
    "redirect_loop": "critical",
    "blocked_by_robots_txt": "warning",
    "noindex_robots_meta": "info",
    "x_robots_noindex": "info",
    "missing_canonical": "warning",
    "canonical_mismatch": "warning",
    "canonical_to_non_200": "warning",
    "canonicalized_to_redirect": "warning",
    "canonical_chain": "warning",
    "hreflang_missing_self_reference": "warning",
    "hreflang_missing_return_tag": "warning",
    "hreflang_non_200": "critical",
    "hreflang_invalid_code": "warning",
    "missing_title": "critical",
    "title_too_long": "warning",
    "missing_meta_description": "warning",
    "meta_description_too_long": "info",
    "missing_h1": "critical",
    "multiple_h1": "warning",
    "missing_viewport": "warning",
    "thin_content": "info",
    "missing_alt_text": "warning",
    "mixed_content": "warning",
    "missing_structured_data": "info",
    "duplicate_title": "warning",
    "duplicate_meta_description": "warning",
    "duplicate_h1": "warning",
    "internal_link_4xx": "critical",
    "internal_link_redirect": "info",
    "slow_lcp": "warning",
    "poor_cls": "warning",
    "orphan_page": "warning",
    "render_blocking_resources": "info",
}


# ----------------------------------------------------------------------- helpers
def today() -> str:
    return date.today().isoformat()


def _first_result(response: list):
    """Extract result[0] from a DataForSEO task response."""
    if not response:
        return {}
    if isinstance(response, list):
        return response[0] if response else {}
    return response


def _items(response: list):
    """Return items list from a DataForSEO result."""
    result = _first_result(response)
    return result.get("items") or []


def _domain_from_url(url: str) -> str:
    return urlparse(url).netloc.lower().lstrip("www.")


# ------------------------------------------------------------------------- tasks
def post_task(domain: str, custom_sitemap: str = "", max_pages: int = MAX_CRAWL_PAGES) -> str:
    """Post an OnPage crawl task. Returns task id."""
    payload = {
        "target": _domain_from_url(domain) or domain,
        "max_crawl_pages": max_pages,
        "tag": f"orbit-{domain}-{today()}",
    }
    if custom_sitemap:
        payload["respect_sitemap"] = True
        payload["crawl_sitemap_only"] = True
        payload["custom_sitemap"] = custom_sitemap

    task = dfs_post(ENDPOINTS["task_post"], [payload], full_task=True)
    task_id = task.get("id")
    if not task_id:
        raise RuntimeError(f"DataForSEO task_post did not return an id: {task}")
    return task_id


def poll_summary(task_id: str) -> dict:
    """Poll /on_page/summary until crawl_progress is finished."""
    deadline = time.time() + MAX_POLL_MINUTES * 60
    while time.time() < deadline:
        try:
            result = dfs_post(ENDPOINTS["summary"], [{"id": task_id}], timeout=60)
        except RuntimeError as e:
            # Task can sit in queue for a short while before it is accepted.
            msg = str(e)
            if "40602" in msg or "Task In Queue" in msg:
                print("  DataForSEO crawl progress: in queue")
                time.sleep(POLL_INTERVAL_SECONDS)
                continue
            raise
        summary = _first_result(result)
        progress = summary.get("crawl_progress", "")
        if progress == "finished":
            return summary
        if progress == "":
            # Task may not have started yet; keep polling
            pass
        print(f"  DataForSEO crawl progress: {progress or 'starting'} "
              f"(crawled {summary.get('crawl_status', {}).get('pages_crawled', 0)})")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise RuntimeError(f"DataForSEO crawl did not finish within {MAX_POLL_MINUTES} minutes")


# ----------------------------------------------------------------------- fetchers
def fetch_all_pages(task_id: str) -> List[dict]:
    """Paginate /on_page/pages and return all HTML page items."""
    pages = []
    offset = 0
    limit = 1000
    while True:
        result = dfs_post(ENDPOINTS["pages"], [{
            "id": task_id,
            "limit": limit,
            "offset": offset,
            "filters": [["resource_type", "=", "html"]],
        }], timeout=120)
        summary = _first_result(result)
        items = summary.get("items") or []
        pages.extend(items)
        total = summary.get("total_items_count") or 0
        offset += len(items)
        print(f"  fetched {len(items)} pages (total {offset}/{total})")
        if not items or offset >= total:
            break
    return pages


def fetch_duplicate_tags(task_id: str) -> Tuple[List[dict], List[dict]]:
    """Return (duplicate_titles, duplicate_descriptions)."""
    titles, descriptions = [], []
    for tag_type, out_list in (("duplicate_title", titles), ("duplicate_description", descriptions)):
        result = dfs_post(ENDPOINTS["duplicate_tags"], [{
            "id": task_id,
            "type": tag_type,
            "limit": 1000,
        }], timeout=120)
        out_list.extend(_items(result))
    return titles, descriptions


def fetch_non_indexable(task_id: str) -> List[dict]:
    result = dfs_post(ENDPOINTS["non_indexable"], [{
        "id": task_id,
        "limit": 1000,
    }], timeout=120)
    return _items(result)


def fetch_redirect_chains(task_id: str) -> List[dict]:
    result = dfs_post(ENDPOINTS["redirect_chains"], [{
        "id": task_id,
        "limit": 1000,
    }], timeout=120)
    return _items(result)


def fetch_links(task_id: str) -> List[dict]:
    """Fetch all internal links and flag broken (4xx/5xx) or redirect (3xx) targets."""
    issues = []
    offset = 0
    limit = 1000
    while True:
        result = dfs_post(ENDPOINTS["links"], [{
            "id": task_id,
            "limit": limit,
            "offset": offset,
            "filters": [
                ["direction", "=", "internal"],
            ],
        }], timeout=120)
        summary = _first_result(result)
        items = summary.get("items") or []
        for it in items:
            sc = it.get("page_to_status_code")
            if sc is None:
                continue
            if 400 <= sc < 600:
                issues.append({**it, "_broken": True})
            elif 300 <= sc < 400:
                issues.append({**it, "_broken": False})
        total = summary.get("total_items_count") or 0
        offset += len(items)
        print(f"  scanned {len(items)} internal links (total {offset}/{total})")
        if not items or offset >= total:
            break
    return issues


def _norm(url: str) -> str:
    return url.split("#")[0].rstrip("/")


def fetch_hreflang_issues(task_id: str) -> List[dict]:
    """Return hreflang issues from alternate links (invalid codes, non-200 targets,
    missing self-reference, missing return tags)."""
    alternates = []
    offset = 0
    limit = 1000
    while True:
        result = dfs_post(ENDPOINTS["links"], [{
            "id": task_id,
            "limit": limit,
            "offset": offset,
            "filters": [
                ["type", "=", "alternate"],
            ],
        }], timeout=120)
        summary = _first_result(result)
        items = summary.get("items") or []
        alternates.extend(items)
        total = summary.get("total_items_count") or 0
        offset += len(items)
        print(f"  scanned {len(items)} alternate links (total {offset}/{total})")
        if not items or offset >= total:
            break

    issues = []
    graph = {}  # source_norm -> {target_norm: code}
    self_refs = {}  # source_norm -> bool
    for it in alternates:
        source = it.get("link_from", "") or it.get("page_from", "")
        target = it.get("link_to", "") or it.get("page_to", "")
        code = it.get("hreflang", "")
        source_norm = _norm(source)
        target_norm = _norm(target)
        if not source or not target:
            continue

        if not it.get("is_valid_hreflang"):
            issues.append({
                "url": source,
                "type": "hreflang_invalid_code",
                "severity": ISSUE_SEVERITY["hreflang_invalid_code"],
                "details": f"{code} → {target}",
            })

        sc = it.get("page_to_status_code")
        if sc is not None and sc >= 400:
            issues.append({
                "url": source,
                "type": "hreflang_non_200",
                "severity": ISSUE_SEVERITY["hreflang_non_200"],
                "details": f"{code} → {target} (HTTP {sc})",
            })
        elif it.get("is_broken"):
            issues.append({
                "url": source,
                "type": "hreflang_non_200",
                "severity": ISSUE_SEVERITY["hreflang_non_200"],
                "details": f"{code} → {target} (broken)",
            })

        graph.setdefault(source_norm, {})[target_norm] = code
        if source_norm == target_norm:
            self_refs[source_norm] = True

    # missing self-reference and return-tag checks
    for source_norm, targets in graph.items():
        if not self_refs.get(source_norm):
            issues.append({
                "url": source_norm,
                "type": "hreflang_missing_self_reference",
                "severity": ISSUE_SEVERITY["hreflang_missing_self_reference"],
                "details": "",
            })
        for target_norm, code in targets.items():
            if target_norm == source_norm:
                continue
            if target_norm not in graph:
                # target is outside the crawled alternate-link graph; skip return-tag check
                continue
            back_links = graph.get(target_norm, {})
            if source_norm not in back_links:
                issues.append({
                    "url": source_norm,
                    "type": "hreflang_missing_return_tag",
                    "severity": ISSUE_SEVERITY["hreflang_missing_return_tag"],
                    "details": f"{code} → {target_norm}",
                })

    return issues


# --------------------------------------------------------------------- transform
def _page_row(item: dict) -> dict:
    meta = item.get("meta") or {}
    content = meta.get("content") or {}
    checks = item.get("checks") or {}
    htags = meta.get("htags") or {}
    h1s = htags.get("h1") or []

    return {
        "url": item.get("url", ""),
        "status_code": item.get("status_code") or 0,
        "final_url": item.get("location") or item.get("url", ""),
        "title": meta.get("title") or "",
        "meta_description": meta.get("description") or "",
        "h1": h1s[0] if h1s else "",
        "canonical": meta.get("canonical") or "",
        "canonical_ok": 1 if checks.get("canonical") else 0,
        "word_count": content.get("plain_text_word_count") or 0,
        "internal_links": meta.get("internal_links_count") or 0,
        "external_links": meta.get("external_links_count") or 0,
        "has_viewport": 0,  # not directly exposed by DataForSEO in Basic mode
        "redirect_count": 0,
        "lcp": None,
        "inp": None,
        "cls": None,
        "performance_score": None,
        "seo_score": None,
        "psi_status": "dataforseo",
        "fetch_error": "",
        "inlinks": None,
        "outlinks": None,
        "response_time_ms": None,
        "structured_data_types": None,
        "lighthouse_performance": None,
    }


def _page_issues(item: dict) -> List[dict]:
    """Map a single DataForSEO page item into Orbit issue dicts."""
    url = item.get("url", "")
    checks = item.get("checks") or {}
    meta = item.get("meta") or {}
    htags = meta.get("htags") or {}
    h1s = htags.get("h1") or []
    issues = []

    def add(itype: str, details: str = ""):
        issues.append({
            "url": url,
            "type": itype,
            "severity": ISSUE_SEVERITY.get(itype, "info"),
            "details": details,
        })

    status = item.get("status_code") or 0
    if status >= 500:
        add("status_5xx", f"HTTP {status}")
    elif status >= 400:
        add("status_4xx", f"HTTP {status}")
    elif checks.get("is_broken"):
        add("status_4xx", f"HTTP {status}")

    if checks.get("redirect_chain"):
        add("redirect_chain", f"HTTP {status}")
    if checks.get("is_redirect") and not checks.get("redirect_chain"):
        add("redirect_chain", item.get("location") or "")

    if not checks.get("canonical"):
        if meta.get("canonical"):
            add("canonical_mismatch", f"canonical={meta.get('canonical')}")
        else:
            add("missing_canonical")
    if checks.get("canonical_to_broken"):
        add("canonical_to_non_200", f"canonical={meta.get('canonical')}")
    if checks.get("canonical_to_redirect"):
        add("canonicalized_to_redirect", f"canonical={meta.get('canonical')}")
    if checks.get("canonical_chain"):
        add("canonical_chain", f"canonical={meta.get('canonical')}")

    if checks.get("no_title") or not meta.get("title"):
        add("missing_title")
    if checks.get("title_too_long"):
        add("title_too_long", f"{meta.get('title_length', 0)} chars")

    if checks.get("no_description") or not meta.get("description"):
        add("missing_meta_description")
    desc_len = meta.get("description_length") or len(meta.get("description") or "")
    if desc_len > 160:
        add("meta_description_too_long", f"{desc_len} chars")

    if checks.get("no_h1_tag") or not h1s:
        add("missing_h1")
    elif len(h1s) > 1:
        add("multiple_h1", f"{len(h1s)} H1s")

    if checks.get("no_image_alt"):
        add("missing_alt_text", f"{meta.get('images_count', 0)} images")

    if checks.get("https_to_http_links"):
        add("mixed_content")

    if checks.get("low_content_rate") or checks.get("low_character_count"):
        word_count = (meta.get("content") or {}).get("plain_text_word_count", 0)
        add("thin_content", f"{word_count} words")

    if checks.get("is_orphan_page"):
        add("orphan_page")

    if checks.get("has_links_to_redirects"):
        add("internal_link_redirect")

    if checks.get("has_render_blocking_resources"):
        add("render_blocking_resources")

    return issues


def _cross_page_issues(
    duplicate_titles: List[dict],
    duplicate_descriptions: List[dict],
    non_indexable: List[dict],
    redirect_chains: List[dict],
    link_issues: List[dict],
) -> List[dict]:
    """Map DataForSEO cross-page endpoints into Orbit issue dicts."""
    issues = []

    for item in duplicate_titles:
        for url in _urls_from_duplicate_item(item):
            issues.append({
                "url": url,
                "type": "duplicate_title",
                "severity": ISSUE_SEVERITY["duplicate_title"],
                "details": "",
            })

    for item in duplicate_descriptions:
        for url in _urls_from_duplicate_item(item):
            issues.append({
                "url": url,
                "type": "duplicate_meta_description",
                "severity": ISSUE_SEVERITY["duplicate_meta_description"],
                "details": "",
            })

    reason_map = {
        "robots_txt": "blocked_by_robots_txt",
        "meta_tag": "noindex_robots_meta",
        "http_header": "x_robots_noindex",
        "too_many_redirects": "redirect_loop",
    }
    for item in non_indexable:
        reason = item.get("reason", "")
        itype = reason_map.get(reason)
        if itype:
            issues.append({
                "url": item.get("url", ""),
                "type": itype,
                "severity": ISSUE_SEVERITY.get(itype, "info"),
                "details": reason,
            })

    for item in redirect_chains:
        urls = item.get("urls") or []
        if urls and urls[0] == urls[-1]:
            itype = "redirect_loop"
        else:
            itype = "redirect_chain"
        for url in urls[:1]:
            issues.append({
                "url": url,
                "type": itype,
                "severity": ISSUE_SEVERITY[itype],
                "details": " → ".join(urls),
            })

    for item in link_issues:
        source = item.get("link_from", "") or item.get("page_from", "")
        target = item.get("link_to", "") or item.get("page_to", "")
        sc = item.get("page_to_status_code") or 0
        if item.get("_broken"):
            itype = "internal_link_4xx"
            details = f"{target} (HTTP {sc})"
        else:
            itype = "internal_link_redirect"
            details = f"{target} → HTTP {sc}"
        issues.append({
            "url": source,
            "type": itype,
            "severity": ISSUE_SEVERITY[itype],
            "details": details,
        })

    return issues


def _urls_from_duplicate_item(item: dict) -> List[str]:
    """Extract URLs from a duplicate_tags item (handles common response shapes)."""
    if "pages" in item and isinstance(item["pages"], list):
        return [p.get("url", "") for p in item["pages"] if p.get("url")]
    if "urls" in item and isinstance(item["urls"], list):
        return [u for u in item["urls"] if u]
    url = item.get("url", "")
    return [url] if url else []


# --------------------------------------------------------------------------- run
def transform_to_orbit(
    summary: dict,
    pages: List[dict],
    duplicate_titles: List[dict],
    duplicate_descriptions: List[dict],
    non_indexable: List[dict],
    redirect_chains: List[dict],
    link_issues: List[dict],
    hreflang_issues: List[dict],
    property: str,
    day: str,
    duration: int = 0,
) -> Tuple[dict, List[dict], List[dict]]:
    """Convert DataForSEO responses into Orbit run/page/issue rows."""
    crawl_status = summary.get("crawl_status") or {}
    pages_crawled = crawl_status.get("pages_crawled") or len(pages)
    pages_failed = sum(1 for p in pages if (p.get("status_code") or 0) >= 400)

    page_rows = [_page_row(p) for p in pages]

    issues = []
    for p in pages:
        issues.extend(_page_issues(p))
    issues.extend(_cross_page_issues(
        duplicate_titles, duplicate_descriptions, non_indexable,
        redirect_chains, link_issues,
    ))
    issues.extend(hreflang_issues)

    run_row = {
        "day": day,
        "property": property,
        "pages_crawled": pages_crawled,
        "pages_failed": pages_failed,
        "issues_found": len(issues),
        "psi_calls": 0,
        "run_duration_seconds": duration,
        "crawl_source": "dataforseo",
    }
    return run_row, page_rows, issues


def run_for_property(property: str, sitemaps: list, limit: int = 0) -> Tuple[dict, List[dict], List[dict]]:
    """Run a DataForSEO OnPage audit for one property.

    `sitemaps` is the same list of (property, page_type, sitemap_url, pattern)
    tuples used by the custom crawler; we use the first sitemap URL as the
    custom sitemap if available.
    """
    from site_audit import PROPERTIES

    start_time = time.time()
    domain = PROPERTIES.get(property, {}).get("domain", property)
    custom_sitemap = ""
    if sitemaps:
        _, _, custom_sitemap, _ = sitemaps[0]

    max_pages = limit or MAX_CRAWL_PAGES

    print(f"[{property}] posting DataForSEO task for {domain} (max {max_pages} pages)")
    task_id = post_task(domain, custom_sitemap=custom_sitemap, max_pages=max_pages)
    print(f"[{property}] task id: {task_id}")

    print(f"[{property}] polling crawl summary...")
    summary = poll_summary(task_id)
    crawl_status = summary.get("crawl_status") or {}
    print(f"[{property}] crawl finished: {crawl_status.get('pages_crawled', 0)} pages")

    print(f"[{property}] fetching pages...")
    pages = fetch_all_pages(task_id)

    print(f"[{property}] fetching duplicate tags...")
    duplicate_titles, duplicate_descriptions = fetch_duplicate_tags(task_id)

    print(f"[{property}] fetching non-indexable pages...")
    non_indexable = fetch_non_indexable(task_id)

    print(f"[{property}] fetching redirect chains...")
    redirect_chains = fetch_redirect_chains(task_id)

    print(f"[{property}] fetching link issues...")
    link_issues = fetch_links(task_id)

    print(f"[{property}] fetching hreflang issues...")
    hreflang_issues = fetch_hreflang_issues(task_id)

    duration = int(time.time() - start_time)
    return transform_to_orbit(
        summary, pages, duplicate_titles, duplicate_descriptions,
        non_indexable, redirect_chains, link_issues, hreflang_issues,
        property, today(), duration=duration,
    )
