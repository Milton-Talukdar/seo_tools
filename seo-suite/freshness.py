#!/usr/bin/env python3
"""
freshness.py — Content Freshness / Decay Monitor.

Phase 1: crawl configured sitemaps, extract page metadata, score each page on
age + depth + importance, and flag decay risk.
Phase 2: layer in rank-trend decline and (optionally) Google Search Console
traffic decline to compute a priority-ranked action list: Refresh, Update,
Consolidate, or Prune.

Reads: freshness_sitemaps.csv
Writes: freshness_scores table in seo_suite.db

Usage:
    python3 freshness.py --dry-run          # preview what would run; no network
    python3 freshness.py --limit 10         # only crawl 10 URLs per sitemap
    python3 freshness.py --force            # run even if already ran this month
    python3 freshness.py --property vc      # only one property
    python3 freshness.py                    # monthly full run (self-throttled)
"""
import argparse
import base64
import csv
import gzip
import hashlib
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

from common import DB_PATH, init_db, supabase_upsert

HERE = Path(__file__).parent
CONFIG = HERE / "freshness_sitemaps.csv"

# ---- edit these ------------------------------------------------------------
MAX_PAGES_PER_SITEMAP = 500
REQUEST_TIMEOUT = 25
CRAWL_DELAY_SECONDS = 0.3
MIN_DAYS_BETWEEN_RUNS = 25          # monthly-ish gate
WORD_BLOCKLIST = {"script", "style", "nav", "header", "footer", "aside", "noscript"}
GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
# -----------------------------------------------------------------------------

SELF_DOMAINS = {"vantagecircle.com", "www.vantagecircle.com",
                "vantagefit.io", "www.vantagefit.io"}


def now():
    return datetime.now(timezone.utc).isoformat()


def today():
    return date.today().isoformat()


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:12]


def normalize_url(url: str) -> str:
    return url.split("#")[0].rstrip("/")


def domain_from_url(url: str) -> str:
    return urlparse(url).netloc.lower().lstrip("www.")


def is_self_link(url: str) -> bool:
    netloc = urlparse(url).netloc.lower()
    if not netloc:
        return True
    return netloc in SELF_DOMAINS


# --------------------------------------------------------------------------- fetch

