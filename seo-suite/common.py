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
.table-tools { display: flex; align-items: center; gap: 12px; margin: 6px 0 4px; }
.table-tools input { flex: 1; max-width: 320px; padding: 8px 12px; border: 1px solid var(--line);
                     border-radius: 9px; font-size: 13px; font-family: inherit;
                     background: #f8fafc; color: var(--ink); }
.table-tools input:focus { outline: 2px solid var(--accent); outline-offset: -1px; background: #fff; }
th.sortable { cursor: pointer; user-select: none; white-space: nowrap; }
th.sortable:hover { color: var(--accent); }
th.sortable .arrow { font-size: 9px; color: var(--accent); }
/* ---- rank tracker v2: property sub-tabs + ahrefs-style cells ---- */
.rank-tabs { display: flex; gap: 6px; margin: 6px 0 0; }
.rank-tab { padding: 7px 14px; border-radius: 9px; font-size: 12.5px; font-weight: 600;
            color: #475569; background: #eef1f6; cursor: pointer; user-select: none; }
.rank-tab:hover { background: #e2e8f0; }
.rank-tab.active { background: linear-gradient(90deg, var(--accent), var(--accent2)); color: #fff; }
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
  details, .no-print, .sidebar, .table-tools, .rank-tabs { display: none; }
  .content { margin-left: 0; }
  .has-js .panel, .has-js .rank-prop { display: block !important; }
  .card, .kpi { break-inside: avoid; box-shadow: none; }
}
"""
