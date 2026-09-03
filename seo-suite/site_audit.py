#!/usr/bin/env python3
"""
site_audit.py — Technical site health crawler + optional PageSpeed Insights.

Crawls the same sitemaps used by freshness.py, extracts on-page SEO signals,
and flags technical issues:
  - 4xx/5xx pages
  - Redirect chains
  - Missing or oversized title / meta description / H1
  - Canonical mismatches
  - Missing viewport tag
  - Internal links pointing to 4xx or redirect chains

Optionally calls the Google PageSpeed Insights API for Core Web Vitals
(LCP, INP, CLS) and Lighthouse scores on the most important pages.

Reads: freshness_sitemaps.csv
Writes: site_audit_runs, site_audit_pages, site_audit_issues in seo_suite.db

Usage:
    python3 site_audit.py --dry-run          # preview what would run; no network
    python3 site_audit.py --limit 10         # only audit 10 URLs per sitemap
    python3 site_audit.py --force            # run even if already ran this month
    python3 site_audit.py --property vc      # only one property
    python3 site_audit.py                    # monthly full run (self-throttled)
"""
import argparse
import csv
import gzip
import html
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from common import DB_PATH, init_db, load_env, supabase_upsert
import dataforseo_site_audit

HERE = Path(__file__).parent
CONFIG = HERE / "freshness_sitemaps.csv"

# ---- edit these ------------------------------------------------------------
MAX_PAGES_PER_SITEMAP = 500
REQUEST_TIMEOUT = 25
CRAWL_DELAY_SECONDS = 0.3
MIN_DAYS_BETWEEN_RUNS = 25          # monthly-ish gate
MAX_PSI_PAGES = 50                  # PSI has a free quota; audit top N pages only
MAX_REDIRECT_HOPS = 5
THIN_CONTENT_WORDS = 300
WORD_BLOCKLIST = {"script", "style", "nav", "header", "footer", "aside", "noscript"}
# -----------------------------------------------------------------------------

SELF_DOMAINS = {"vantagecircle.com", "www.vantagecircle.com",
                "vantagefit.io", "www.vantagefit.io"}

PROPERTIES = {
    "vantagecircle": {"label": "Vantage Circle", "domain": "vantagecircle.com"},
    "vantagefit": {"label": "Vantage Fit", "domain": "vantagefit.io"},
}

