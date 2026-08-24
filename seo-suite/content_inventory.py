#!/usr/bin/env python3
"""
content_inventory.py — Sync content repos into the SEO Suite content engine.

Reads Markdown frontmatter from Astro content repos and upserts a unified
content_inventory table in Supabase. The table becomes the source of truth for
the Content Engine dashboard: inventory, pipeline, clusters, and performance.

Usage:
    python3 content_inventory.py --dry-run              # preview counts
    python3 content_inventory.py                        # sync all configured repos
    python3 content_inventory.py --repo ../vantagecircle-astro/content --property vantagecircle
"""
import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import yaml

try:
    from common import supabase_upsert
except Exception as _import_err:  # pragma: no cover - allows dry-run without deps
    def supabase_upsert(table, rows, batch_size=500):
        print(f"[supabase] would upsert {len(rows)} rows to {table}")

HERE = Path(__file__).parent
CONFIG = HERE / "content_repos.csv"

# ----------------------------------------------------------------------------- config

TYPE_URL_RULES = {
    # content_dir: (url_builder_func_name, ...)
    "posts": lambda lang, slug, **_kw: f"/{lang}/blog/{slug}/",
    "casestudy": lambda lang, slug, **_kw: f"{lang_prefix(lang)}/case-study/{slug}/",
    "comparisons": lambda lang, slug, **_kw: f"{lang_prefix(lang)}/comparisons/{slug}/",
    "glossaries": lambda lang, slug, **_kw: f"{lang_prefix(lang)}/glossaries/{slug}/",
    "help": lambda lang, slug, **_kw: f"{lang_prefix(lang)}/help/{slug}/",
    "news": lambda lang, slug, **_kw: f"{lang_prefix(lang)}/in-the-news/{slug}/",
    "pages": lambda lang, slug, **_kw: f"{lang_prefix(lang)}/{slug}/",
    "podcasts": lambda lang, slug, **_kw: f"/{lang}/blog/podcasts/vantage-influencers/{slug}/",
    "product-updates": lambda lang, slug, **_kw: f"{lang_prefix(lang)}/product-updates/{slug}/",
    "recognition-templates": lambda lang, slug, **_kw: f"{lang_prefix(lang)}/recognition-templates/{slug}/",
    "reports": lambda lang, slug, wp_type=None, **_kw: report_url(lang, slug, wp_type),
    "resources": lambda lang, slug, **_kw: f"{lang_prefix(lang)}/resources/{slug}/",
    "survey-templates": lambda lang, slug, **_kw: f"{lang_prefix(lang)}/survey-templates/{slug}/",
    "webinars": lambda lang, slug, wp_type=None, **_kw: webinar_url(lang, slug, wp_type),
}

WEBINAR_SERIES_MAP = {
    "doers-series": "vantage-doers-webinar-series",
    "vucap-2021": "vucap-series-2021",
    "vptwebcast-usa": "vantage-point-webcast-usa",
    "vptwebcast-usa-s2": "vantage-point-webcast-usa-s2",
    "vptwebcast-india": "vantage-point-webcast-in",
    "vpt-with-dave": "vantage-point-webcast-with-dave-ulrich",
    "webinar-with-john": "webinar-with-john",
    "webinar-with-partha": "webinar-with-partha-neog",
}


def lang_prefix(lang: str) -> str:
    return "" if lang == "en" else f"/{lang}"


def report_url(lang: str, slug: str, wp_type: str | None) -> str:
    prefix = lang_prefix(lang)
    if wp_type == "research-reports":
        return f"{prefix}/recognition-and-rewards-reports/{slug}/"
    return f"{prefix}/hr-academy/industry-reports/{slug}/"


def webinar_url(lang: str, slug: str, wp_type: str | None) -> str:
    prefix = lang_prefix(lang)
    series = WEBINAR_SERIES_MAP.get(wp_type or "")
    if series:
        return f"{prefix}/webinars/{series}/{slug}/"
    return f"{prefix}/webinars/{slug}/"


def discover_repos():
    """Return list of (repo_path, property, site) from config or defaults."""
    repos = []
    if CONFIG.exists():
        import csv
        with CONFIG.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                path = Path(row["repo_path"]).expanduser()
                if not path.is_absolute():
                    path = HERE / path
                repos.append((path, row.get("property", "vantagecircle").strip(), row.get("site", "").strip()))
    candidates = [
        HERE.parent.parent / "vantagecircle-astro" / "content",
        HERE.parent / "vantagecircle-astro" / "content",
    ]
    for default in candidates:
        if default.exists() and not repos:
            repos.append((default, "vantagecircle", "https://www.vantagecircle.com"))
            break
    return repos


