#!/usr/bin/env python3
"""
competitor_tracker.py — crawl competitor sitemaps, hash pages, detect changes.

Reads competitors.csv, fetches each sitemap, discovers URLs, hashes the first
MAX_PAGES_PER_COMPETITOR pages per competitor, and records:
  - competitor_pages: latest page fingerprint (title, meta, h1, schemas, word count, hash)
  - competitor_changes: diff events (new_page, content_update, title_change, meta_change,
    h1_change, schema_change, redirect, page_removed, url_case_change)
  - competitor_snapshots: daily summary per competitor

Usage:
    python3 competitor_tracker.py              # run all properties
    python3 competitor_tracker.py --property vantagecircle  # one property
    python3 competitor_tracker.py --dry-run    # show what would run; no network
    python3 competitor_tracker.py --limit 3    # only first 3 competitors per property
"""
import argparse
import csv
import gzip
import hashlib
import html
import json
import re
import sqlite3
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from common import DB_PATH, init_db, supabase_upsert

HERE = Path(__file__).parent
CONFIG = HERE / "competitors.csv"

# ---- edit these ------------------------------------------------------------
MAX_PAGES_PER_COMPETITOR = 200
REQUEST_TIMEOUT = 25
CRAWL_DELAY_SECONDS = 0.4
WORD_BLOCKLIST = {"script", "style", "nav", "header", "footer", "aside", "noscript"}
# -----------------------------------------------------------------------------

SELF_DOMAINS = {"vantagecircle.com", "vantagefit.io"}


def now():
    return datetime.now(timezone.utc).isoformat()


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:12]


def normalize_url(url: str) -> str:
    """Strip trailing slash and fragment for comparison."""
    u = url.split("#")[0].rstrip("/")
    return u