ISSUE_SEVERITY = {
    # status / crawl
    "status_4xx": "critical",
    "status_5xx": "critical",
    "redirect_chain": "warning",
    "redirect_loop": "critical",
    "blocked_by_robots_txt": "warning",
    "sitemap_fetch_error": "warning",

    # indexing
    "noindex_robots_meta": "info",
    "x_robots_noindex": "info",

    # canonical
    "missing_canonical": "warning",
    "canonical_mismatch": "warning",
    "canonical_to_non_200": "warning",
    "canonicalized_to_redirect": "warning",

    # hreflang
    "hreflang_missing_self_reference": "warning",
    "hreflang_missing_return_tag": "warning",
    "hreflang_non_200": "critical",
    "hreflang_invalid_code": "warning",

    # content / on-page
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

    # duplicates
    "duplicate_title": "warning",
    "duplicate_meta_description": "warning",
    "duplicate_h1": "warning",

    # links
    "internal_link_4xx": "critical",
    "internal_link_redirect": "info",

    # performance
    "slow_lcp": "warning",
    "poor_cls": "warning",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def today():
    return date.today().isoformat()


def normalize_url(url: str) -> str:
    return url.split("#")[0].rstrip("/")


def domain_from_url(url: str) -> str:
    return urlparse(url).netloc.lower().lstrip("www.")


def is_self_link(url: str) -> bool:
    netloc = urlparse(url).netloc.lower()
    if not netloc:
        return True
    return netloc in SELF_DOMAINS


def property_from_url(url: str) -> str:
    d = domain_from_url(url)
    if "vantagefit" in d:
        return "vfit"
    return "vc"


def fetch_redirect_chain(url: str, method: str = "HEAD"):
    """Manually follow redirects up to MAX_REDIRECT_HOPS. Returns dict with
    final_url, status, redirect_count, loop, chain."""
    chain = [url]
    current = url
    status = 0
    for _ in range(MAX_REDIRECT_HOPS):
        req = urllib.request.Request(
            current,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; VantageSEOSiteAuditBot/1.0; "
                    "+https://www.vantagecircle.com)"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                status = resp.status
                final_url = resp.geturl()
                if normalize_url(final_url) == normalize_url(current):
                    break
                if normalize_url(final_url) in [normalize_url(u) for u in chain]:
                    chain.append(final_url)
                    return {
                        "final_url": final_url,
                        "status": status,
                        "redirect_count": len(chain) - 1,
                        "loop": True,
                        "chain": chain,
                    }
                chain.append(final_url)
                current = final_url
        except urllib.error.HTTPError as e:
            status = e.code
            break
        except Exception:
            break
    return {
        "final_url": current,
        "status": status,
        "redirect_count": len(chain) - 1,
        "loop": False,
        "chain": chain,
    }


def parse_robots_txt(base_url: str):
    """Return RobotFileParser for the domain, or None on failure.
    Fetches robots.txt with our user-agent because Cloudflare blocks the
    default urllib UA, which would make RobotFileParser.read() silently fail."""
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    text, _, status, _ = fetch(robots_url)
    if status != 200 or not text:
        print(f"  robots.txt fetch failed: {robots_url} (HTTP {status})")
        return None
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.parse(text.splitlines())
        return rp
    except Exception as e:
        print(f"  robots.txt parse failed: {robots_url} ({e})")
        return None


def is_blocked_by_robots(rp: urllib.robotparser.RobotFileParser, url: str) -> bool:
    if not rp:
        return False
    try:
        return not rp.can_fetch("*", url)
    except Exception:
        return False


# Valid BCP-47-ish hreflang pattern: language[-script][-region]
# We allow x-default as a special case.
HREFLANG_RE = re.compile(r"^(x-default|[a-zA-Z]{2,3}(?:-[a-zA-Z]{4})?(?:-[a-zA-Z]{2}|\d{3})?)$")


def valid_hreflang_code(code: str) -> bool:
    return bool(HREFLANG_RE.match(code.strip()))


# --------------------------------------------------------------------------- fetch

def fetch(url: str, binary: bool = False, method: str = "GET"):
    """Fetch a URL. Returns (body_bytes_or_text, final_url, status, headers)."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; VantageSEOSiteAuditBot/1.0; "
                "+https://www.vantagecircle.com)"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read()
            final_url = resp.geturl()
            headers = dict(resp.headers)
            encoding = headers.get("Content-Encoding", "").lower()
            if encoding == "gzip":
                raw = gzip.decompress(raw)
            if binary:
                return raw, final_url, resp.status, headers
            text = raw.decode("utf-8", errors="replace")
            return text, final_url, resp.status, headers
    except urllib.error.HTTPError as e:
        return None, url, e.code, {}
    except Exception as e:
        return None, url, 0, {"error": str(e)}


# ----------------------------------------------------------------------- sitemaps

def parse_sitemap(url: str, limit: int = 0):
    """Return list of (url, lastmod) from a sitemap or sitemap index."""
    text, final_url, status, headers = fetch(url)
    if text is None:
        print(f"  sitemap fetch failed: {url} (status {status})")
        return []

    try:
        root = ET.fromstring(text.encode("utf-8", "ignore"))
    except ET.ParseError as e:
        print(f"  sitemap parse failed: {url} ({e})")
        return []

    ns = "http://www.sitemaps.org/schemas/sitemap/0.9"
    urls = []
    sitemaps = []
    for child in root:
        tag = child.tag.split("}")[-1]
        if tag == "url":
            loc = child.find(f"{{{ns}}}loc")
            lastmod = child.find(f"{{{ns}}}lastmod")
            if loc is not None and loc.text:
                urls.append((loc.text.strip(), lastmod.text.strip() if lastmod is not None and lastmod.text else None))
        elif tag == "sitemap":
            loc = child.find(f"{{{ns}}}loc")
            if loc is not None and loc.text:
                sitemaps.append(loc.text.strip())

    if sitemaps:
        result = []
        seen = set()
        for sm in sitemaps:
            if sm in seen:
                continue
            seen.add(sm)
            result.extend(parse_sitemap(sm, limit=limit))
            if limit and len(result) >= limit:
                break
        return result[:limit] if limit else result

    return urls[:limit] if limit else urls


def load_config():
    """[(property, page_type, sitemap_url, url_pattern), ...]"""
    rows = []
    if not CONFIG.exists():
        return rows
    for rec in csv.reader(open(CONFIG, encoding="utf-8")):
        if not rec or rec[0].strip().startswith("#"):
            continue
        rows.append((rec[0].strip(), rec[1].strip(), rec[2].strip(),
                     rec[3].strip() if len(rec) > 3 else ""))
    return rows


# ------------------------------------------------------------------ HTML parsing

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.text_parts = []
        self.links = []
        self.h1s = []
        self.title = None
        self.meta_desc = None
        self.canonical = None
        self.has_viewport = False
        self.robots_meta = None
        self.hreflangs = []          # list of (hreflang_code, href)
        self.images = []             # list of (src, alt)
        self.resource_urls = []      # list of (tag, src/href) for mixed-content check
        self.structured_data = []    # list of JSON-LD types found
        self.in_title = False
        self.in_head = True
        self.in_script_jsonld = False
        self.current_tag = None
        self.current_h1 = None
        self._jsonld_buffer = ""

    def handle_starttag(self, tag, attrs):
        self.current_tag = tag
        attr = dict(attrs)
        if tag in WORD_BLOCKLIST:
            self.skip += 1
        if self.in_head and tag == "title":
            self.in_title = True
        if self.in_head and tag == "link":
            rel = (attr.get("rel") or "").lower()
            if rel == "canonical":
                self.canonical = attr.get("href")
            if rel == "alternate" and attr.get("hreflang"):
                self.hreflangs.append((attr.get("hreflang").strip(), attr.get("href", "").strip()))
        if self.in_head and tag == "meta":
            name = (attr.get("name") or attr.get("property") or "").lower()
            if name in ("description", "og:description") and not self.meta_desc:
                self.meta_desc = attr.get("content")
            if name == "viewport":
                self.has_viewport = True
            if name == "robots" and attr.get("content"):
                self.robots_meta = (attr.get("content") or "").lower()
        if tag == "h1":
            self.current_h1 = ""
        if tag == "a" and attr.get("href"):
            href = attr.get("href")
            self.links.append(href)
        if tag == "img" and attr.get("src"):
            self.images.append((attr.get("src"), attr.get("alt", "")))
            self.resource_urls.append(("img", attr.get("src")))
        if tag == "script":
            src = attr.get("src")
            if src:
                self.resource_urls.append(("script", src))
            type_attr = (attr.get("type") or "").lower()
            if type_attr == "application/ld+json":
                self.in_script_jsonld = True
                self._jsonld_buffer = ""
        if tag == "link" and attr.get("href"):
            rel = (attr.get("rel") or "").lower()
            if rel in ("stylesheet", "icon", "shortcut icon"):
                self.resource_urls.append(("link", attr.get("href")))

    def handle_endtag(self, tag):
        if tag in WORD_BLOCKLIST:
            self.skip = max(0, self.skip - 1)
        if tag == "title" and self.in_title:
            self.in_title = False
        if tag == "head":
            self.in_head = False
        if tag == "h1" and self.current_h1 is not None:
            self.h1s.append(self.current_h1.strip())
            self.current_h1 = None
        if tag == "script" and self.in_script_jsonld:
            self.in_script_jsonld = False
            try:
                data = json.loads(self._jsonld_buffer)
                if isinstance(data, dict):
                    self.structured_data.append(data.get("@type", "JSON-LD"))
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            self.structured_data.append(item.get("@type", "JSON-LD"))
            except Exception:
                pass
            self._jsonld_buffer = ""
        self.current_tag = None

    def handle_data(self, data):
        if self.in_title:
            self.title = (self.title or "") + data
        if self.current_tag == "h1" and self.current_h1 is not None:
            self.current_h1 = (self.current_h1 or "") + data
        if self.skip == 0 and self.current_tag not in ("script", "style"):
            stripped = data.strip()
            if stripped:
                self.text_parts.append(stripped)
        if self.in_script_jsonld:
            self._jsonld_buffer += data


def parse_page(text: str):
    parser = PageParser()
    parser.feed(text)
    word_count = len(re.findall(r"\b\w+\b", " ".join(parser.text_parts)))
    title = (parser.title or "").strip()
    return {
        "title": title,
        "meta_description": (parser.meta_desc or "").strip(),
        "h1": parser.h1s[0] if parser.h1s else "",
        "h1_count": len(parser.h1s),
        "canonical": parser.canonical or "",
        "has_viewport": parser.has_viewport,
        "robots_meta": parser.robots_meta or "",
        "hreflangs": parser.hreflangs,
        "images": parser.images,
        "resource_urls": parser.resource_urls,
        "structured_data": parser.structured_data,
        "links": parser.links,
        "word_count": word_count,
    }


# ------------------------------------------------------------- PageSpeed Insights

def psi_score(url: str, api_key: str):
    """Call PageSpeed Insights API. Returns dict or None on failure."""
    if not api_key:
        return None
    endpoint = (
        "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
        f"?url={urllib.request.quote(url)}&key={api_key}&category=PERFORMANCE&category=SEO"
    )
    try:
        req = urllib.request.Request(
            endpoint,
            headers={"Accept": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.load(resp)
    except Exception as e:
        return {"error": str(e)}

    try:
        lh = data.get("lighthouseResult", {})
        audits = lh.get("audits", {})
        metrics = lh.get("audits", {})
        cwv = data.get("loadingExperience", {}).get("metrics", {})

        def ms(x):
            try:
                return round(x / 1000, 2) if x else None
            except Exception:
                return None

        return {
            "lcp": ms(cwv.get("LARGEST_CONTENTFUL_PAINT_MS", {}).get("percentile"))
                or ms(metrics.get("largest-contentful-paint", {}).get("numericValue")),
            "inp": ms(cwv.get("INTERACTION_TO_NEXT_PAINT", {}).get("percentile"))
                or ms(metrics.get("interaction-to-next-paint", {}).get("numericValue")),
            "cls": round(cwv.get("CUMULATIVE_LAYOUT_SHIFT_SCORE", {}).get("percentile", 0) / 100, 3)
                or metrics.get("cumulative-layout-shift", {}).get("numericValue"),
            "performance_score": lh.get("categories", {}).get("performance", {}).get("score"),
            "seo_score": lh.get("categories", {}).get("seo", {}).get("score"),
        }
    except Exception as e:
        return {"error": f"parse error: {e}"}


# ---------------------------------------------------------------------- auditing

def audit_url(url: str, api_key: str = "", rp: urllib.robotparser.RobotFileParser = None, base_url: str = ""):
    """Audit a single URL. Returns (page_row_dict, issues_list, internal_links)."""
    text, final_url, status, headers = fetch(url)
    headers_lower = {k.lower(): v for k, v in headers.items()}
    row = {
        "url": url,
        "status_code": status,
        "final_url": final_url,
        "title": "",
        "meta_description": "",
        "h1": "",
        "canonical": "",
        "canonical_ok": 1,
        "word_count": 0,
        "internal_links": 0,
        "external_links": 0,
        "has_viewport": 0,
        "redirect_count": 0,
        "lcp": None,
        "inp": None,
        "cls": None,
        "performance_score": None,
        "seo_score": None,
        "psi_status": "skipped",
        "fetch_error": "",
        # Screaming Frog-style extra metrics (empty for custom crawler)
        "inlinks": None,
        "outlinks": None,
        "response_time_ms": None,
        "structured_data_types": None,
        "lighthouse_performance": None,
        # in-memory only for post-processing
        "_hreflangs": [],
        "_robots_meta": "",
        "_resource_urls": [],
        "_images": [],
        "_structured_data": [],
    }
    issues = []
    internal_links = []

    if text is None:
        row["fetch_error"] = headers.get("error", f"status {status}")
        if status >= 400:
            sev = "status_5xx" if status >= 500 else "status_4xx"
            issues.append({"type": sev, "severity": ISSUE_SEVERITY[sev], "details": f"HTTP {status}"})
        return row, issues, internal_links

    parsed = parse_page(text)
    row["title"] = parsed["title"]
    row["meta_description"] = parsed["meta_description"]
    row["h1"] = parsed["h1"]
    row["canonical"] = parsed["canonical"]
    row["has_viewport"] = 1 if parsed["has_viewport"] else 0
    row["word_count"] = parsed["word_count"]
    row["_hreflangs"] = parsed["hreflangs"]
    row["_robots_meta"] = parsed["robots_meta"]
    row["_resource_urls"] = parsed["resource_urls"]
    row["_images"] = parsed["images"]
    row["_structured_data"] = parsed["structured_data"]

    base_url = base_url or final_url

    # robots.txt block
    if is_blocked_by_robots(rp, url):
        issues.append({"type": "blocked_by_robots_txt", "severity": ISSUE_SEVERITY["blocked_by_robots_txt"], "details": "URL disallowed in robots.txt"})

    # redirect chain / loop detection
    if normalize_url(final_url) != normalize_url(url):
        redirect_info = fetch_redirect_chain(url, method="HEAD")
        row["redirect_count"] = redirect_info["redirect_count"]
        if redirect_info["loop"]:
            issues.append({
                "type": "redirect_loop",
                "severity": ISSUE_SEVERITY["redirect_loop"],
                "details": " → ".join(redirect_info["chain"]),
            })
        elif redirect_info["redirect_count"] > 1:
            issues.append({
                "type": "redirect_chain",
                "severity": ISSUE_SEVERITY["redirect_chain"],
                "details": f"{redirect_info['redirect_count']} hops → {redirect_info['final_url']}",
            })
        else:
            issues.append({
                "type": "redirect_chain",
                "severity": ISSUE_SEVERITY["redirect_chain"],
                "details": f"redirected to {final_url}",
            })

    # canonical checks
    canonical = parsed["canonical"]
    if canonical:
        canonical_abs = normalize_url(urljoin(final_url, canonical))
        if canonical_abs != normalize_url(final_url):
            row["canonical_ok"] = 0
            issues.append({
                "type": "canonical_mismatch",
                "severity": ISSUE_SEVERITY["canonical_mismatch"],
                "details": f"canonical={parsed['canonical']}, final={final_url}",
            })
    else:
        row["canonical_ok"] = 0
        issues.append({
            "type": "missing_canonical",
            "severity": ISSUE_SEVERITY["missing_canonical"],
            "details": "",
        })

    # indexing directives
    x_robots = headers_lower.get("x-robots-tag", "")
    robots_content = (parsed["robots_meta"] or "") + " " + x_robots.lower()
    if "noindex" in robots_content:
        if "noindex" in (parsed["robots_meta"] or ""):
            issues.append({"type": "noindex_robots_meta", "severity": ISSUE_SEVERITY["noindex_robots_meta"], "details": parsed["robots_meta"]})
        if "noindex" in x_robots.lower():
            issues.append({"type": "x_robots_noindex", "severity": ISSUE_SEVERITY["x_robots_noindex"], "details": x_robots})

    # title / meta / h1 checks
    title_len = len(parsed["title"])
    if not parsed["title"]:
        issues.append({"type": "missing_title", "severity": ISSUE_SEVERITY["missing_title"], "details": ""})
    elif title_len > 60:
        issues.append({"type": "title_too_long", "severity": ISSUE_SEVERITY["title_too_long"], "details": f"{title_len} chars"})

    meta_len = len(parsed["meta_description"])
    if not parsed["meta_description"]:
        issues.append({"type": "missing_meta_description", "severity": ISSUE_SEVERITY["missing_meta_description"], "details": ""})
    elif meta_len > 160:
        issues.append({"type": "meta_description_too_long", "severity": ISSUE_SEVERITY["meta_description_too_long"], "details": f"{meta_len} chars"})

    if not parsed["h1"]:
        issues.append({"type": "missing_h1", "severity": ISSUE_SEVERITY["missing_h1"], "details": ""})
    elif parsed["h1_count"] > 1:
        issues.append({"type": "multiple_h1", "severity": ISSUE_SEVERITY["multiple_h1"], "details": f"{parsed['h1_count']} H1s"})

    if not parsed["has_viewport"]:
        issues.append({"type": "missing_viewport", "severity": ISSUE_SEVERITY["missing_viewport"], "details": ""})

    if parsed["word_count"] < THIN_CONTENT_WORDS:
        issues.append({"type": "thin_content", "severity": ISSUE_SEVERITY["thin_content"], "details": f"{parsed['word_count']} words"})

    if not parsed["structured_data"]:
        issues.append({"type": "missing_structured_data", "severity": ISSUE_SEVERITY["missing_structured_data"], "details": ""})

    # image alt text
    for src, alt in parsed["images"]:
        if not (alt or "").strip():
            abs_src = urljoin(final_url, src)
            issues.append({"type": "missing_alt_text", "severity": ISSUE_SEVERITY["missing_alt_text"], "details": abs_src})

    # mixed content (HTTP resources on HTTPS page)
    parsed_base = urlparse(final_url)
    if parsed_base.scheme == "https":
        for tag, res in parsed["resource_urls"]:
            abs_res = urljoin(final_url, res)
            if urlparse(abs_res).scheme == "http" and is_self_link(abs_res):
                issues.append({"type": "mixed_content", "severity": ISSUE_SEVERITY["mixed_content"], "details": f"<{tag}> {abs_res}"})

    # hreflang local checks (return-tag validation happens in post-processing)
    for code, href in parsed["hreflangs"]:
        if not valid_hreflang_code(code):
            issues.append({"type": "hreflang_invalid_code", "severity": ISSUE_SEVERITY["hreflang_invalid_code"], "details": f"{code} → {href}"})

    # classify links
    for href in parsed["links"]:
        absolute = urljoin(final_url, href)
        if is_self_link(absolute):
            internal_links.append(normalize_url(absolute))
            row["internal_links"] += 1
        else:
            row["external_links"] += 1

    return row, issues, internal_links


def audit_internal_links(internal_links, seen_urls, limit: int = 0):
    """Spot-check internal links for 4xx/redirect. Returns list of issue dicts."""
    issues = []
    unique = list(dict.fromkeys(internal_links))
    if limit and len(unique) > limit:
        unique = unique[:limit]
    for url in unique:
        if url in seen_urls:
            continue
        _, final_url, status, _ = fetch(url, method="HEAD")
        if status >= 400:
            issues.append({
                "url": url,
                "type": "internal_link_4xx",
                "severity": ISSUE_SEVERITY["internal_link_4xx"],
                "details": f"HTTP {status}",
            })
        elif normalize_url(final_url) != url:
            issues.append({
                "url": url,
                "type": "internal_link_redirect",
                "severity": ISSUE_SEVERITY["internal_link_redirect"],
                "details": f"→ {final_url}",
            })
        time.sleep(CRAWL_DELAY_SECONDS)
    return issues


def post_process_issues(page_rows: list, property: str):
    """Run duplicate, hreflang, and canonical-target checks across all crawled pages."""
    issues = []
    url_to_row = {normalize_url(p["url"]): p for p in page_rows}

    # ---- duplicate title / meta description / h1 --------------------------------
    buckets = {"title": {}, "meta_description": {}, "h1": {}}
    for p in page_rows:
        for key in buckets:
            val = (p.get(key) or "").strip()
            if val:
                buckets[key].setdefault(val, []).append(normalize_url(p["url"]))

    issue_map = {
        "title": "duplicate_title",
        "meta_description": "duplicate_meta_description",
        "h1": "duplicate_h1",
    }
    for key, val_map in buckets.items():
        for val, urls in val_map.items():
            if len(urls) > 1:
                for url in urls:
                    issues.append({
                        "url": url,
                        "type": issue_map[key],
                        "severity": ISSUE_SEVERITY[issue_map[key]],
                        "details": f"shared with {len(urls) - 1} other page(s): {urls[0] if urls[0] != url else urls[1]}",
                    })

    # ---- hreflang validation ----------------------------------------------------
    # Build graph of hreflang links within crawled set
    hreflang_targets = set()  # external or internal targets to status-check
    return_tag_graph = {}     # target_norm -> set(source_norm)
    for p in page_rows:
        src = normalize_url(p["url"])
        has_self = False
        for code, href in p.get("_hreflangs", []):
            if not href:
                continue
            target = normalize_url(urljoin(p["final_url"], href))
            if target == src:
                has_self = True
            if target in url_to_row:
                return_tag_graph.setdefault(target, set()).add(src)
            else:
                hreflang_targets.add((p["url"], code, target))
        if p.get("_hreflangs") and not has_self:
            issues.append({
                "url": p["url"],
                "type": "hreflang_missing_self_reference",
                "severity": ISSUE_SEVERITY["hreflang_missing_self_reference"],
                "details": "",
            })

    # return-tag check: A -> B implies B has a link back to A
    for p in page_rows:
        src = normalize_url(p["url"])
        for code, href in p.get("_hreflangs", []):
            target = normalize_url(urljoin(p["final_url"], href))
            if target in url_to_row and src not in return_tag_graph.get(target, set()):
                issues.append({
                    "url": p["url"],
                    "type": "hreflang_missing_return_tag",
                    "severity": ISSUE_SEVERITY["hreflang_missing_return_tag"],
                    "details": f"{code} → {href}",
                })

    # status-check external/internal hreflang targets not in crawl set (cap at 100)
    checked = set()
    for source_url, code, target in list(hreflang_targets)[:100]:
        if target in checked:
            continue
        checked.add(target)
        _, final, status, _ = fetch(target, method="HEAD")
        if status >= 400 or status == 0:
            issues.append({
                "url": source_url,
                "type": "hreflang_non_200",
                "severity": ISSUE_SEVERITY["hreflang_non_200"],
                "details": f"{code} → {target} (HTTP {status})",
            })
        time.sleep(CRAWL_DELAY_SECONDS)

    # ---- canonical target validation --------------------------------------------
    canonical_targets = []
    seen_canonicals = set()
    for p in page_rows:
        canonical = (p.get("canonical") or "").strip()
        if not canonical:
            continue
        target = normalize_url(urljoin(p["final_url"], canonical))
        if target == normalize_url(p["url"]):
            continue
        if target not in seen_canonicals:
            seen_canonicals.add(target)
            canonical_targets.append((p["url"], target))

    for source_url, target in canonical_targets[:200]:
        _, final, status, _ = fetch(target, method="HEAD")
        if status >= 400 or status == 0:
            issues.append({
                "url": source_url,
                "type": "canonical_to_non_200",
                "severity": ISSUE_SEVERITY["canonical_to_non_200"],
                "details": f"canonical={target} (HTTP {status})",
            })
        elif normalize_url(final) != target:
            issues.append({
                "url": source_url,
                "type": "canonicalized_to_redirect",
                "severity": ISSUE_SEVERITY["canonicalized_to_redirect"],
                "details": f"canonical={target} → {final}",
            })
        time.sleep(CRAWL_DELAY_SECONDS)

    return issues


# ------------------------------------------------------------------------- runs

def should_run(property: str, force: bool) -> bool:
    if force:
        return True
    con = init_db()
    row = con.execute(
        "SELECT day FROM site_audit_runs WHERE property = ? ORDER BY day DESC LIMIT 1",
        (property,),
    ).fetchone()
    con.close()
    if not row:
        return True
    last = date.fromisoformat(row[0])
    return (date.today() - last).days >= MIN_DAYS_BETWEEN_RUNS


def run_for_property(property: str, sitemaps: list, limit: int = 0, psi_limit: int = MAX_PSI_PAGES, api_key: str = ""):
    day = today()
    start_time = time.time()

    # robots.txt for the property
    base_url = f"https://{PROPERTIES[property]['domain']}"
    rp = parse_robots_txt(base_url)

    urls = []
    sitemap_issues = []
    for _, _, sm_url, pattern in sitemaps:
        text, final_url, status, _ = fetch(sm_url)
        if status != 200 or text is None:
            sitemap_issues.append({
                "url": sm_url,
                "type": "sitemap_fetch_error",
                "severity": ISSUE_SEVERITY["sitemap_fetch_error"],
                "details": f"HTTP {status}",
            })
            continue
        parsed = parse_sitemap(sm_url, limit=limit)
        for u, _ in parsed:
            if pattern and not re.search(pattern, u):
                continue
            urls.append(u)
        if limit and len(urls) >= limit:
            urls = urls[:limit]
            break

    urls = list(dict.fromkeys(urls))
    print(f"[{property}] auditing {len(urls)} URLs")

    page_rows = []
    all_issues = []
    seen_urls = set()
    failed = 0
    internal_links_pool = []

    for i, url in enumerate(urls, 1):
        seen_urls.add(normalize_url(url))
        row, issues, internal_links = audit_url(url, api_key="", rp=rp, base_url=base_url)
        page_rows.append(row)
        all_issues.extend([{**iss, "url": url} for iss in issues])
        internal_links_pool.extend(internal_links)
        if row["fetch_error"]:
            failed += 1
        if i % 10 == 0:
            print(f"  crawled {i}/{len(urls)}")
        time.sleep(CRAWL_DELAY_SECONDS)

    # spot-check internal links
    print(f"[{property}] spot-checking {len(internal_links_pool)} internal links")
    link_issues = audit_internal_links(internal_links_pool, seen_urls, limit=min(200, len(internal_links_pool)))
    all_issues.extend(link_issues)

    # cross-page post-processing (duplicates, hreflang return tags, canonical targets)
    print(f"[{property}] post-processing {len(page_rows)} pages")
    all_issues.extend(post_process_issues(page_rows, property))

    # sitemap-level issues (must be attached to a URL for the table; use sitemap URL)
    all_issues.extend(sitemap_issues)

    # PageSpeed Insights on top pages (prioritize by issue severity, then by rank if available)
    psi_calls = 0
    if api_key:
        con = sqlite3.connect(DB_PATH)
        ranked = con.execute(
            """SELECT url, position FROM rank_snapshots
               WHERE property = ? AND day = (SELECT MAX(day) FROM rank_snapshots WHERE property = ?)
               ORDER BY position ASC LIMIT ?""",
            (property, property, psi_limit),
        ).fetchall()
        con.close()
        psi_urls = [u for u, _ in ranked if any(normalize_url(u) == normalize_url(p["url"]) for p in page_rows)]
        if not psi_urls:
            psi_urls = [p["url"] for p in page_rows[:psi_limit]]

        print(f"[{property}] running PSI on {len(psi_urls)} pages")
        for url in psi_urls:
            score = psi_score(url, api_key)
            if score:
                for p in page_rows:
                    if normalize_url(p["url"]) == normalize_url(url):
                        if "error" in score:
                            p["psi_status"] = f"error: {score['error']}"
                        else:
                            p["lcp"] = score.get("lcp")
                            p["inp"] = score.get("inp")
                            p["cls"] = score.get("cls")
                            p["performance_score"] = int(score.get("performance_score", 0) * 100) if score.get("performance_score") is not None else None
                            p["seo_score"] = int(score.get("seo_score", 0) * 100) if score.get("seo_score") is not None else None
                            p["psi_status"] = "ok"
                            if score.get("lcp") and score["lcp"] > 2.5:
                                all_issues.append({"url": url, "type": "slow_lcp", "severity": ISSUE_SEVERITY["slow_lcp"], "details": f"{score['lcp']}s"})
                            if score.get("cls") and score["cls"] > 0.1:
                                all_issues.append({"url": url, "type": "poor_cls", "severity": ISSUE_SEVERITY["poor_cls"], "details": f"{score['cls']}"})
                        psi_calls += 1
                        break
            time.sleep(0.5)

    duration = int(time.time() - start_time)
    run_row = {
        "day": day,
        "property": property,
        "pages_crawled": len(page_rows),
        "pages_failed": failed,
        "issues_found": len(all_issues),
        "psi_calls": psi_calls,
        "run_duration_seconds": duration,
        "crawl_source": "custom",
    }
    return run_row, page_rows, all_issues


def save(run_row: dict, page_rows: list, issues: list):
    # deduplicate issues by (url, issue_type) for PK safety;
    # concatenate details when multiple instances exist on the same page.
    deduped_issues = {}
    for i in issues:
        key = (i["url"], i["type"])
        if key in deduped_issues:
            existing = deduped_issues[key]
            if i["details"] and i["details"] not in existing["details"]:
                existing["details"] = (existing["details"] + "; " + i["details"]).strip("; ")
        else:
            deduped_issues[key] = {
                "day": run_row["day"],
                "property": run_row["property"],
                "url": i["url"],
                "issue_type": i["type"],
                "severity": i["severity"],
                "details": i["details"] or "",
            }
    issue_rows = list(deduped_issues.values())
    run_row["issues_found"] = len(issue_rows)

    con = init_db()
    # Remove stale data from a previous run on the same day/property so
    # fixed issues disappear and counts stay accurate.
    con.execute(
        "DELETE FROM site_audit_issues WHERE day = ? AND property = ?",
        (run_row["day"], run_row["property"]),
    )
    con.execute(
        "DELETE FROM site_audit_pages WHERE day = ? AND property = ?",
        (run_row["day"], run_row["property"]),
    )
    con.execute(
        "DELETE FROM site_audit_runs WHERE day = ? AND property = ?",
        (run_row["day"], run_row["property"]),
    )

    con.execute(
        """INSERT OR REPLACE INTO site_audit_runs
           (day, property, pages_crawled, pages_failed, issues_found, psi_calls, run_duration_seconds, crawl_source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_row["day"], run_row["property"], run_row["pages_crawled"],
         run_row["pages_failed"], run_row["issues_found"], run_row["psi_calls"],
         run_row["run_duration_seconds"], run_row.get("crawl_source", "custom")),
    )
    con.executemany(
        """INSERT OR REPLACE INTO site_audit_pages
           (day, property, url, status_code, final_url, title, meta_description, h1,
            canonical, canonical_ok, word_count, internal_links, external_links,
            has_viewport, redirect_count, lcp, inp, cls, performance_score, seo_score,
            psi_status, fetch_error, inlinks, outlinks, response_time_ms,
            structured_data_types, lighthouse_performance)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(run_row["day"], run_row["property"], p["url"], p["status_code"], p["final_url"],
          p["title"], p["meta_description"], p["h1"], p["canonical"], p["canonical_ok"],
          p["word_count"], p["internal_links"], p["external_links"], p["has_viewport"],
          p["redirect_count"], p["lcp"], p["inp"], p["cls"], p["performance_score"],
          p["seo_score"], p["psi_status"], p["fetch_error"],
          p.get("inlinks"), p.get("outlinks"), p.get("response_time_ms"),
          p.get("structured_data_types"), p.get("lighthouse_performance"))
         for p in page_rows],
    )
    con.executemany(
        """INSERT OR REPLACE INTO site_audit_issues
           (day, property, url, issue_type, severity, details)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [(i["day"], i["property"], i["url"], i["issue_type"], i["severity"], i["details"])
         for i in issue_rows],
    )
    con.commit()
    con.close()

    # optional Supabase sync (strip in-memory-only keys from pages)
    supabase_upsert("site_audit_runs", [run_row])
    page_cols = {
        "url", "status_code", "final_url", "title", "meta_description", "h1",
        "canonical", "canonical_ok", "word_count", "internal_links",
        "external_links", "has_viewport", "redirect_count", "lcp", "inp",
        "cls", "performance_score", "seo_score", "psi_status", "fetch_error",
        "inlinks", "outlinks", "response_time_ms", "structured_data_types",
        "lighthouse_performance",
    }
    supabase_upsert("site_audit_pages", [
        {**{k: v for k, v in p.items() if k in page_cols},
         "day": run_row["day"], "property": run_row["property"]}
        for p in page_rows
    ])
    supabase_upsert("site_audit_issues", issue_rows)


# -------------------------------------------------------------------------- CLI

def main():
    load_env()
    ap = argparse.ArgumentParser(description="Technical site health crawler")
    ap.add_argument("--dry-run", action="store_true", help="preview what would run; no network")
    ap.add_argument("--limit", type=int, default=0, help="max URLs per property")
    ap.add_argument("--force", action="store_true", help="run even if already ran this month")
    ap.add_argument("--property", choices=["vantagecircle", "vantagefit", "all"], default="all", help="which property to audit")
    ap.add_argument("--provider", choices=["custom", "dataforseo", "screamingfrog"], default="custom", help="crawl provider: custom crawler, DataForSEO OnPage API, or Screaming Frog SEO Spider")
    args = ap.parse_args()

    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        print("[note] GOOGLE_API_KEY not set; skipping PageSpeed Insights (CWV/Lighthouse)")

    config = load_config()
    prop_map = {}
    for prop, ptype, sm_url, pattern in config:
        key = "vantagefit" if prop.lower().startswith("vantagefit") else "vantagecircle"
        prop_map.setdefault(key, []).append((prop, ptype, sm_url, pattern))

    targets = ["vantagecircle", "vantagefit"] if args.property == "all" else [args.property]

    for prop in targets:
        sitemaps = prop_map.get(prop, [])
        if not sitemaps:
            print(f"[{prop}] no sitemaps configured; skipping")
            continue
        if not should_run(prop, args.force):
            print(f"[{prop}] already ran within {MIN_DAYS_BETWEEN_RUNS} days; use --force to override")
            continue
        if args.dry_run:
            if args.provider == "dataforseo":
                max_pages = args.limit or dataforseo_site_audit.MAX_CRAWL_PAGES
                print(f"[dry-run {prop}] would post DataForSEO OnPage task for {PROPERTIES[prop]['domain']} (max {max_pages} pages)")
                if sitemaps:
                    print(f"  custom sitemap: {sitemaps[0][2]}")
                continue
            if args.provider == "screamingfrog":
                print(f"[dry-run {prop}] would run Screaming Frog headless crawl for {PROPERTIES[prop]['domain']}")
                if sitemaps:
                    print(f"  using sitemap: {sitemaps[0][2]}")
                continue
            urls = []
            for _, _, sm_url, pattern in sitemaps:
                parsed = parse_sitemap(sm_url, limit=args.limit)
                for u, _ in parsed:
                    if pattern and not re.search(pattern, u):
                        continue
                    urls.append(u)
            urls = list(dict.fromkeys(urls))[:args.limit or len(urls)]
            print(f"[dry-run {prop}] would audit {len(urls)} URLs from {len(sitemaps)} sitemap(s)")
            for u in urls[:10]:
                print(f"  - {u}")
            if len(urls) > 10:
                print(f"  ... and {len(urls) - 10} more")
            continue

        if args.provider == "dataforseo":
            run_row, page_rows, issues = dataforseo_site_audit.run_for_property(prop, sitemaps, limit=args.limit)
        elif args.provider == "screamingfrog":
            import screamingfrog_site_audit
            run_row, page_rows, issues = screamingfrog_site_audit.run_for_property(prop, sitemaps, limit=args.limit)
        else:
            run_row, page_rows, issues = run_for_property(prop, sitemaps, limit=args.limit, api_key=api_key)
        save(run_row, page_rows, issues)
        print(f"[{prop}] done: {run_row['pages_crawled']} pages, {run_row['issues_found']} issues, {run_row['psi_calls']} PSI calls in {run_row['run_duration_seconds']}s")


if __name__ == "__main__":
    main()
