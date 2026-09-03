#!/usr/bin/env python3
"""
screamingfrog_site_audit.py — Screaming Frog SEO Spider provider for Orbit.

Runs the Screaming Frog SEO Spider CLI in headless mode, exports the key
audit tabs as CSV, and maps the findings into the existing site_audit
schema so the dashboard can consume them.

Requires:
- SCREAMING_FROG_BIN env var, or a default install location.
- SCREAMING_FROG_LICENCE env var for headless crawls > 500 URLs.

Reads: site_audit.PROPERTIES for domain mapping.
Writes: site_audit_runs, site_audit_pages, site_audit_issues via save() in site_audit.py.
"""
import csv
import glob
import os
import platform
import re
import shutil
import subprocess
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urljoin, urlparse

from common import load_env

# ------------------------------------------------------------------------- config
MAX_CRAWL_PAGES = 2000
CLI_TIMEOUT_SECONDS = 3600  # 1 hour for large crawls

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
    "multiple_title_tags": "warning",
    "heading_hierarchy_error": "info",
    "missing_viewport": "warning",
    "thin_content": "info",
    "missing_alt_text": "warning",
    "mixed_content": "warning",
    "missing_structured_data": "info",
    "duplicate_title": "warning",
    "duplicate_meta_description": "warning",
    "duplicate_h1": "warning",
    "duplicate_content": "warning",
    "internal_link_4xx": "critical",
    "internal_link_redirect": "info",
    "external_link_4xx": "info",
    "slow_lcp": "warning",
    "poor_cls": "warning",
    "structured_data_error": "warning",
    "structured_data_warning": "info",
    "sitemap_url_not_crawled": "warning",
    "crawled_url_not_in_sitemap": "info",
    "orphan_page": "warning",
    "render_blocking_resources": "info",
}

EXPORT_TABS = [
    "Internal:All",
    "Response Codes:Internal Client Error (4xx)",
    "Response Codes:Internal Server Error (5xx)",
    "Response Codes:Internal Redirection (3xx)",
    "Response Codes:Internal Redirect Chain",
    "Response Codes:Internal Redirect Loop",
    "Inlinks:All",
    "External:All",
    "Hreflang:All",
    "Structured Data:Validation Errors",
    "Structured Data:Validation Warnings",
    "Sitemaps:URLs not in Sitemap",
    "Sitemaps:Orphan URLs",
    "Canonicals:All",
    "Page Titles:All",
    "Meta Description:All",
    "H1:All",
]


# ----------------------------------------------------------------------- helpers
def today() -> str:
    return date.today().isoformat()


def _norm_url(url: str) -> str:
    return url.split("#")[0].rstrip("/")


def _domain_from_url(url: str) -> str:
    return urlparse(url).netloc.lower().lstrip("www.")


def _find_binary() -> str:
    env_bin = os.environ.get("SCREAMING_FROG_BIN")
    if env_bin and Path(env_bin).exists():
        return env_bin
    system = platform.system()
    if system == "Darwin":
        default = "/Applications/Screaming Frog SEO Spider.app/Contents/MacOS/ScreamingFrogSEOSpiderLauncher"
    else:
        default = "/usr/bin/screamingfrogseospider"
    if Path(default).exists():
        return default
    # fallback to PATH
    path_bin = shutil.which("screamingfrogseospider")
    if path_bin:
        return path_bin
    raise FileNotFoundError("Screaming Frog SEO Spider binary not found. Set SCREAMING_FROG_BIN.")


def _activate_licence(licence: str):
    """Write the licence file so headless mode can use it."""
    home = Path.home()
    sf_dir = home / ".ScreamingFrogSEOSpider"
    sf_dir.mkdir(parents=True, exist_ok=True)
    (sf_dir / "licence.txt").write_text(licence.strip(), encoding="utf-8")


def _load_env():
    load_env()


# ----------------------------------------------------------------------- crawling
def _build_crawl_args(
    binary: str,
    domain: str,
    output_dir: Path,
    sitemaps: list,
    limit: int = 0,
) -> List[str]:
    args = [binary, "--headless", "--save-crawl", "--overwrite",
            "--output-folder", str(output_dir),
            "--export-format", "csv",
            "--export-tabs", ",".join(EXPORT_TABS)]

    if limit:
        # Build a crawl list limited to the first N URLs from the configured sitemaps.
        urls = []
        from site_audit import parse_sitemap
        for _, _, sm_url, pattern in sitemaps:
            for u, _ in parse_sitemap(sm_url, limit=limit):
                if pattern and not re.search(pattern, u):
                    continue
                urls.append(u)
                if len(urls) >= limit:
                    break
            if len(urls) >= limit:
                break
        urls = list(dict.fromkeys(urls))[:limit]
        if not urls:
            raise RuntimeError(f"No URLs found for Screaming Frog crawl-list")
        list_file = output_dir / "crawl-list.txt"
        list_file.write_text("\n".join(urls) + "\n", encoding="utf-8")
        args.extend(["--crawl-list", str(list_file)])
    elif sitemaps:
        # Use the first sitemap as the crawl seed.
        args.extend(["--crawl-sitemap", sitemaps[0][2]])
    else:
        args.extend(["--crawl", f"https://{domain}"])
    return args