# ----------------------------------------------------------------------------- parsing

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
HTML_A_RE = re.compile(r'<a[^>]+href=["\']([^"\']+)["\']', re.IGNORECASE)
SELF_DOMAINS = {"www.vantagecircle.com", "vantagecircle.com", "www.vantagefit.io", "vantagefit.io", "blog.vantagecircle.com"}


def parse_frontmatter(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    meta = {}
    body = text
    m = FRONTMATTER_RE.match(text)
    if m:
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            meta = {}
        body = text[m.end():]
    return meta, body


def first_date(*values):
    for v in values:
        if not v:
            continue
        if isinstance(v, datetime):
            return v.date().isoformat()
        if isinstance(v, str):
            return v[:10]
    return None


def link_counts(body: str):
    internal = 0
    external = 0
    for match in LINK_RE.finditer(body):
        href = match.group(2).strip()
        internal, external = _classify_link(href, internal, external)
    for href in HTML_A_RE.findall(body):
        internal, external = _classify_link(href, internal, external)
    return internal, external


def _classify_link(href: str, internal: int, external: int):
    href = href.split("#")[0].strip()
    if not href or href.startswith("mailto:") or href.startswith("tel:"):
        return internal, external
    if href.startswith("/") and not href.startswith("//"):
        return internal + 1, external
    netloc = urlparse(href).netloc.lower().lstrip("www.")
    if netloc in {d.lstrip("www.") for d in SELF_DOMAINS}:
        return internal + 1, external
    return internal, external + 1


def content_url(content_type: str, lang: str, slug: str, meta: dict, site: str) -> str:
    if meta.get("canonical"):
        return meta["canonical"].rstrip("/") + "/"
    builder = TYPE_URL_RULES.get(content_type)
    if not builder:
        return ""
    path = builder(lang, slug, wp_type=meta.get("wp_type"))
    if site:
        return (site.rstrip("/") + path).rstrip("/") + "/"
    return path


def property_from_path(repo_path: Path) -> str:
    name = repo_path.name.lower()
    if "vantagefit" in str(repo_path).lower():
        return "vantagefit"
    return "vantagecircle"


# ----------------------------------------------------------------------------- sync

def sync_repo(repo_path: Path, property: str, site: str, dry_run: bool = False):
    rows = []
    files = list(repo_path.rglob("*.md"))
    print(f"[inventory] scanning {repo_path} ({len(files)} .md files)")

    for path in files:
        parts = path.relative_to(repo_path).parts
        if len(parts) < 2:
            continue
        lang = parts[0]
        content_type = parts[1]
        if content_type in ("authors",):
            continue

        meta, body = parse_frontmatter(path)
        slug = meta.get("slug") or path.stem
        title = meta.get("title") or meta.get("meta_title") or slug.replace("-", " ").title()

        url = content_url(content_type, lang, slug, meta, site)
        if not url:
            continue

        authors = meta.get("author") or meta.get("authors") or []
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(",") if a.strip()]
        tags = meta.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        internal, external = link_counts(body)

        rows.append({
            "url": url,
            "property": property,
            "lang": lang,
            "content_type": content_type,
            "slug": slug,
            "title": title,
            "meta_title": meta.get("meta_title") or None,
            "meta_description": meta.get("meta_description") or None,
            "excerpt": meta.get("excerpt") or None,
            "authors": json.dumps(authors) if authors else None,
            "tags": json.dumps(tags) if tags else None,
            "featured": bool(meta.get("featured")),
            "published_date": first_date(meta.get("date")),
            "updated_date": first_date(meta.get("updated"), meta.get("date")),
            "word_count": len(body.split()),
            "internal_links": internal,
            "external_links": external,
            "status": "draft" if meta.get("draft") else "published",
            "repo_path": str(path),
            "content_hash": hashlib.sha256(body.encode("utf-8", "ignore")).hexdigest(),
            "synced_at": datetime.now(timezone.utc).isoformat(),
        })

    print(f"[inventory] {property}: {len(rows)} rows ready")
    if dry_run:
        return rows
    supabase_upsert("content_inventory", rows)
    return rows


def main():
    parser = argparse.ArgumentParser(description="Sync content repos into Supabase")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--repo", type=str, help="Path to a content repo root")
    parser.add_argument("--property", type=str, default="vantagecircle", help="Property name")
    parser.add_argument("--site", type=str, default="https://www.vantagecircle.com", help="Site base URL")
    args = parser.parse_args()

    if args.repo:
        sync_repo(Path(args.repo), args.property, args.site, dry_run=args.dry_run)
    else:
        for repo_path, prop, site in discover_repos():
            sync_repo(repo_path, prop, site or args.site, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