def fetch(url: str, binary: bool = False):
    """Fetch a URL. Returns (body_bytes_or_text, final_url, status, headers)."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; VantageSEOCompetitorBot/1.0; "
                "+https://www.vantagecircle.com)"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        },
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
            # sniff XML sitemaps by suffix or content start
            text = raw.decode("utf-8", errors="replace")
            return text, final_url, resp.status, headers
    except urllib.error.HTTPError as e:
        return None, url, e.code, {}
    except Exception as e:
        return None, url, 0, {"error": str(e)}


def parse_sitemap(url: str, limit: int = 0):
    """Return list of URLs from a sitemap or sitemap index. Handles gzip files."""
    text, final_url, status, headers = fetch(url, binary=False)
    if text is None:
        print(f"  sitemap fetch failed: {url} (status {status})")
        return []

    is_gzip = url.endswith(".gz") or headers.get("Content-Encoding", "").lower() == "gzip"
    if is_gzip and text is not None:
        # already decompressed by fetch, but xml may have started as gz
        pass

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
            if loc is not None and loc.text:
                urls.append(loc.text.strip())
        elif tag == "sitemap":
            loc = child.find(f"{{{ns}}}loc")
            if loc is not None and loc.text:
                sitemaps.append(loc.text.strip())

    if sitemaps:
        # sitemap index: recurse into child sitemaps
        collected = []
        for sm in sitemaps:
            collected.extend(parse_sitemap(sm, limit=limit))
            if limit and len(collected) >= limit:
                break
        return collected[:limit] if limit else collected

    if limit:
        urls = urls[:limit]
    return urls


class HtmlParser(HTMLParser):
    """Minimal stdlib HTML parser for title, meta, h1, schemas, word count."""

    def __init__(self):
        super().__init__()
        self.title = ""
        self.meta = ""
        self.h1 = ""
        self.schemas = []
        self._in_title = False
        self._in_script = False
        self._script_buffer = []
        self._skip_depth = 0
        self._text_parts = []
        self._current_tag = None

    def _is_blocklist(self, tag):
        return tag.lower() in WORD_BLOCKLIST

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        self._current_tag = tag
        if self._is_blocklist(tag):
            self._skip_depth += 1
            if tag == "script":
                self._in_script = True
                self._script_buffer = []
        attrs = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag == "meta" and attrs.get("name", "").lower() == "description":
            self.meta = attrs.get("content", "").strip()
        if tag == "h1" and not self.h1:
            self._capture_h1 = True
        else:
            self._capture_h1 = False

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self._is_blocklist(tag):
            self._skip_depth -= 1
        if tag == "script" and self._in_script:
            self._in_script = False
            buf = " ".join(self._script_buffer)
            if "application/ld+json" in buf or "@context" in buf:
                for schema in extract_schemas(buf):
                    if schema not in self.schemas:
                        self.schemas.append(schema)
            self._script_buffer = []
        if tag == "title":
            self._in_title = False
        if tag == "h1":
            self._capture_h1 = False
        self._current_tag = None

    def handle_data(self, data):
        if self._in_script:
            self._script_buffer.append(data)
            return
        if self._skip_depth > 0:
            return
        if self._in_title:
            self.title = data.strip()
        if getattr(self, "_capture_h1", False):
            self.h1 = data.strip()
        # collect body text for word count
        if self._current_tag not in ("style", "script"):
            self._text_parts.append(data)

    def word_count(self):
        text = " ".join(self._text_parts)
        text = re.sub(r"[\s\n\r]+", " ", text).strip()
        return len(text.split())

    def parsed(self):
        return {
            "title": self.title,
            "meta": self.meta,
            "h1": self.h1,
            "schemas": self.schemas,
            "word_count": self.word_count(),
        }


def extract_schemas(text: str):
    """Return sorted list of @type values from JSON-LD snippets found in text."""
    schemas = []
    for raw in re.findall(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", text, re.S | re.I):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            t = data.get("@type")
            if isinstance(t, str):
                schemas.append(t)
            elif isinstance(t, list):
                schemas.extend(t)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    t = item.get("@type")
                    if isinstance(t, str):
                        schemas.append(t)
                    elif isinstance(t, list):
                        schemas.extend(t)
    return sorted(set(schemas))


def parse_page(text: str):
    parser = HtmlParser()
    try:
        parser.feed(text)
    except Exception:
        pass
    return parser.parsed()


def content_hash(text: str) -> str:
    """Hash of visible-ish normalized text."""
    clean = re.sub(r"[\s\n\r]+", " ", text).strip().lower()
    return short_hash(clean)


def paragraphs(text: str):
    """Split visible text into paragraph-like blocks."""
    blocks = re.split(r"\n{2,}|<\s*/\s*(?:p|div|section|article|li)\s*>", text, flags=re.I)
    out = []
    for b in blocks:
        b = re.sub(r"<[^>]+>", " ", b)
        b = re.sub(r"[\s\n\r]+", " ", b).strip()
        if len(b) > 40:
            out.append(b)
    return out


def diff_paragraphs(old_text: str, new_text: str):
    old_set = set(paragraphs(old_text))
    new_set = set(paragraphs(new_text))
    added = list(new_set - old_set)
    removed = list(old_set - new_set)
    added.sort(key=len, reverse=True)
    removed.sort(key=len, reverse=True)
    return added[:5], removed[:5]


def read_config(path):
    rows = []
    if not path.exists():
        return rows
    with open(path, encoding="utf-8") as f:
        for rec in csv.reader(f):
            if not rec or rec[0].strip().startswith("#"):
                continue
            if len(rec) < 4:
                continue
            rows.append({
                "property": rec[0].strip(),
                "competitor": rec[1].strip(),
                "domain": rec[2].strip().lower(),
                "sitemap_url": rec[3].strip(),
            })
    return rows


def load_previous_pages(con, property, competitor):
    cur = con.execute(
        "SELECT url, title, meta, h1, schemas, word_count, content_hash, first_seen "
        "FROM competitor_pages WHERE property=? AND competitor=?",
        (property, competitor),
    )
    rows = {}
    for url, title, meta, h1, schemas, wc, chash, first_seen in cur.fetchall():
        rows[normalize_url(url)] = {
            "url": url,
            "title": title or "",
            "meta": meta or "",
            "h1": h1 or "",
            "schemas": json.loads(schemas) if schemas else [],
            "word_count": wc or 0,
            "content_hash": chash or "",
            "first_seen": first_seen,
        }
    return rows


def section_of(url: str):
    """First non-locale path segment."""
    locale = {"en", "fr", "es", "de", "it", "pt", "ja", "ko", "zh",
              "en-us", "en-gb", "en-au", "en-in", "en-ca", "fr-ca"}
    try:
        p = urlparse(url).path.strip("/").split("/")
        p = [x for x in p if x]
        if p and p[0].lower() in locale and len(p) > 1:
            p = p[1:]
        return p[0].lower() if p else "home"
    except Exception:
        return "other"


def type_label(change_type: str, count: int = 1):
    labels = {
        "new_page": ("new page", "new pages"),
        "content_update": ("content update", "content updates"),
        "page_removed": ("page removed", "pages removed"),
        "redirect": ("redirect", "redirects"),
        "title_change": ("title change", "title changes"),
        "meta_change": ("meta change", "meta changes"),
        "h1_change": ("H1 change", "H1 changes"),
        "schema_change": ("schema change", "schema changes"),
        "url_case_change": ("URL case change", "URL case changes"),
    }
    pair = labels.get(change_type, (change_type, change_type + "s"))
    return pair[0] if count == 1 else pair[1]


def discover_urls(sitemap_url: str, limit: int):
    raw_urls = parse_sitemap(sitemap_url, limit=limit * 2 if limit else 0)
    seen = set()
    urls = []
    for u in raw_urls:
        nu = normalize_url(u)
        if nu in seen:
            continue
        seen.add(nu)
        urls.append(u)
        if limit and len(urls) >= limit:
            break
    return urls


def crawl_one(url: str):
    """Return (parsed dict, final_url, status) or None on failure."""
    text, final_url, status, _ = fetch(url)
    if text is None:
        return None, final_url, status
    parsed = parse_page(text)
    parsed["url"] = url
    parsed["final_url"] = final_url
    parsed["status"] = status
    parsed["text"] = text
    return parsed, final_url, status


def run_property(con, cfg_rows, args):
    property = cfg_rows[0]["property"]
    print(f"\n=== {property} ===")
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ts = now()
    page_rows = []
    change_rows = []
    snapshot_rows = []

    for row in cfg_rows:
        competitor = row["competitor"]
        domain = row["domain"]
        sitemap_url = row["sitemap_url"]
        is_self = domain in SELF_DOMAINS
        print(f"\n{competitor} ({domain})")

        prev = load_previous_pages(con, property, competitor)
        print(f"  previous pages: {len(prev)}")

        urls = discover_urls(sitemap_url, limit=MAX_PAGES_PER_COMPETITOR)
        print(f"  discovered: {len(urls)} URLs")

        hashed = 0
        failures = 0
        current_norms = set()
        change_count = 0

        for url in urls:
            norm = normalize_url(url)
            current_norms.add(norm)
            parsed, final_url, status = crawl_one(url)
            if parsed is None:
                failures += 1
                continue
            hashed += 1

            # detect redirect (final url differs meaningfully)
            redirect_to = None
            if normalize_url(final_url) != norm and urlparse(final_url).path != urlparse(url).path:
                redirect_to = final_url

            chash = content_hash(parsed["text"])
            old = prev.get(norm)

            changes_for_page = []

            if old is None:
                details = {
                    "word_count": parsed["word_count"],
                    "h1": parsed["h1"],
                    "schemas": parsed["schemas"],
                }
                changes_for_page.append(("new_page", details))
            else:
                # redirects
                if redirect_to:
                    changes_for_page.append(("redirect", {
                        "status_code": status,
                        "redirect_to": redirect_to,
                    }))
                # title change
                if parsed["title"] != old["title"]:
                    changes_for_page.append(("title_change", {
                        "old_title": old["title"],
                        "new_title": parsed["title"],
                    }))
                # meta change
                if parsed["meta"] != old["meta"]:
                    changes_for_page.append(("meta_change", {
                        "old_meta": old["meta"],
                        "new_meta": parsed["meta"],
                    }))
                # h1 change
                if parsed["h1"] != old["h1"]:
                    changes_for_page.append(("h1_change", {
                        "old_h1": old["h1"],
                        "new_h1": parsed["h1"],
                    }))
                # schema change
                old_schemas = set(old["schemas"])
                new_schemas = set(parsed["schemas"])
                if old_schemas != new_schemas:
                    changes_for_page.append(("schema_change", {
                        "added_schemas": sorted(new_schemas - old_schemas),
                        "removed_schemas": sorted(old_schemas - new_schemas),
                    }))
                # content update by hash
                if chash != old["content_hash"]:
                    added, removed = diff_paragraphs(old.get("text", ""), parsed["text"])
                    details = {
                        "old_hash": old["content_hash"],
                        "new_hash": chash,
                        "word_count_change": parsed["word_count"] - old["word_count"],
                        "old_word_count": old["word_count"],
                        "new_word_count": parsed["word_count"],
                    }
                    if added or removed:
                        details["added"] = added
                        details["removed"] = removed
                        details["added_total"] = len(added)
                        details["removed_total"] = len(removed)
                    changes_for_page.append(("content_update", details))

            # url case change: same norm but URL casing changed
            if old is not None and old["url"] != url and normalize_url(old["url"]) == norm:
                changes_for_page.append(("url_case_change", {
                    "old_url": old["url"],
                    "new_url": url,
                }))

            # persist page fingerprint
            first_seen = old["first_seen"] if old else ts
            con.execute(
                """INSERT INTO competitor_pages
                   (property, competitor, domain, url, last_seen, title, meta, h1, schemas,
                    word_count, content_hash, first_seen)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(property, competitor, url) DO UPDATE SET
                   last_seen=excluded.last_seen, title=excluded.title, meta=excluded.meta,
                   h1=excluded.h1, schemas=excluded.schemas, word_count=excluded.word_count,
                   content_hash=excluded.content_hash""",
                (property, competitor, domain, url, ts, parsed["title"], parsed["meta"],
                 parsed["h1"], json.dumps(parsed["schemas"]), parsed["word_count"], chash,
                 first_seen),
            )
            page_rows.append({
                "property": property,
                "competitor": competitor,
                "domain": domain,
                "url": url,
                "last_seen": ts,
                "title": parsed["title"],
                "meta": parsed["meta"],
                "h1": parsed["h1"],
                "schemas": json.dumps(parsed["schemas"]),
                "word_count": parsed["word_count"],
                "content_hash": chash,
                "first_seen": first_seen,
            })

            # write change events
            for change_type, details in changes_for_page:
                chg_id = "chg_" + short_hash(f"{property}:{competitor}:{norm}:{change_type}:{ts}")
                con.execute(
                    """INSERT OR REPLACE INTO competitor_changes
                       (id, timestamp, property, competitor, domain, url, change_type, title,
                        details_json)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (chg_id, ts, property, competitor, domain, url, change_type,
                     parsed["title"], json.dumps(details)),
                )
                change_rows.append({
                    "id": chg_id,
                    "timestamp": ts,
                    "property": property,
                    "competitor": competitor,
                    "domain": domain,
                    "url": url,
                    "change_type": change_type,
                    "title": parsed["title"],
                    "details_json": json.dumps(details),
                })
                change_count += 1

            if hashed % 25 == 0:
                print(f"    crawled {hashed}...")
            time.sleep(CRAWL_DELAY_SECONDS)

        # detect removed pages
        removed_norms = set(prev.keys()) - current_norms
        for norm in removed_norms:
            old = prev[norm]
            chg_id = "chg_" + short_hash(f"{property}:{competitor}:{norm}:page_removed:{ts}")
            details = {"missing_runs": 1, "last_word_count": old["word_count"]}
            con.execute(
                """INSERT OR REPLACE INTO competitor_changes
                   (id, timestamp, property, competitor, domain, url, change_type, title,
                    details_json)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (chg_id, ts, property, competitor, domain, old["url"], "page_removed",
                 old["title"], json.dumps(details)),
            )
            change_rows.append({
                "id": chg_id,
                "timestamp": ts,
                "property": property,
                "competitor": competitor,
                "domain": domain,
                "url": old["url"],
                "change_type": "page_removed",
                "title": old["title"],
                "details_json": json.dumps(details),
            })
            # keep the page row but update last_seen? no, leave it; it will be re-added if it returns
            change_count += 1

        con.execute(
            """INSERT OR REPLACE INTO competitor_snapshots
               (day, property, competitor, domain, total_urls, last_crawl, last_successful_crawl,
                pages_hashed, hash_failures)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (day, property, competitor, domain, len(urls), ts, ts if hashed else None,
             hashed, failures),
        )
        snapshot_rows.append({
            "day": day,
            "property": property,
            "competitor": competitor,
            "domain": domain,
            "total_urls": len(urls),
            "last_crawl": ts,
            "last_successful_crawl": ts if hashed else None,
            "pages_hashed": hashed,
            "hash_failures": failures,
        })
        con.commit()
        print(f"  hashed: {hashed}, failures: {failures}, changes: {change_count}")

    supabase_upsert("competitor_pages", page_rows)
    supabase_upsert("competitor_changes", change_rows)
    supabase_upsert("competitor_snapshots", snapshot_rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--property", help="Run one property only")
    ap.add_argument("--dry-run", action="store_true", help="Print config and exit")
    ap.add_argument("--limit", type=int, default=0, help="Limit competitors per property")
    args = ap.parse_args()

    config = read_config(CONFIG)
    if not config:
        print("No competitors configured. Add rows to competitors.csv")
        return

    if args.dry_run:
        for r in config:
            print(r)
        return

    con = init_db()

    # group by property
    groups = {}
    for r in config:
        groups.setdefault(r["property"], []).append(r)

    if args.property:
        if args.property not in groups:
            print(f"Unknown property: {args.property}. Available: {', '.join(groups)}")
            return
        groups = {args.property: groups[args.property]}

    if args.limit:
        for prop in groups:
            groups[prop] = groups[prop][:args.limit]

    for cfg_rows in groups.values():
        run_property(con, cfg_rows, args)

    con.close()
    print("\nCompetitor tracker run complete.")


if __name__ == "__main__":
    main()