def _run_sf(cli_args: List[str], timeout: int = CLI_TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
    print(f"  running: {' '.join(cli_args[:5])} ...")
    proc = subprocess.run(cli_args, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        return proc
    # Surface licence / fatal errors even when exit code is 0
    combined = (proc.stdout or "") + (proc.stderr or "")
    if "licence expired" in combined.lower() or "failed to start" in combined.lower():
        proc.returncode = 1
    return proc


def _find_export_file(output_dir: Path, tab: str) -> Path:
    """Screaming Frog sanitises tab names into filenames. Try a few variants."""
    safe = tab.replace(":", "_").replace(" ", "_").replace("(", "").replace(")", "")
    candidates = [
        output_dir / f"{safe}.csv",
        output_dir / f"{tab.replace(':', '_').replace(' ', '_')}.csv",
    ]
    # also allow Screaming Frog's own sanitisation (e.g. ampersand, slashes)
    for cand in candidates:
        if cand.exists():
            return cand
    # last resort: scan CSV filenames for the tab tail (case-insensitive)
    tab_tail = tab.split(":")[-1].replace(" ", "_").replace("(", "").replace(")", "").lower()
    for p in output_dir.glob("*.csv"):
        if tab_tail in p.name.lower():
            return p
    return None


def _read_csv(path: Path) -> List[dict]:
    if not path or not path.exists():
        return []
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return list(csv.DictReader(f))


def _header_map(row: dict) -> Dict[str, str]:
    """Map messy Screaming Frog CSV headers to normalised keys."""
    mapping = {}
    for k in row.keys():
        if k is None:
            continue
        norm = k.strip().lower().replace(" ", "_").replace("/", "_").replace("-", "_")
        mapping[norm] = k
    return mapping


def _val(row: dict, header_map: Dict[str, str], *keys: str) -> str:
    for k in keys:
        if k in header_map:
            v = row.get(header_map[k], "")
            if v is not None:
                return str(v).strip()
    return ""


def _int(row: dict, header_map: Dict[str, str], *keys: str) -> int:
    v = _val(row, header_map, *keys)
    if not v:
        return 0
    try:
        return int(float(v.replace(",", "")))
    except ValueError:
        return 0


def _float(row: dict, header_map: Dict[str, str], *keys: str) -> float:
    v = _val(row, header_map, *keys)
    if not v:
        return 0.0
    try:
        return float(v.replace(",", ""))
    except ValueError:
        return 0.0


# --------------------------------------------------------------------- page data
def _parse_internal_csv(path: Path) -> Dict[str, dict]:
    """Return url_norm -> page metrics from Internal:All export."""
    pages = {}
    for row in _read_csv(path):
        h = _header_map(row)
        address = _val(row, h, "address", "url", "uri")
        if not address:
            continue
        norm = _norm_url(address)
        title = _val(row, h, "title_1", "title", "page_title")
        meta = _val(row, h, "meta_description_1", "meta_description", "description")
        h1 = _val(row, h, "h1_1", "h1")
        canonical = _val(row, h, "canonical_link_element_1", "canonical")
        status = _int(row, h, "status_code", "status")
        word_count = _int(row, h, "word_count", "words")
        inlinks = _int(row, h, "inlinks", "inlinks_all", "total_inlinks")
        outlinks = _int(row, h, "outlinks", "outlinks_all", "total_outlinks")
        resp_time = _int(row, h, "response_time", "response_time_ms", "time_to_first_byte_ms")
        schema_types = _val(row, h, "schema_types", "structured_data_types")
        lh_perf = _int(row, h, "pagespeed_insights_lighthouse_performance", "lighthouse_performance")
        robots = _val(row, h, "meta_robots_1", "robots_meta")
        xrobots = _val(row, h, "x_robots_tag_1", "x_robots_tag")
        pages[norm] = {
            "url": address,
            "status_code": status,
            "final_url": _val(row, h, "final_redirect_url", "redirect_url") or address,
            "title": title,
            "meta_description": meta,
            "h1": h1,
            "canonical": canonical,
            "canonical_ok": 1 if _norm_url(canonical or address) == norm else 0,
            "word_count": word_count,
            "internal_links": outlinks,
            "external_links": 0,
            "has_viewport": 0,  # not exposed cleanly in CSV
            "redirect_count": _int(row, h, "redirects", "number_of_redirects"),
            "lcp": None,
            "inp": None,
            "cls": None,
            "performance_score": lh_perf if lh_perf else None,
            "seo_score": None,
            "psi_status": "screamingfrog",
            "fetch_error": "",
            # extra metrics
            "inlinks": inlinks,
            "outlinks": outlinks,
            "response_time_ms": resp_time,
            "structured_data_types": schema_types,
            "lighthouse_performance": lh_perf if lh_perf else None,
            "_robots_meta": robots,
            "_x_robots": xrobots,
        }
    return pages


# ---------------------------------------------------------------------- issues
def _response_code_issues(paths: Dict[str, Path]) -> List[dict]:
    issues = []
    issue_map = {
        "Response Codes:Internal Client Error (4xx)": ("status_4xx", "HTTP {}"),
        "Response Codes:Internal Server Error (5xx)": ("status_5xx", "HTTP {}"),
        "Response Codes:Internal Redirection (3xx)": ("redirect_chain", "redirected to {}"),
        "Response Codes:Internal Redirect Chain": ("redirect_chain", "{}"),
        "Response Codes:Internal Redirect Loop": ("redirect_loop", "{}"),
    }
    for tab, (itype, tmpl) in issue_map.items():
        for row in _read_csv(paths.get(tab)):
            h = _header_map(row)
            address = _val(row, h, "address", "url")
            if not address:
                continue
            status = _int(row, h, "status_code", "status")
            detail = tmpl.format(status)
            if itype == "redirect_chain":
                detail = _val(row, h, "redirect_url", "final_redirect_url") or detail
            issues.append({
                "url": address,
                "type": itype,
                "severity": ISSUE_SEVERITY[itype],
                "details": detail,
            })
    return issues


def _canonical_issues(path: Path) -> List[dict]:
    issues = []
    for row in _read_csv(path):
        h = _header_map(row)
        address = _val(row, h, "address", "url")
        canonical = _val(row, h, "canonical_link_element_1", "canonical")
        if not address:
            continue
        if not canonical:
            issues.append({"url": address, "type": "missing_canonical",
                           "severity": ISSUE_SEVERITY["missing_canonical"], "details": ""})
        elif _norm_url(canonical) != _norm_url(address):
            issues.append({"url": address, "type": "canonical_mismatch",
                           "severity": ISSUE_SEVERITY["canonical_mismatch"],
                           "details": f"canonical={canonical}"})
    return issues


def _meta_issues(title_path: Path, meta_path: Path, h1_path: Path) -> List[dict]:
    issues = []

    def _dupes(path: Path, itype: str, value_key: str):
        buckets = {}
        for row in _read_csv(path):
            h = _header_map(row)
            address = _val(row, h, "address", "url")
            val = _val(row, h, value_key)
            if address and val:
                buckets.setdefault(val, []).append(address)
        out = []
        for val, urls in buckets.items():
            if len(urls) > 1:
                for url in urls:
                    out.append({"url": url, "type": itype,
                                "severity": ISSUE_SEVERITY[itype],
                                "details": f"shared with {len(urls)-1} other page(s)"})
        return out

    issues.extend(_dupes(title_path, "duplicate_title", "title_1"))
    issues.extend(_dupes(meta_path, "duplicate_meta_description", "meta_description_1"))
    issues.extend(_dupes(h1_path, "duplicate_h1", "h1_1"))

    for row in _read_csv(h1_path):
        h = _header_map(row)
        address = _val(row, h, "address", "url")
        h1_count = _int(row, h, "h1_count", "h1_1_count")
        if address and h1_count > 1:
            issues.append({"url": address, "type": "multiple_h1",
                           "severity": ISSUE_SEVERITY["multiple_h1"],
                           "details": f"{h1_count} H1s"})

    for row in _read_csv(title_path):
        h = _header_map(row)
        address = _val(row, h, "address", "url")
        title_len = _int(row, h, "title_1_length", "title_length")
        if address and title_len > 60:
            issues.append({"url": address, "type": "title_too_long",
                           "severity": ISSUE_SEVERITY["title_too_long"],
                           "details": f"{title_len} chars"})

    for row in _read_csv(meta_path):
        h = _header_map(row)
        address = _val(row, h, "address", "url")
        meta_len = _int(row, h, "meta_description_1_length", "meta_description_length")
        if address and meta_len > 160:
            issues.append({"url": address, "type": "meta_description_too_long",
                           "severity": ISSUE_SEVERITY["meta_description_too_long"],
                           "details": f"{meta_len} chars"})

    return issues


def _link_issues(inlinks_path: Path, external_path: Path) -> List[dict]:
    issues = []
    for row in _read_csv(inlinks_path):
        h = _header_map(row)
        source = _val(row, h, "source", "from")
        dest = _val(row, h, "destination", "to")
        status = _int(row, h, "status_code", "status")
        if not source or not dest:
            continue
        if 400 <= status < 600:
            issues.append({"url": source, "type": "internal_link_4xx",
                           "severity": ISSUE_SEVERITY["internal_link_4xx"],
                           "details": f"{dest} (HTTP {status})"})
        elif 300 <= status < 400:
            issues.append({"url": source, "type": "internal_link_redirect",
                           "severity": ISSUE_SEVERITY["internal_link_redirect"],
                           "details": f"{dest} → HTTP {status}"})

    for row in _read_csv(external_path):
        h = _header_map(row)
        source = _val(row, h, "source", "from")
        dest = _val(row, h, "destination", "to")
        status = _int(row, h, "status_code", "status")
        if not source or not dest:
            continue
        if 400 <= status < 600:
            issues.append({"url": source, "type": "external_link_4xx",
                           "severity": ISSUE_SEVERITY["external_link_4xx"],
                           "details": f"{dest} (HTTP {status})"})
    return issues


def _hreflang_issues(path: Path) -> List[dict]:
    issues = []
    graph = {}
    self_refs = {}
    for row in _read_csv(path):
        h = _header_map(row)
        source = _val(row, h, "url", "address", "source")
        target = _val(row, h, "hreflang_url", "target_url", "target")
        code = _val(row, h, "hreflang", "language_region")
        status = _int(row, h, "hreflang_status_code", "status_code")
        is_valid = _val(row, h, "valid", "is_valid").lower() in ("true", "yes", "1")
        if not source or not target:
            continue
        source_norm = _norm_url(source)
        target_norm = _norm_url(target)
        if not is_valid:
            issues.append({"url": source, "type": "hreflang_invalid_code",
                           "severity": ISSUE_SEVERITY["hreflang_invalid_code"],
                           "details": f"{code} → {target}"})
        if status >= 400:
            issues.append({"url": source, "type": "hreflang_non_200",
                           "severity": ISSUE_SEVERITY["hreflang_non_200"],
                           "details": f"{code} → {target} (HTTP {status})"})
        graph.setdefault(source_norm, {})[target_norm] = code
        if source_norm == target_norm:
            self_refs[source_norm] = True

    for source_norm, targets in graph.items():
        if not self_refs.get(source_norm):
            issues.append({"url": source_norm, "type": "hreflang_missing_self_reference",
                           "severity": ISSUE_SEVERITY["hreflang_missing_self_reference"],
                           "details": ""})
        for target_norm, code in targets.items():
            if target_norm == source_norm or target_norm not in graph:
                continue
            if source_norm not in graph.get(target_norm, {}):
                issues.append({"url": source_norm, "type": "hreflang_missing_return_tag",
                               "severity": ISSUE_SEVERITY["hreflang_missing_return_tag"],
                               "details": f"{code} → {target_norm}"})
    return issues


def _structured_data_issues(error_path: Path, warn_path: Path) -> List[dict]:
    issues = []
    for row in _read_csv(error_path):
        h = _header_map(row)
        url = _val(row, h, "url", "address")
        schema = _val(row, h, "structured_data_type", "schema_type", "type")
        detail = _val(row, h, "error", "error_text", "description")
        if url:
            issues.append({"url": url, "type": "structured_data_error",
                           "severity": ISSUE_SEVERITY["structured_data_error"],
                           "details": f"{schema}: {detail}"})
    for row in _read_csv(warn_path):
        h = _header_map(row)
        url = _val(row, h, "url", "address")
        schema = _val(row, h, "structured_data_type", "schema_type", "type")
        detail = _val(row, h, "warning", "warning_text", "description")
        if url:
            issues.append({"url": url, "type": "structured_data_warning",
                           "severity": ISSUE_SEVERITY["structured_data_warning"],
                           "details": f"{schema}: {detail}"})
    return issues


def _sitemap_issues(not_in_sitemap_path: Path, orphan_path: Path) -> List[dict]:
    issues = []
    for row in _read_csv(not_in_sitemap_path):
        h = _header_map(row)
        url = _val(row, h, "url", "address")
        if url:
            issues.append({"url": url, "type": "crawled_url_not_in_sitemap",
                           "severity": ISSUE_SEVERITY["crawled_url_not_in_sitemap"],
                           "details": ""})
    for row in _read_csv(orphan_path):
        h = _header_map(row)
        url = _val(row, h, "url", "address")
        if url:
            issues.append({"url": url, "type": "sitemap_url_not_crawled",
                           "severity": ISSUE_SEVERITY["sitemap_url_not_crawled"],
                           "details": "orphan URL in sitemap"})
    return issues


# -------------------------------------------------------------------------- run
def run_for_property(property: str, sitemaps: list, limit: int = 0) -> Tuple[dict, List[dict], List[dict]]:
    """Run a Screaming Frog audit for one property."""
    _load_env()
    from site_audit import PROPERTIES

    start_time = time.time()
    domain = PROPERTIES.get(property, {}).get("domain", property)
    licence = os.environ.get("SCREAMING_FROG_LICENCE", "")
    if not licence:
        print("[note] SCREAMING_FROG_LICENCE not set; free 500-URL limit may apply")
    else:
        _activate_licence(licence)

    binary = _find_binary()
    output_dir = Path(tempfile.mkdtemp(prefix=f"sf-{property}-{today()}-"))

    print(f"[{property}] running Screaming Frog headless crawl for {domain}")
    cli_args = _build_crawl_args(binary, domain, output_dir, sitemaps, limit=limit)
    proc = _run_sf(cli_args)
    if proc.returncode != 0:
        # stdout/stderr may be huge; show tail
        tail = (proc.stderr or proc.stdout or "")[-2000:]
        raise RuntimeError(f"Screaming Frog crawl failed (exit {proc.returncode}): {tail}")

    print(f"[{property}] crawl complete; parsing exports from {output_dir}")
    paths = {tab: _find_export_file(output_dir, tab) for tab in EXPORT_TABS}
    missing = [tab for tab, p in paths.items() if not p]
    for tab in missing:
        print(f"  [warn] missing export for {tab}")

    if len(missing) == len(EXPORT_TABS):
        raise RuntimeError(
            "Screaming Frog produced no CSV exports. Common causes: "
            "expired/missing licence, empty crawl list, or unsupported SF version."
        )

    pages = _parse_internal_csv(paths.get("Internal:All"))

    issues = []
    issues.extend(_response_code_issues(paths))
    issues.extend(_canonical_issues(paths.get("Canonicals:All")))
    issues.extend(_meta_issues(paths.get("Page Titles:All"),
                               paths.get("Meta Description:All"),
                               paths.get("H1:All")))
    issues.extend(_link_issues(paths.get("Inlinks:All"), paths.get("External:All")))
    issues.extend(_hreflang_issues(paths.get("Hreflang:All")))
    issues.extend(_structured_data_issues(paths.get("Structured Data:Validation Errors"),
                                          paths.get("Structured Data:Validation Warnings")))
    issues.extend(_sitemap_issues(paths.get("Sitemaps:URLs not in Sitemap"),
                                  paths.get("Sitemaps:Orphan URLs")))

    # Indexability / noindex from Internal export
    for norm, p in pages.items():
        robots = (p.get("_robots_meta") or "") + " " + (p.get("_x_robots") or "")
        if "noindex" in robots.lower():
            issues.append({"url": p["url"], "type": "noindex_robots_meta",
                           "severity": ISSUE_SEVERITY["noindex_robots_meta"],
                           "details": robots.strip()})
        if p.get("inlinks", 0) == 0:
            issues.append({"url": p["url"], "type": "orphan_page",
                           "severity": ISSUE_SEVERITY["orphan_page"],
                           "details": "no internal inlinks"})
        if p.get("word_count", 0) > 0 and p["word_count"] < 300:
            issues.append({"url": p["url"], "type": "thin_content",
                           "severity": ISSUE_SEVERITY["thin_content"],
                           "details": f"{p['word_count']} words"})

    duration = int(time.time() - start_time)
    page_rows = list(pages.values())
    run_row = {
        "day": today(),
        "property": property,
        "pages_crawled": len(page_rows),
        "pages_failed": sum(1 for p in page_rows if p["status_code"] >= 400),
        "issues_found": len(issues),
        "psi_calls": 0,
        "run_duration_seconds": duration,
        "crawl_source": "screamingfrog",
    }
    return run_row, page_rows, issues