def fetch(url: str, binary: bool = False, method: str = "GET"):
    """Fetch a URL. Returns (body_bytes_or_text, final_url, status, headers)."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; VantageSEOFreshnessBot/1.0; "
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


def head(url: str):
    """Lightweight HEAD request. Returns (final_url, status, headers)."""
    text, final_url, status, headers = fetch(url, method="HEAD")
    return final_url, status, headers


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
        # this is a sitemap index; recurse into child sitemaps
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

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.text_parts = []
        self.links = []
        self.h1 = None
        self.title = None
        self.canonical = None
        self.meta_desc = None
        self.published = None
        self.modified = None
        self.ld_json = []
        self.in_title = False
        self.in_head = True
        self.in_ld_json = False
        self.current_tag = None

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
            if name == "article:published_time":
                self.published = attr.get("content")
            if name == "article:modified_time":
                self.modified = attr.get("content")
        if tag == "h1" and self.h1 is None:
            self.h1 = ""
        if tag == "a" and attr.get("href"):
            href = attr.get("href")
            self.links.append(href)
        if tag == "script" and attr.get("type") == "application/ld+json":
            self.in_ld_json = True

    def handle_endtag(self, tag):
        if tag in WORD_BLOCKLIST:
            self.skip = max(0, self.skip - 1)
        if tag == "title" and self.in_title:
            self.in_title = False
        if tag == "head":
            self.in_head = False
        self.current_tag = None
        if tag == "script":
            self.in_ld_json = False

    def handle_data(self, data):
        if self.in_title:
            self.title = (self.title or "") + data
        if self.current_tag == "h1" and self.h1 is not None:
            self.h1 = (self.h1 or "") + data
        if self.skip == 0 and self.current_tag not in ("script", "style"):
            stripped = data.strip()
            if stripped:
                self.text_parts.append(stripped)
        if getattr(self, "in_ld_json", False):
            self.ld_json.append(data)

    def text(self):
        return "\n".join(self.text_parts)


def extract_schema_dates(ld_json_blocks):
    """Return (published, modified, [schema_types]) from JSON-LD blocks."""
    published = modified = None
    types = []
    for raw in ld_json_blocks:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            ctx = item.get("@context", "")
            if isinstance(ctx, str) and "schema.org" not in ctx and "schema.org" not in str(item):
                continue
            t = item.get("@type")
            if isinstance(t, str):
                types.append(t)
            elif isinstance(t, list):
                types.extend(t)
            if not published and item.get("datePublished"):
                published = item.get("datePublished")
            if not modified and item.get("dateModified"):
                modified = item.get("dateModified")
    return published, modified, list(dict.fromkeys(types))


def parse_http_date(value):
    """Parse common HTTP Last-Modified formats."""
    if not value:
        return None
    value = value.strip()
    formats = [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d-%b-%Y %H:%M:%S %Z",
        "%d %b %Y %H:%M:%S %Z",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def parse_iso_date(value):
    """Parse ISO-ish dates robustly."""
    if not value:
        return None
    value = value.strip()
    # strip timezone name in parentheses, e.g. "2024-01-01 00:00:00 UTC"
    value = re.sub(r"\s+[A-Z]{2,4}$", "", value)
    # DataForSEO/WordPress sometimes uses space instead of T
    value = value.replace(" ", "T", 1)
    # allow fractional seconds and Z
    value = value.rstrip("Z")
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    # fallback: date only
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    return None


def choose_modified_date(http_lastmod, sitemap_lastmod, meta_modified, schema_modified, published):
    """Pick the most recent trustworthy modified date."""
    candidates = []
    for v in (http_lastmod, meta_modified, schema_modified, sitemap_lastmod):
        if v:
            candidates.append(v)
    if not candidates and published:
        return published
    if not candidates:
        return None
    return max(candidates)


def word_count_from_text(text: str) -> int:
    """Rough word count; good enough for relative depth scoring."""
    return len(re.findall(r"\b\w+\b", text))


def count_links(links, base_url):
    internal = external = 0
    for href in links:
        full = urljoin(base_url, href)
        if is_self_link(full):
            internal += 1
        else:
            external += 1
    return internal, external


def crawl_page(url: str, sitemap_lastmod: str = None):
    """Crawl a single page and return a dict of metadata."""
    # HEAD first to capture Last-Modified cheaply
    final_url, status, headers = head(url)
    http_lastmod = parse_http_date(headers.get("Last-Modified"))

    if status in (301, 302, 307, 308) or final_url != url:
        # redirect
        return {
            "url": normalize_url(url),
            "status_code": status,
            "redirect_url": final_url,
        }

    if status != 200:
        return {
            "url": normalize_url(url),
            "status_code": status,
        }

    text, final_url, status, _ = fetch(url)
    if text is None:
        return {"url": normalize_url(url), "status_code": status or 0}

    parser = TextExtractor()
    try:
        parser.feed(text)
    except Exception:
        pass

    schema_pub_raw, schema_mod_raw, schema_types = extract_schema_dates(parser.ld_json)
    schema_pub = parse_iso_date(schema_pub_raw)
    schema_mod = parse_iso_date(schema_mod_raw)
    sitemap_mod = parse_iso_date(sitemap_lastmod)
    meta_pub = parse_iso_date(parser.published)
    meta_mod = parse_iso_date(parser.modified)

    published = schema_pub or meta_pub or sitemap_mod or http_lastmod
    modified = choose_modified_date(http_lastmod, sitemap_mod, meta_mod, schema_mod, published)

    body_text = parser.text()
    wc = word_count_from_text(body_text)
    internal, external = count_links(parser.links, final_url)

    return {
        "url": normalize_url(url),
        "status_code": status,
        "redirect_url": final_url if final_url != url else None,
        "title": (parser.title or "").strip(),
        "h1": (parser.h1 or "").strip(),
        "canonical": parser.canonical,
        "published_date": published.isoformat() if published else None,
        "modified_date": modified.isoformat() if modified else None,
        "word_count": wc,
        "internal_links": internal,
        "external_links": external,
        "schema_types": ",".join(schema_types),
    }


# ----------------------------------------------------------------- scoring logic

def age_days(modified_date_iso):
    if not modified_date_iso:
        return 9999
    try:
        d = datetime.fromisoformat(modified_date_iso).replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).days
    except Exception:
        return 9999


def freshness_score(age_days_):
    if age_days_ <= 90:
        return 100
    if age_days_ <= 180:
        return 80
    if age_days_ <= 365:
        return 60
    if age_days_ <= 730:
        return 40
    return 20


def depth_score(word_count, schema_types):
    base = 0
    if word_count >= 2000:
        base = 100
    elif word_count >= 1200:
        base = 85
    elif word_count >= 800:
        base = 70
    elif word_count >= 400:
        base = 50
    elif word_count >= 200:
        base = 35
    else:
        base = 20
    # small bonus for structured data
    if schema_types:
        base = min(100, base + 10)
    return base


def importance_score(position, volume):
    if position is None or position > 100:
        return 30
    if position <= 3:
        return 100
    if position <= 10:
        return 85
    if position <= 20:
        return 70
    if position <= 50:
        return 55
    return 40


def health_score(status_code, redirect_url):
    if status_code == 200:
        return 100
    if redirect_url:
        return 70
    if status_code in (404, 410):
        return 0
    return 40


def overall_decay_risk(freshness, depth, importance, health):
    # weighted composite; lower = higher risk
    score = (
        freshness * 0.40 +
        depth * 0.25 +
        importance * 0.20 +
        health * 0.15
    )
    if score >= 70:
        return "LOW"
    if score >= 45:
        return "MEDIUM"
    return "HIGH"


# ---------------------------------------------------------------- rank + traffic

def best_keyword_for_url(con, property_, url, day):
    """Return (keyword, position, volume) for the keyword ranking this URL."""
    domain = domain_from_url(url)
    # exact match first
    row = con.execute(
        """SELECT r.keyword, r.position, COALESCE(k.volume, 0)
           FROM rank_snapshots r
           LEFT JOIN keyword_meta k ON r.property = k.property AND r.keyword = k.keyword
           WHERE r.day = ? AND r.property = ? AND r.url = ?
           ORDER BY r.position ASC, COALESCE(k.volume, 0) DESC
           LIMIT 1""",
        (day, property_, url),
    ).fetchone()
    if row:
        return row
    # fallback: URL contains path
    path = urlparse(url).path
    if path:
        row = con.execute(
            """SELECT r.keyword, r.position, COALESCE(k.volume, 0)
               FROM rank_snapshots r
               LEFT JOIN keyword_meta k ON r.property = k.property AND r.keyword = k.keyword
               WHERE r.day = ? AND r.property = ? AND r.url LIKE ?
               ORDER BY r.position ASC, COALESCE(k.volume, 0) DESC
               LIMIT 1""",
            (day, property_, f"%{path}%"),
        ).fetchone()
        if row:
            return row
    return None, None, 0


def rank_trends(con, property_, keyword, current_day):
    if not keyword:
        return None, None, None
    current = con.execute(
        "SELECT position FROM rank_snapshots WHERE day = ? AND property = ? AND keyword = ?",
        (current_day, property_, keyword),
    ).fetchone()
    if not current:
        return None, None, None
    cur_pos = current[0] if current[0] else 101

    def pos_on(days_ago):
        d = (datetime.strptime(current_day, "%Y-%m-%d").date() - timedelta(days=days_ago)).isoformat()
        row = con.execute(
            "SELECT position FROM rank_snapshots WHERE day <= ? AND property = ? AND keyword = ? ORDER BY day DESC LIMIT 1",
            (d, property_, keyword),
        ).fetchone()
        return row[0] if row and row[0] else 101

    return cur_pos - pos_on(30), cur_pos - pos_on(60), cur_pos - pos_on(90)


# --------------------------------------------------------------- GSC (optional)

def gsc_service_account_credentials():
    """Return credentials if GSC_SERVICE_ACCOUNT_JSON env var is set, else None."""
    raw = os.environ.get("GSC_SERVICE_ACCOUNT_JSON")
    if not raw:
        return None
    try:
        import google.auth.transport.requests
        from google.oauth2 import service_account
        info = json.loads(raw)
        return service_account.Credentials.from_service_account_info(
            info, scopes=GSC_SCOPES
        )
    except Exception as e:
        print(f"  GSC credentials error: {e}")
        return None


def gsc_page_traffic(credentials, site_url, page_url, end_date):
    """Return (clicks_28d, clicks_prev_28d) for a single page from GSC."""
    try:
        from googleapiclient.discovery import build
    except ImportError:
        print("  google-api-python-client not installed; skipping GSC")
        return None, None

    service = build("webmasters", "v3", credentials=credentials, cache_discovery=False)
    start = (datetime.strptime(end_date, "%Y-%m-%d").date() - timedelta(days=55)).isoformat()
    mid = (datetime.strptime(end_date, "%Y-%m-%d").date() - timedelta(days=27)).isoformat()
    end = end_date

    def fetch_range(s, e):
        req = {
            "startDate": s,
            "endDate": e,
            "dimensions": ["date"],
            "dimensionFilterGroups": [{
                "filters": [{"dimension": "page", "expression": page_url, "operator": "equals"}]
            }],
            "rowLimit": 10000,
        }
        resp = service.searchanalytics().query(siteUrl=site_url, body=req).execute()
        return sum(row.get("clicks", 0) for row in resp.get("rows", []))

    return fetch_range(mid, end), fetch_range(start, mid)


# --------------------------------------------------------------- action decision

def decide_action(age_days_, position, volume, rank_drop_avg, traffic_drop_pct,
                  word_count, status_code, redirect_url):
    """Recommend an action and give a one-line reason."""
    if status_code in (404, 410):
        return "FIX", "Page returns 4xx"
    if redirect_url:
        return "FIX", f"Redirect chain ({redirect_url})"
    if status_code != 200:
        return "FIX", f"HTTP {status_code}"

    decaying = (rank_drop_avg is not None and rank_drop_avg > 3) or \
               (traffic_drop_pct is not None and traffic_drop_pct > 20)
    old = age_days_ > 730
    medium_old = age_days_ > 365
    valuable = (position is not None and position <= 20) or (volume and volume >= 100)
    thin = word_count < 300

    if old and not valuable and thin:
        return "PRUNE", "Old, thin, and low value — consider noindex/merge"
    if decaying and valuable:
        return "UPDATE", "Valuable page with declining rank/traffic"
    if medium_old and (valuable or word_count >= 800):
        return "REFRESH", "Mature valuable content due for refresh"
    if thin and valuable:
        return "EXPAND", "Thin but valuable — expand depth"
    return "MONITOR", "No urgent action"


def decay_priority_score(age_days_, position, volume, rank_drop_avg, traffic_drop_pct,
                         freshness, depth, action):
    """Higher score = higher priority."""
    score = 0.0
    # age weight
    score += min(age_days_, 730) / 730 * 25
    # freshness inverse
    score += (100 - freshness) * 0.15
    # depth inverse (thin pages that rank are urgent)
    score += (100 - depth) * 0.10
    # rank decline
    if rank_drop_avg:
        score += min(rank_drop_avg, 50) * 0.8
    # traffic decline
    if traffic_drop_pct:
        score += min(traffic_drop_pct, 100) * 0.25
    # position / volume value
    if position and position <= 10:
        score += 20
    elif position and position <= 30:
        score += 12
    if volume:
        score += min(volume / 100, 15)
    # action multiplier
    multipliers = {"UPDATE": 1.4, "REFRESH": 1.2, "EXPAND": 1.1, "FIX": 1.5, "PRUNE": 0.9, "MONITOR": 0.5}
    score *= multipliers.get(action, 1.0)
    return round(score, 1)


# ---------------------------------------------------------------------- main run

def should_run(con, force: bool) -> bool:
    if force:
        return True
    row = con.execute("SELECT MAX(day) FROM freshness_scores").fetchone()
    if not row or not row[0]:
        return True
    last = datetime.strptime(row[0], "%Y-%m-%d").date()
    return (date.today() - last).days >= MIN_DAYS_BETWEEN_RUNS


def run(args):
    con = init_db()
    if not args.dry_run and not should_run(con, args.force):
        last = con.execute("SELECT MAX(day) FROM freshness_scores").fetchone()[0]
        print(f"Freshness crawl is gated until {MIN_DAYS_BETWEEN_RUNS} days pass (last: {last}). Use --force to override.")
        return

    configs = load_config()
    if args.property:
        configs = [c for c in configs if c[0] == args.property]
    if args.page_type:
        configs = [c for c in configs if c[1] == args.page_type]
    if not configs:
        print("No sitemap configs matched.")
        return

    gsc_creds = gsc_service_account_credentials()
    day = today()
    rank_day = con.execute(
        "SELECT day FROM rank_snapshots GROUP BY day HAVING COUNT(*) >= 50 ORDER BY day DESC LIMIT 1"
    ).fetchone()
    rank_day = rank_day[0] if rank_day else day
    all_rows = []

    # map property -> best GSC site_url heuristic
    gsc_site_urls = {}
    for prop, _, sm_url, _ in configs:
        parsed = urlparse(sm_url)
        gsc_site_urls[prop] = f"https://{parsed.netloc}/"

    for prop, page_type, sm_url, url_pattern in configs:
        print(f"\n[{prop}/{page_type}] parsing {sm_url}")
        urls = parse_sitemap(sm_url, limit=0)
        if url_pattern:
            before = len(urls)
            urls = [(u, lm) for u, lm in urls if re.match(url_pattern, u)]
            print(f"  matched {len(urls)} of {before} URLs by pattern")
        if args.limit:
            urls = urls[:args.limit]
        print(f"  will crawl {len(urls)} URLs")
        if args.dry_run:
            continue

        for i, (url, sitemap_lastmod) in enumerate(urls):
            if i and i % 50 == 0:
                print(f"  crawled {i}/{len(urls)}")
            try:
                meta = crawl_page(url, sitemap_lastmod)
            except Exception as e:
                print(f"  crawl error {url}: {e}")
                meta = {"url": normalize_url(url), "status_code": 0}
            meta["property"] = prop
            meta["page_type"] = page_type
            meta["last_crawled"] = now()

            # rank / keyword matching
            kw, pos, vol = best_keyword_for_url(con, prop, meta["url"], rank_day)
            drop30, drop60, drop90 = rank_trends(con, prop, kw, rank_day)
            rank_drop_avg = None
            if drop30 is not None:
                rank_drop_avg = round(sum([drop30, drop60 or drop30, drop90 or drop30]) / 3, 1)

            # GSC traffic (optional)
            traffic_28d = traffic_prev_28d = traffic_drop_pct = None
            if gsc_creds and meta["status_code"] == 200:
                try:
                    t28, tprev = gsc_page_traffic(gsc_creds, gsc_site_urls[prop], meta["url"], day)
                    if t28 is not None:
                        traffic_28d = int(t28)
                        traffic_prev_28d = int(tprev)
                        if tprev and tprev > 0:
                            traffic_drop_pct = round((tprev - t28) / tprev * 100, 1)
                        else:
                            traffic_drop_pct = 0.0
                except Exception as e:
                    print(f"  GSC error for {meta['url']}: {e}")

            age = age_days(meta.get("modified_date"))
            fresh = freshness_score(age)
            depth = depth_score(meta.get("word_count", 0), meta.get("schema_types"))
            imp = importance_score(pos, vol)
            health = health_score(meta.get("status_code", 0), meta.get("redirect_url"))
            risk = overall_decay_risk(fresh, depth, imp, health)

            action, reason = decide_action(
                age, pos, vol, rank_drop_avg, traffic_drop_pct,
                meta.get("word_count", 0), meta.get("status_code", 0), meta.get("redirect_url")
            )
            priority = decay_priority_score(
                age, pos, vol, rank_drop_avg, traffic_drop_pct, fresh, depth, action
            )

            all_rows.append({
                "day": day,
                "url": meta["url"],
                "property": prop,
                "page_type": page_type,
                "title": meta.get("title", ""),
                "h1": meta.get("h1", ""),
                "published_date": meta.get("published_date"),
                "modified_date": meta.get("modified_date"),
                "age_days": age,
                "word_count": meta.get("word_count", 0),
                "internal_links": meta.get("internal_links", 0),
                "external_links": meta.get("external_links", 0),
                "schema_types": meta.get("schema_types", ""),
                "status_code": meta.get("status_code", 0),
                "canonical": meta.get("canonical", ""),
                "freshness_score": fresh,
                "depth_score": depth,
                "decay_risk": risk,
                "target_keyword": kw or "",
                "position": pos if pos is not None else 101,
                "volume": vol or 0,
                "rank_drop_30d": drop30,
                "rank_drop_60d": drop60,
                "rank_drop_90d": drop90,
                "traffic_28d": traffic_28d,
                "traffic_prev_28d": traffic_prev_28d,
                "traffic_drop_pct": traffic_drop_pct,
                "decay_score": round(100 - (fresh * 0.5 + depth * 0.2 + imp * 0.2 + health * 0.1), 1),
                "priority_score": priority,
                "action": action,
                "reason": reason,
                "last_crawled": meta["last_crawled"],
            })
            time.sleep(CRAWL_DELAY_SECONDS)

    if not args.dry_run and all_rows:
        cols = list(all_rows[0].keys())
        placeholders = ",".join("?" * len(cols))
        con.executemany(
            f"INSERT OR REPLACE INTO freshness_scores({','.join(cols)}) VALUES ({placeholders})",
            [tuple(r[c] for c in cols) for r in all_rows],
        )
        con.commit()
        print(f"\nWrote {len(all_rows)} rows to freshness_scores for {day}")
        supabase_upsert("freshness_scores", all_rows)

    con.close()


def main():
    ap = argparse.ArgumentParser(description="Content Freshness / Decay Monitor")
    ap.add_argument("--dry-run", action="store_true", help="Show what would be crawled; no network")
    ap.add_argument("--force", action="store_true", help="Run even if already ran this month")
    ap.add_argument("--limit", type=int, default=MAX_PAGES_PER_SITEMAP,
                    help=f"Max URLs per sitemap (default {MAX_PAGES_PER_SITEMAP})")
    ap.add_argument("--property", help="Only run for this property")
    ap.add_argument("--page-type", help="Only run for this page type (e.g. blog, page)")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
