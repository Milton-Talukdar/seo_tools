#!/usr/bin/env python3
"""
common.py — shared plumbing for every seo-suite module.

- load_env(): DataForSEO credentials from .env (with a fallback to the
  llm-keyword-tracker/.env so both tools share one credential file)
- dfs_post(): DataForSEO API POST with Basic auth + retry
- init_db():  one shared SQLite DB (seo_suite.db), all tables created here
- DASHBOARD_CSS: the dashboard stylesheet, shared by dashboard.py
"""
import base64
import json
import os
import sqlite3
import time
from pathlib import Path
from urllib import request

HERE = Path(__file__).parent
DB_PATH = HERE / "seo_suite.db"
ENV_PATH = HERE / ".env"
FALLBACK_ENV_PATH = HERE.parent / "llm-keyword-tracker" / ".env"

BASE = "https://api.dataforseo.com/v3"


def load_env():
    """Read seo-suite/.env first, then fall back to the llm-keyword-tracker
    .env. CI sets DATAFORSEO_* via the environment instead."""
    for path in (ENV_PATH, FALLBACK_ENV_PATH):
        if not path.exists():
            continue
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
        return


def dfs_post(path, payload, retries=2):
    auth = base64.b64encode(
        f"{os.environ['DATAFORSEO_LOGIN']}:{os.environ['DATAFORSEO_PASSWORD']}".encode()
    ).decode()
    for attempt in range(retries + 1):
        try:
            req = request.Request(
                BASE + path,
                data=json.dumps(payload).encode(),
                headers={"Authorization": "Basic " + auth,
                         "Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req, timeout=180) as r:
                data = json.load(r)
            task = data["tasks"][0]
            if task.get("status_code") != 20000:
                raise RuntimeError(f"DFS {task.get('status_code')}: "
                                   f"{task.get('status_message')}")
            return task.get("result") or []
        except Exception:
            if attempt == retries:
                raise
            time.sleep(3 * (attempt + 1))


def init_db():
    """One DB for the whole suite; every module's table is created here.

    Migrations are additive and guarded by PRAGMA table_info, so an existing
    DB upgrades cleanly on the next run of any module."""
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS rank_snapshots(
        day TEXT, keyword TEXT, property TEXT NOT NULL DEFAULT 'vantagecircle',
        position INTEGER, url TEXT, serp_features TEXT,
        PRIMARY KEY(day, keyword, property));
    CREATE TABLE IF NOT EXISTS keyword_meta(
        property TEXT, keyword TEXT, tag TEXT, volume INTEGER, kd REAL,
        cpc REAL, intent TEXT, branded INTEGER, serp_features TEXT,
        traffic_prev REAL, traffic_cur REAL,
        PRIMARY KEY(property, keyword));
    CREATE TABLE IF NOT EXISTS backlink_snapshots(
        day TEXT, backlinks INTEGER, refdomains INTEGER, rank INTEGER,
        PRIMARY KEY(day));
    CREATE TABLE IF NOT EXISTS refdomain_events(
        day TEXT, event TEXT CHECK(event IN ('new', 'lost')), domain TEXT,
        rank INTEGER,
        PRIMARY KEY(day, event, domain));
    CREATE TABLE IF NOT EXISTS llm_snapshots(
        day TEXT, platform TEXT, prompt TEXT, mentions TEXT,
        cited_mine INTEGER, links TEXT, answer TEXT,
        PRIMARY KEY(day, platform, prompt));
    CREATE TABLE IF NOT EXISTS volumes(
        day TEXT, keyword TEXT, ai_search_volume INTEGER, trend_json TEXT,
        PRIMARY KEY(day, keyword));
    CREATE TABLE IF NOT EXISTS discovered(
        query TEXT PRIMARY KEY, platform TEXT, ai_search_volume INTEGER,
        seed TEXT, first_seen TEXT, last_seen TEXT);
    CREATE TABLE IF NOT EXISTS silent(
        day TEXT, query TEXT, platform TEXT, ai_search_volume INTEGER,
        PRIMARY KEY(day, query, platform));
    CREATE TABLE IF NOT EXISTS keyword_research(
        seed TEXT, source TEXT, keyword TEXT, volume INTEGER, kd REAL,
        cpc REAL, competition REAL, intent TEXT, serp_features TEXT,
        parent_topic TEXT, fetched TEXT,
        PRIMARY KEY(seed, source, keyword));
    CREATE TABLE IF NOT EXISTS seed_overview(
        seed TEXT PRIMARY KEY, volume INTEGER, kd REAL, cpc REAL,
        competition REAL, intent TEXT, serp_features TEXT, fetched TEXT);
    CREATE TABLE IF NOT EXISTS competitor_pages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        property TEXT, competitor TEXT, domain TEXT, url TEXT,
        last_seen TEXT, title TEXT, meta TEXT, h1 TEXT,
        schemas TEXT, word_count INTEGER, content_hash TEXT,
        first_seen TEXT,
        UNIQUE(property, competitor, url));
    CREATE TABLE IF NOT EXISTS competitor_changes(
        id TEXT PRIMARY KEY,
        timestamp TEXT, property TEXT, competitor TEXT, domain TEXT,
        url TEXT, change_type TEXT, title TEXT, details_json TEXT);
    CREATE TABLE IF NOT EXISTS competitor_snapshots(
        day TEXT, property TEXT, competitor TEXT, domain TEXT,
        total_urls INTEGER, last_crawl TEXT, last_successful_crawl TEXT,
        pages_hashed INTEGER, hash_failures INTEGER,
        PRIMARY KEY(day, property, competitor));
    CREATE TABLE IF NOT EXISTS freshness_scores(
        day TEXT, url TEXT, property TEXT, page_type TEXT,
        title TEXT, h1 TEXT, published_date TEXT, modified_date TEXT,
        age_days INTEGER, word_count INTEGER, internal_links INTEGER,
        external_links INTEGER, schema_types TEXT, status_code INTEGER,
        canonical TEXT, freshness_score INTEGER, depth_score INTEGER,
        decay_risk TEXT, target_keyword TEXT, position INTEGER,
        volume INTEGER, rank_drop_30d REAL, rank_drop_60d REAL,
        rank_drop_90d REAL, traffic_28d INTEGER, traffic_prev_28d INTEGER,
        traffic_drop_pct REAL, decay_score REAL, priority_score REAL,
        action TEXT, reason TEXT, last_crawled TEXT,
        PRIMARY KEY(day, url));
    """)
    # v2 migration: rank_snapshots gained a `property` column
    cols = [r[1] for r in con.execute("PRAGMA table_info(rank_snapshots)")]
    if cols and "property" not in cols:
        con.execute("ALTER TABLE rank_snapshots ADD COLUMN property "
                    "TEXT NOT NULL DEFAULT 'vantagecircle'")
    return con


DASHBOARD_CSS = """
:root {
  --bg: #f2f4fa;
  --ink: #0f172a;
  --muted: #64748b;
  --line: #e8ecf4;
  --accent: #4f46e5;
  --accent2: #7c3aed;
  --you: #059669;
  --you-soft: #d1fae5;
  --amber-soft: #fef3c7;
  --amber: #92400e;
  --rose-soft: #ffe4e6;
  --rose: #9f1239;
  --shadow: 0 1px 2px rgba(15,23,42,.05), 0 10px 30px rgba(15,23,42,.06);
}
* { box-sizing: border-box; }
body { font-family: 'Inter', -apple-system, 'Segoe UI', Roboto, sans-serif; margin: 0;
       background: var(--bg); color: var(--ink); -webkit-font-smoothing: antialiased; }
.wrap { max-width: 1060px; margin: 0 auto; padding: 28px 20px 80px; }
.hero { background: linear-gradient(120deg, #312e81 0%, var(--accent) 55%, var(--accent2) 100%);
        border-radius: 20px; padding: 30px 32px; color: #fff; box-shadow: var(--shadow); }
.eyebrow { font-size: 11px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase;
           color: rgba(255,255,255,.65); margin-bottom: 6px; }
h1 { font-size: 26px; font-weight: 800; letter-spacing: -.02em; margin: 0 0 6px; }
.hero .sub { color: rgba(255,255,255,.75); font-size: 13px; }
h2 { font-size: 15px; font-weight: 700; letter-spacing: -.01em; margin: 36px 0 4px;
     display: flex; align-items: center; gap: 9px; }
h2::before { content: ''; width: 4px; height: 17px; border-radius: 2px;
             background: linear-gradient(180deg, var(--accent), var(--accent2)); flex: none; }
h2 .sub { font-weight: 500; }
.sub { color: var(--muted); font-size: 13px; }
.card { background: #fff; border: 1px solid var(--line); border-radius: 16px;
        padding: 20px 22px; margin-top: 14px; box-shadow: var(--shadow); }
.card > b { font-size: 14px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; margin-top: 8px; }
th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--line); }
tr:last-child td { border-bottom: none; }
tbody tr:hover, tr:hover td { background: #f8fafc; }
th { color: var(--muted); font-weight: 600; font-size: 11px; letter-spacing: .05em;
     text-transform: uppercase; }
.bar { height: 10px; border-radius: 999px; background: #eceef5; min-width: 60px; overflow: hidden; }
.bar > div { height: 10px; border-radius: 999px; background: linear-gradient(90deg, #c3cadf, #94a3b8);
             transition: width .6s ease; }
.bar.you > div { background: linear-gradient(90deg, #34d399, var(--you)); }
.chip { display: inline-block; padding: 3px 10px; margin: 2px 3px 2px 0; border-radius: 999px;
        background: #eef1f6; color: #475569; font-size: 11.5px; font-weight: 600; }
.chip.you { background: var(--you-soft); color: #047857; }
.chip.cite { background: var(--amber-soft); color: var(--amber); }
.chip.none { background: var(--rose-soft); color: var(--rose); }
.chip.tracked { background: var(--you-soft); color: #047857; }
details { margin-top: 12px; }
summary { cursor: pointer; display: inline-block; padding: 7px 14px; font-size: 12.5px;
          font-weight: 600; color: #475569; background: #eef1f6; border-radius: 8px;
          user-select: none; transition: background .15s ease; list-style: none; }
summary::-webkit-details-marker { display: none; }
summary::before { content: '▸ '; }
details[open] summary::before { content: '▾ '; }
summary:hover { background: #e2e8f0; }
.answer { white-space: pre-wrap; font-size: 12.5px; line-height: 1.55; color: #334155;
          background: #f8fafc; border: 1px solid var(--line); border-radius: 12px;
          padding: 12px 14px; margin: 8px 0 16px; max-height: 320px; overflow-y: auto; }
.plat { font-weight: 700; font-size: 12.5px; color: #334155; display: inline-block; min-width: 95px; }
.spark { display: inline-flex; align-items: flex-end; gap: 2px; height: 18px; }
.spark i { display: block; width: 7px; background: #a5b4fc; border-radius: 2px; }
.vol { font-weight: 700; color: var(--ink); }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 14px; margin-top: 16px; }
.kpi { background: #fff; border: 1px solid var(--line); border-radius: 14px;
       padding: 18px 20px; box-shadow: var(--shadow); }
.kpi .num { font-size: 30px; font-weight: 800; letter-spacing: -.02em; color: var(--accent);
            line-height: 1.1; }
.kpi .num .sub { font-size: 16px; font-weight: 600; }
.kpi .label { color: var(--muted); font-size: 12px; margin-top: 6px; line-height: 1.45; }
.delta { font-size: 12px; font-weight: 700; }
.delta.up { color: var(--you); }
.delta.down { color: var(--rose); }
.lead-row { display: flex; align-items: center; gap: 12px; margin: 8px 0; font-size: 13px; }
.lead-row .name { min-width: 155px; font-weight: 500; }
.lead-row .bar { flex: 1; }
.lead-row b { min-width: 40px; text-align: right; }
.insights { margin: 14px 0 0; padding-left: 20px; }
.insights li { margin: 8px 0; font-size: 14px; color: #334155; line-height: 1.5; }
.insights li::marker { color: var(--accent); }
code { background: #eef1f6; padding: 1px 6px; border-radius: 6px; font-size: 12px; }
/* ---- sidebar tool-switcher layout ---- */
.sidebar { position: fixed; top: 0; left: 0; bottom: 0; width: 212px; background: #fff;
           border-right: 1px solid var(--line); padding: 22px 14px; display: flex;
           flex-direction: column; z-index: 10; }
.side-brand { font-size: 14px; font-weight: 800; letter-spacing: -.01em;
              padding: 4px 10px 16px; border-bottom: 1px solid var(--line); margin-bottom: 12px; }
.side-brand span { display: block; color: var(--muted); font-weight: 600; font-size: 10px;
                   text-transform: uppercase; letter-spacing: .12em; margin-top: 2px; }
.nav-item { display: block; padding: 8px 10px; margin: 1px 0; border-radius: 9px;
            font-size: 13px; font-weight: 600; color: #475569; cursor: pointer;
            user-select: none; }
.nav-item:hover { background: #f1f5f9; }
.nav-item.active { background: linear-gradient(90deg, var(--accent), var(--accent2)); color: #fff; }
.nav-item.sub { padding-left: 24px; font-weight: 500; font-size: 12.5px; color: var(--muted); }
.nav-item.sub.active { color: #fff; }
.side-foot { margin-top: auto; padding: 12px 10px 0; border-top: 1px solid var(--line);
             color: var(--muted); font-size: 11px; line-height: 1.55; }
.content { margin-left: 212px; }
.has-js .panel { display: none; }
.has-js .panel.active { display: block; }
/* ---- rank table search/sort ---- */
.table-tools { display: flex; align-items: center; gap: 12px; margin: 6px 0 4px; flex-wrap: wrap; }
.table-tools input { flex: 1; max-width: 320px; padding: 8px 12px; border: 1px solid var(--line);
                     border-radius: 9px; font-size: 13px; font-family: inherit;
                     background: #f8fafc; color: var(--ink); }
.table-tools input:focus { outline: 2px solid var(--accent); outline-offset: -1px; background: #fff; }
th.sortable { cursor: pointer; user-select: none; white-space: nowrap; }
th.sortable:hover { color: var(--accent); }
th.sortable .arrow { font-size: 9px; color: var(--accent); }
.nav-group { padding: 12px 10px 3px; font-size: 10.5px; font-weight: 700;
             letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.research-empty h3 { margin: 0 0 8px; font-size: 18px; }
.research-empty code { display: block; margin-top: 14px; }
.research-form textarea { width: 100%; min-height: 120px; padding: 12px; border: 1px solid var(--line);
  border-radius: 12px; font-family: inherit; font-size: 14px; resize: vertical; background: #f8fafc; }
.research-form-foot { display: flex; justify-content: space-between; align-items: center; margin-top: 12px; }
.research-form-foot button { padding: 8px 22px; border: none; border-radius: 8px;
  background: linear-gradient(90deg, var(--accent), var(--accent2)); color: #fff;
  font-weight: 700; cursor: pointer; }
.research-form-foot button:disabled { opacity: .6; cursor: not-allowed; }
a.research-btn { padding: 8px 22px; border-radius: 8px; text-decoration: none;
  background: linear-gradient(90deg, var(--accent), var(--accent2)); color: #fff;
  font-weight: 700; font-size: 13px; }
.research-status.ok { color: var(--you); }
.research-status.err { color: var(--rose); }
.research-tools input { max-width: 110px; }
/* ---- seed keyword detail card + highlighted seed row ---- */
.seed-detail-wrap { margin-top: 14px; }
.seed-detail-card { padding: 18px 20px; }
.seed-detail-head { margin-bottom: 14px; }
.seed-detail-keyword { font-size: 18px; font-weight: 800; color: var(--ink); letter-spacing: -.01em; }
.seed-detail-meta { font-size: 12px; color: var(--muted); margin-top: 2px; }
.seed-detail-kpis { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; }
.seed-detail-kpi { text-align: center; padding: 10px; background: #f8fafc; border-radius: 10px; }
.seed-detail-val { font-size: 18px; font-weight: 800; color: var(--accent); line-height: 1.2; }
.seed-detail-label { font-size: 10.5px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; margin-top: 4px; }
.research-table tr.seed-row { background: #eef2ff; }
.research-table tr.seed-row td:first-child { font-weight: 700; color: var(--accent); }
.seed-badge { display: inline-block; margin-left: 8px; padding: 1px 7px; border-radius: 6px; font-size: 10px; font-weight: 800; text-transform: uppercase; background: var(--accent); color: #fff; }
@media (max-width: 640px) {
  .seed-detail-kpis { grid-template-columns: repeat(3, 1fr); }
}
/* ---- rank tracker v2: one page per property + ahrefs-style cells ---- */
.has-js .rank-prop { display: none; }
.has-js .rank-prop.active { display: block; }
.table-tools select { padding: 7px 10px; border: 1px solid var(--line); border-radius: 9px;
                      font-size: 13px; font-family: inherit; background: #f8fafc; color: var(--ink); }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
.pos-chip { display: inline-block; min-width: 34px; padding: 1px 7px; border-radius: 7px;
            font-size: 11px; font-weight: 700; text-align: center; }
.pos-chip.up { background: var(--you-soft); color: #047857; }
.pos-chip.down { background: var(--rose-soft); color: var(--rose); }
.pos-chip.new { background: var(--amber-soft); color: var(--amber); }
.pos-chip.flat { background: #eef1f6; color: #64748b; }
.badge-b { display: inline-block; padding: 1px 6px; border-radius: 6px; font-size: 10.5px;
           font-weight: 800; background: var(--amber-soft); color: var(--amber); }
.feat-chip { display: inline-block; padding: 1px 7px; margin: 1px 2px 1px 0; border-radius: 6px;
             font-size: 10.5px; font-weight: 600; background: #eef1f6; color: #475569; }
.tag-cell { color: var(--muted); font-size: 12px; }
/* ---- competitor tracker ---- */
.comp-tabs { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; align-items: center; }
.comp-tab { padding: 7px 14px; border-radius: 8px; border: 1px solid var(--line); background: #f8fafc;
             font-size: 13px; font-weight: 600; color: #475569; cursor: pointer; }
.comp-tab:hover { background: #eef1f6; }
.comp-tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.comp-export { margin-left: auto; padding: 7px 14px; border-radius: 8px; border: none;
               background: linear-gradient(90deg, var(--accent), var(--accent2)); color: #fff;
               font-weight: 700; font-size: 12.5px; cursor: pointer; }
.comp-panel { display: none; }
.comp-panel.active { display: block; }
.comp-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 18px; }
.comp-kpi { background: #f8fafc; border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; }
.comp-kpi .num { font-size: 22px; font-weight: 800; color: var(--accent); }
.comp-kpi .label { font-size: 11.5px; color: var(--muted); margin-top: 4px; }
.comp-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; margin: 16px 0; }
.comp-card { border: 1px solid var(--line); border-radius: 14px; padding: 16px; background: #fff; }
.comp-card.you { border-color: #34d399; background: #f0fdf4; }
.comp-card h4 { margin: 0 0 4px; font-size: 14px; }
.comp-card .domain { font-size: 11.5px; color: var(--muted); }
.comp-card .row { display: flex; justify-content: space-between; font-size: 12.5px; margin: 6px 0; }
.comp-card .bar { margin-top: 10px; }
.comp-you-badge { display: inline-block; margin-left: 6px; padding: 1px 6px; border-radius: 5px; background: var(--you-soft); color: #047857; font-size: 9.5px; font-weight: 800; text-transform: uppercase; vertical-align: middle; }
.comp-filters { display: flex; gap: 10px; flex-wrap: wrap; margin: 12px 0; }
.comp-filters select, .comp-filters input { padding: 7px 10px; border: 1px solid var(--line); border-radius: 8px; font-size: 12.5px; background: #f8fafc; }
.comp-timeline { margin-top: 12px; }
.comp-day { font-size: 11.5px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; margin: 14px 0 6px; }
.comp-group { border: 1px solid var(--line); border-radius: 10px; margin-bottom: 8px; overflow: hidden; }
.comp-group-head { display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; background: #f8fafc; cursor: pointer; }
.comp-group-name { font-weight: 600; font-size: 13px; }
.comp-group-summary { font-size: 11.5px; color: var(--muted); }
.comp-group-items { display: none; padding: 8px 12px 12px; }
.comp-group.open .comp-group-items { display: block; }
.comp-row { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--line); font-size: 12.5px; cursor: pointer; }
.comp-row:last-child { border-bottom: none; }
.comp-row-detail { display: none; padding: 10px 12px; background: #f8fafc; border-radius: 8px; margin-bottom: 8px; font-size: 12px; }
.comp-row-detail.open { display: block; }
.comp-badge { display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 10.5px; font-weight: 800; text-transform: uppercase; white-space: nowrap; }
.comp-badge.new_page { background: #d1fae5; color: #047857; }
.comp-badge.content_update { background: #fef3c7; color: #92400e; }
.comp-badge.title_change { background: #e0e7ff; color: #3730a3; }
.comp-badge.meta_change { background: #ede9fe; color: #5b21b6; }
.comp-badge.h1_change { background: #fce7f3; color: #9d174d; }
.comp-badge.schema_change { background: #ecfeff; color: #0e7490; }
.comp-badge.redirect { background: #ffedd5; color: #9a3412; }
.comp-badge.page_removed { background: #ffe4e6; color: #9f1239; }
.comp-badge.url_case_change { background: #f3f4f6; color: #374151; }
.comp-seo-tag { display: inline-block; padding: 1px 7px; border-radius: 5px; background: #eef1f6; color: #475569; font-size: 10.5px; font-weight: 600; margin: 2px 4px 2px 0; }
.comp-seo-tag.up { background: #d1fae5; color: #047857; }
.comp-seo-tag.down { background: #ffe4e6; color: #9f1239; }
.comp-chart { margin: 16px 0; }
.comp-chart h4 { font-size: 13px; margin-bottom: 8px; }
.comp-hbar { display: flex; align-items: center; gap: 10px; margin: 6px 0; font-size: 12px; }
.comp-hbar .name { min-width: 140px; font-weight: 500; }
.comp-hbar .track { flex: 1; height: 14px; background: #eceef5; border-radius: 999px; overflow: hidden; }
.comp-hbar .fill { height: 100%; border-radius: 999px; }
.comp-matrix { overflow-x: auto; }
.comp-matrix table { font-size: 12px; min-width: 400px; }
.comp-matrix th, .comp-matrix td { text-align: center; }
.comp-matrix td:first-child, .comp-matrix th:first-child { text-align: left; }
.comp-warning { background: #fff7ed; border: 1px solid #fed7aa; color: #9a3412; padding: 10px 12px; border-radius: 10px; font-size: 12px; margin-bottom: 12px; }
@media (max-width: 860px) {
  .sidebar { position: static; width: auto; flex-direction: row; align-items: center;
             overflow-x: auto; padding: 10px; border-right: none;
             border-bottom: 1px solid var(--line); }
  .side-brand, .side-foot { display: none; }
  .nav-item { white-space: nowrap; }
  .content { margin-left: 0; }
}
@media print {
  body { background: #fff; }
  .hero { background: #fff; color: #000; box-shadow: none; border: 1px solid #ccc; }
  .hero .sub, .eyebrow { color: #444; }
  details, .no-print, .sidebar, .table-tools { display: none; }
  .content { margin-left: 0; }
  .has-js .panel, .has-js .rank-prop { display: block !important; }
  .card, .kpi { break-inside: avoid; box-shadow: none; }
}
"""
