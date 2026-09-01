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
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from common import DB_PATH, init_db, load_env, supabase_upsert

HERE = Path(__file__).parent
CONFIG = HERE / "freshness_sitemaps.csv"

# ---- edit these ------------------------------------------------------------
MAX_PAGES_PER_SITEMAP = 500
REQUEST_TIMEOUT = 25
CRAWL_DELAY_SECONDS = 0.3
MIN_DAYS_BETWEEN_RUNS = 25          # monthly-ish gate
MAX_PSI_PAGES = 50                  # PSI has a free quota; audit top N pages only
WORD_BLOCKLIST = {"script", "style", "nav", "header", "footer", "aside", "noscript"}
# -----------------------------------------------------------------------------

SELF_DOMAINS = {"vantagecircle.com", "www.vantagecircle.com",
                "vantagefit.io", "www.vantagefit.io"}

PROPERTIES = {
    "vantagecircle": {"label": "Vantage Circle", "domain": "vantagecircle.com"},
    "vantagefit": {"label": "Vantage Fit", "domain": "vantagefit.io"},
}

ISSUE_SEVERITY = {
    "status_4xx": "critical",
    "status_5xx": "critical",
    "redirect_chain": "warning",
    "missing_title": "critical",
    "title_too_long": "warning",
    "missing_meta_description": "warning",
    "meta_description_too_long": "info",
    "missing_h1": "critical",
    "multiple_h1": "warning",
    "canonical_mismatch": "warning",
    "missing_viewport": "warning",
    "internal_link_4xx": "critical",
    "internal_link_redirect": "info",
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
        self.in_title = False
        self.in_head = True
        self.current_tag = None
        self.current_h1 = None

    def handle_starttag(self, tag, attrs):
        self.current_tag = tag
        attr = dict(attrs)
        if tag in WORD_BLOCKLIST:
            self.skip += 1
        if self.in_head and tag == "title":
            self.in_title = True
        if self.in_head and tag == "link" and attr.get("rel") == "canonical":
            self.canonical = attr.get("href")
        if self.in_head and tag == "meta":
            name = (attr.get("name") or attr.get("property") or "").lower()
            if name in ("description", "og:description") and not self.meta_desc:
                self.meta_desc = attr.get("content")
            if name == "viewport":
                self.has_viewport = True
        if tag == "h1":
            self.current_h1 = ""
        if tag == "a" and attr.get("href"):
            href = attr.get("href")
            self.links.append(href)

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

def audit_url(url: str, api_key: str = ""):
    """Audit a single URL. Returns (page_row_dict, issues_list, internal_links)."""
    text, final_url, status, headers = fetch(url)
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

    # redirect count approximation
    if normalize_url(final_url) != normalize_url(url):
        row["redirect_count"] = 1

    # canonical check (resolve relative URLs)
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

    if row["redirect_count"] > 0:
        issues.append({"type": "redirect_chain", "severity": ISSUE_SEVERITY["redirect_chain"], "details": f"redirected to {final_url}"})

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
    urls = []
    for _, _, sm_url, pattern in sitemaps:
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
        row, issues, internal_links = audit_url(url, api_key="")
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
    }
    return run_row, page_rows, all_issues


def save(run_row: dict, page_rows: list, issues: list):
    con = init_db()
    con.execute(
        """INSERT OR REPLACE INTO site_audit_runs
           (day, property, pages_crawled, pages_failed, issues_found, psi_calls, run_duration_seconds)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (run_row["day"], run_row["property"], run_row["pages_crawled"],
         run_row["pages_failed"], run_row["issues_found"], run_row["psi_calls"],
         run_row["run_duration_seconds"]),
    )
    con.executemany(
        """INSERT OR REPLACE INTO site_audit_pages
           (day, property, url, status_code, final_url, title, meta_description, h1,
            canonical, canonical_ok, word_count, internal_links, external_links,
            has_viewport, redirect_count, lcp, inp, cls, performance_score, seo_score,
            psi_status, fetch_error)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(run_row["day"], run_row["property"], p["url"], p["status_code"], p["final_url"],
          p["title"], p["meta_description"], p["h1"], p["canonical"], p["canonical_ok"],
          p["word_count"], p["internal_links"], p["external_links"], p["has_viewport"],
          p["redirect_count"], p["lcp"], p["inp"], p["cls"], p["performance_score"],
          p["seo_score"], p["psi_status"], p["fetch_error"])
         for p in page_rows],
    )
    con.executemany(
        """INSERT OR REPLACE INTO site_audit_issues
           (day, property, url, issue_type, severity, details)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [(run_row["day"], run_row["property"], i["url"], i["type"], i["severity"], i["details"])
         for i in issues],
    )
    con.commit()
    con.close()

    # optional Supabase sync
    supabase_upsert("site_audit_runs", [run_row])
    supabase_upsert("site_audit_pages", [
        {**p, "day": run_row["day"], "property": run_row["property"]}
        for p in page_rows
    ])
    supabase_upsert("site_audit_issues", [
        {
            "day": run_row["day"],
            "property": run_row["property"],
            "url": i["url"],
            "issue_type": i["type"],
            "severity": i["severity"],
            "details": i["details"],
        }
        for i in issues
    ])


# -------------------------------------------------------------------------- CLI

def main():
    load_env()
    ap = argparse.ArgumentParser(description="Technical site health crawler")
    ap.add_argument("--dry-run", action="store_true", help="preview what would run; no network")
    ap.add_argument("--limit", type=int, default=0, help="max URLs per property")
    ap.add_argument("--force", action="store_true", help="run even if already ran this month")
    ap.add_argument("--property", choices=["vantagecircle", "vantagefit", "all"], default="all", help="which property to audit")
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

        run_row, page_rows, issues = run_for_property(prop, sitemaps, limit=args.limit, api_key=api_key)
        save(run_row, page_rows, issues)
        print(f"[{prop}] done: {run_row['pages_crawled']} pages, {run_row['issues_found']} issues, {run_row['psi_calls']} PSI calls in {run_row['run_duration_seconds']}s")


if __name__ == "__main__":
    main()
