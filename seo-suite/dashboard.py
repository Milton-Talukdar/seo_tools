#!/usr/bin/env python3
"""
dashboard.py — generate a self-contained HTML dashboard from seo_suite.db.

One page with a left sidebar tool-switcher: Executive Summary, Rank Tracker
(one page per property — Vantage Circle, Vantage Fit — grouped under a
"Rank Tracker" sidebar heading, each searchable/sortable), Backlinks, and
LLM Visibility (share-of-voice trend, volumes, discovered prompts, silent
citations, latest run). Every panel hides cleanly when its table is missing
or empty.

Usage:
    python3 dashboard.py           # writes index.html and prints its path
    python3 dashboard.py --open    # also opens it in your browser
"""
import argparse
import html
import json
import os
import sqlite3
import webbrowser
from datetime import datetime
from pathlib import Path

from common import DASHBOARD_CSS, DB_PATH
from llm_visibility import BRANDS, MY_DOMAIN, PLATFORMS, PROMPTS_CSV

# Optional Cloudflare Worker endpoint for one-click keyword research.
# Set at build time: KR_WORKER_URL and KR_WORKER_KEY
WORKER_URL = os.environ.get("KR_WORKER_URL", "")
WORKER_KEY = os.environ.get("KR_WORKER_KEY", "")
from rank_track import PROPERTIES

OUT = Path(__file__).parent / "index.html"  # index.html = clean GitHub Pages URL
YOU = BRANDS[0]  # first brand in the list = your brand
NOT_FOUND = 101  # rank sentinel: deeper than the tracked top 100

# vanilla JS: sidebar panel switching (incl. grouped project pages) +
# per-table live search / tag filter / column sorting.
# (plain string, not an f-string — the braces are literal JS/CSS)
SCRIPT = """
(function () {
  // ---- sidebar panel switching ----
  var items = document.querySelectorAll('.nav-item');
  items.forEach(function (it) {
    it.addEventListener('click', function () {
      var p = it.getAttribute('data-panel');
      if (p) {
        items.forEach(function (n) { n.classList.remove('active'); });
        it.classList.add('active');
        document.querySelectorAll('.panel').forEach(function (el) {
          el.classList.remove('active');
        });
        var el = document.getElementById('panel-' + p);
        if (el) el.classList.add('active');
        window.scrollTo(0, 0);
      }
      var t = it.getAttribute('data-target');
      if (t) {
        var te = document.getElementById(t);
        if (te) te.scrollIntoView({ behavior: 'smooth' });
      }
    });
  });

  // ---- rank tracker: per-property search + tag filter + sorting ----
  document.querySelectorAll('.rank-prop').forEach(function (box) {
    var search = box.querySelector('.rank-search');
    var tagSel = box.querySelector('.tag-filter');
    var tbody = box.querySelector('tbody');
    if (!tbody) return;
    var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
    var count = box.querySelector('.rank-count');
    var ths = box.querySelectorAll('th.sortable');
    var sortKey = 'position', sortDir = 1;

    function applyFilter() {
      var q = search ? search.value.toLowerCase() : '';
      var tag = tagSel ? tagSel.value : '';
      var n = 0;
      rows.forEach(function (r) {
        var ok = r.getAttribute('data-search').indexOf(q) > -1;
        if (ok && tag) {
          var rt = r.getAttribute('data-tag');
          ok = tag === '__untagged__' ? rt === '' : rt === tag;
        }
        r.style.display = ok ? '' : 'none';
        if (ok) n++;
      });
      if (count) count.textContent = n + ' of ' + rows.length + ' keywords';
    }

    function keyVal(r, k) {
      var v = r.getAttribute('data-' + k);
      if (k === 'keyword') return v;
      return v === '' || v === null ? null : parseFloat(v);  // '' = unranked / no data
    }

    function cmp(a, b) {
      var va = keyVal(a, sortKey), vb = keyVal(b, sortKey);
      if (sortKey !== 'keyword') {          // missing values always sort last
        if (va === null && vb === null) return 0;
        if (va === null) return 1;
        if (vb === null) return -1;
      }
      if (va < vb) return -sortDir;
      if (va > vb) return sortDir;
      return 0;
    }

    function applySort() {
      rows.sort(cmp);
      rows.forEach(function (r) { tbody.appendChild(r); });
      ths.forEach(function (th) {
        var arr = th.querySelector('.arrow');
        if (arr) arr.textContent =
          th.getAttribute('data-sort') === sortKey ? (sortDir === 1 ? '▲' : '▼') : '';
      });
    }

    ths.forEach(function (th) {
      th.addEventListener('click', function () {
        var k = th.getAttribute('data-sort');
        if (k === sortKey) { sortDir = -sortDir; }
        else {
          sortKey = k;
          // keyword + position: best/ascending first; volume/traffic/kd: biggest first
          sortDir = (k === 'keyword' || k === 'position') ? 1 : -1;
        }
        applySort();
      });
    });

    if (search) search.addEventListener('input', applyFilter);
    if (tagSel) tagSel.addEventListener('change', applyFilter);
    applySort();
    applyFilter();
  });

  // ---- keyword research: one-click search via Cloudflare Worker ----
  (function () {
    var form = document.querySelector('.research-form[data-worker-url]');
    if (!form) return;
    var btn = form.querySelector('.research-search-btn');
    var ta = form.querySelector('.research-seed-input');
    var status = form.parentNode.querySelector('.research-status');
    if (!btn || !ta) return;
    btn.addEventListener('click', function () {
      var seed = ta.value.trim();
      if (!seed) {
        if (status) { status.textContent = 'Please enter a seed keyword.'; status.className = 'research-status sub err'; }
        return;
      }
      btn.disabled = true;
      btn.textContent = 'Searching…';
      if (status) { status.textContent = 'Sending request…'; status.className = 'research-status sub'; }
      fetch(form.getAttribute('data-worker-url'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Research-Key': form.getAttribute('data-worker-key')
        },
        body: JSON.stringify({ seed: seed, limit: '100' })
      }).then(function (r) {
        return r.json().then(function (data) {
          if (!r.ok || !data.ok) throw new Error(data.error || 'Request failed');
          if (status) { status.textContent = 'Research started. Results appear in ~1 minute. Refresh the dashboard.'; status.className = 'research-status sub ok'; }
          ta.value = '';
        });
      }).catch(function (e) {
        if (status) { status.textContent = 'Error: ' + e.message; status.className = 'research-status sub err'; }
      }).finally(function () {
        btn.disabled = false;
        btn.textContent = 'Search';
      });
    });
  })();

  // ---- keyword research: seed / search / volume / KD filters ----
  (function () {
    var wrap = document.querySelector('.research-wrap');
    if (!wrap) return;
    var seed = wrap.querySelector('.research-seed');
    var search = wrap.querySelector('.research-search');
    var volMin = wrap.querySelector('.research-vol-min');
    var volMax = wrap.querySelector('.research-vol-max');
    var kdMin = wrap.querySelector('.research-kd-min');
    var kdMax = wrap.querySelector('.research-kd-max');
    var rows = Array.prototype.slice.call(wrap.querySelectorAll('tbody tr'));
    var count = wrap.querySelector('.research-count');
    function num(v) { return v === '' || v == null ? NaN : parseFloat(v); }
    function apply() {
      var s = seed ? seed.value : '';
      var q = search ? search.value.toLowerCase() : '';
      var vmin = num(volMin ? volMin.value : ''), vmax = num(volMax ? volMax.value : '');
      var kmin = num(kdMin ? kdMin.value : ''), kmax = num(kdMax ? kdMax.value : '');
      var n = 0;
      rows.forEach(function (r) {
        var ok = true;
        if (s && r.getAttribute('data-seed') !== s) ok = false;
        if (ok && q && r.getAttribute('data-keyword').indexOf(q) === -1) ok = false;
        var v = parseFloat(r.getAttribute('data-volume'));
        if (ok && !isNaN(vmin) && v < vmin) ok = false;
        if (ok && !isNaN(vmax) && v > vmax) ok = false;
        var k = parseFloat(r.getAttribute('data-kd'));
        if (ok && !isNaN(kmin) && k < kmin) ok = false;
        if (ok && !isNaN(kmax) && k > kmax) ok = false;
        r.style.display = ok ? '' : 'none';
        if (ok) n++;
      });
      if (count) count.textContent = n + ' of ' + rows.length + ' keywords';
    }
    [seed, search, volMin, volMax, kdMin, kdMax].forEach(function (el) {
      if (el) el.addEventListener('input', apply);
    });
    apply();
  })();

  // ---- keyword research: show seed details card when a seed is selected ----
  (function () {
    var seedSel = document.querySelector('.research-wrap .research-seed');
    var cards = document.querySelectorAll('.seed-detail-card');
    if (!seedSel || !cards.length) return;
    function update() {
      var val = seedSel.value;
      cards.forEach(function (c) {
        c.style.display = c.getAttribute('data-seed') === val ? 'block' : 'none';
      });
    }
    seedSel.addEventListener('change', update);
    update();
  })();
})();
"""


def esc(s):
    return html.escape(str(s), quote=True)


def brand_chip(brand):
    cls = "chip you" if brand == YOU else "chip"
    return f'<span class="{cls}">{esc(brand)}</span>'


def fmt_pos(pos):
    return str(pos) if pos is not None and pos < NOT_FOUND else "—"


def table_days(con, table, limit=2):
    try:
        return [r[0] for r in con.execute(
            f"SELECT DISTINCT day FROM {table} ORDER BY day DESC LIMIT {limit}")]
    except sqlite3.OperationalError:
        return []


# ---------------------------------------------------------------- exec summary
def exec_summary(con):
    cards = []

    # rank KPIs — aggregate each property's latest full-coverage day
    rprops = [(p, prop_days(con, p)) for p in PROPERTIES]
    rprops = [(p, days) for p, days in rprops if days]
    if rprops:
        rows, prev = [], {}
        latest_day, prev_day = "", ""
        for p, days in rprops:
            rows += con.execute(
                "SELECT keyword, position FROM rank_snapshots "
                "WHERE day=? AND property=?", (days[0], p)).fetchall()
            latest_day = max(latest_day, days[0])
            if len(days) > 1:
                for k, pos in con.execute(
                        "SELECT keyword, position FROM rank_snapshots "
                        "WHERE day=? AND property=?", (days[1], p)):
                    prev[(p, k)] = pos
                prev_day = max(prev_day, days[1])
        ranked = [p for _, p in rows if p is not None]
        cards.append((
            f"{sum(p <= 3 for p in ranked)}",
            f"keywords in Google top 3<br>{sum(p <= 10 for p in ranked)} in top 10 "
            f"· {sum(p <= 50 for p in ranked)} in top 50<br>"
            f"<span class='sub'>{len(ranked)}/{len(rows)} ranked ({esc(latest_day)})</span>"))
        if prev:
            movers = sorted(
                (((prev.get((p, k)) or NOT_FOUND) - (pos or NOT_FOUND), k)
                 for p, days in rprops
                 for k, pos in con.execute(
                     "SELECT keyword, position FROM rank_snapshots "
                     "WHERE day=? AND property=?", (days[0], p)).fetchall()
                 if (prev.get((p, k)) or NOT_FOUND) != (pos or NOT_FOUND)),
                key=lambda m: -m[0])
            if movers:
                d, k = movers[0]
                cls, arrow = ("up", "▲") if d > 0 else ("down", "▼")
                cards.append((
                    f"<span class='delta {cls}'>{arrow}{abs(d)}</span>",
                    f"biggest rank move vs {esc(prev_day)}<br>{esc(k[:60])}"))

    # backlink KPI
    bdays = table_days(con, "backlink_snapshots")
    if bdays:
        latest = con.execute(
            "SELECT refdomains FROM backlink_snapshots WHERE day=?",
            (bdays[0],)).fetchone()
        if len(bdays) > 1:
            prev = con.execute(
                "SELECT refdomains FROM backlink_snapshots WHERE day=?",
                (bdays[1],)).fetchone()
            net = latest[0] - prev[0]
            cls, arrow = ("up", "+") if net >= 0 else ("down", "-")
            delta_html = (f"<span class='delta {cls}'>{arrow}{abs(net):,} "
                          f"vs {esc(bdays[1])}</span>")
        else:
            delta_html = "<span class='sub'>first run</span>"
        cards.append((f"{latest[0]:,}",
                      f"referring domains<br>{delta_html}"))

    # AI share-of-voice KPI
    ldays = table_days(con, "llm_snapshots")
    if ldays:
        rows = con.execute(
            "SELECT mentions FROM llm_snapshots WHERE day=?", (ldays[0],)).fetchall()
        n = len(rows) or 1
        sov = sum(json.loads(m).get(YOU, False) for m, in rows) / n * 100
        cards.append((f"{sov:.0f}%",
                      f"AI share of voice<br>"
                      f"<span class='sub'>{esc(ldays[0])} · {len(rows)} answers</span>"))

    if not cards:
        return ""
    kpis = "".join(f"<div class='kpi'><div class='num'>{num}</div>"
                   f"<div class='label'>{label}</div></div>" for num, label in cards)
    return f"<h2>Executive summary</h2><div class='kpis'>{kpis}</div>"


# ---------------------------------------------------------------- rank tracker
INTENT_SHORT = {"informational": "info", "navigational": "nav",
                "commercial": "com", "transactional": "trans"}


def prop_days(con, prop, limit=2):
    counts = con.execute(
        "SELECT day, COUNT(*) FROM rank_snapshots WHERE property=? "
        "GROUP BY day ORDER BY day DESC", (prop,)).fetchall()
    if not counts:
        return []
    # ignore partial days (e.g. --limit smoke tests): keep days covering
    # at least half of the fullest day's keywords
    fullest = max(c for _, c in counts)
    return [d for d, c in counts if c >= fullest / 2][:limit]


def pos_cell(prev, cur, has_prev):
    """Ahrefs-style: current position, 'from prev', colored change chip."""
    cur_s = fmt_pos(cur)
    if not has_prev:
        return f"<td class='num'><b>{cur_s}</b></td>", ""
    if prev is None and cur is None:
        return "<td class='num'>—</td>", ""
    if prev is None:  # previously unranked, now ranking
        return (f"<td class='num'><b>{cur_s}</b> "
                f"<span class='pos-chip new'>New</span></td>",
                str(NOT_FOUND - cur))
    if cur is None:
        return (f"<td class='num'>— <span class='sub'>from {prev}</span> "
                f"<span class='pos-chip down'>▼{NOT_FOUND - prev if False else 'out'}</span></td>",
                str((prev or NOT_FOUND) - NOT_FOUND))
    d = prev - cur
    if d > 0:
        chip = f"<span class='pos-chip up'>▲{d}</span>"
    elif d < 0:
        chip = f"<span class='pos-chip down'>▼{abs(d)}</span>"
    else:
        chip = "<span class='pos-chip flat'>·</span>"
    prev_s = f" <span class='sub'>from {prev}</span>" if d else ""
    return f"<td class='num'><b>{cur_s}</b>{prev_s} {chip}</td>", str(d)


def traffic_cell(meta):
    cur, prev = meta.get("traffic_cur"), meta.get("traffic_prev")
    if cur is None:
        return "<td class='num sub'>—</td>", ""
    cur_s = f"{cur:,.0f}"
    if prev is None:
        return f"<td class='num'>{cur_s}</td>", str(cur)
    d = cur - prev
    if d > 0:
        delta = f" <span class='delta up'>+{d:,.0f}</span>"
    elif d < 0:
        delta = f" <span class='delta down'>{d:,.0f}</span>"
    else:
        delta = ""
    return f"<td class='num'>{cur_s}{delta}</td>", str(cur)


def intent_cell(meta):
    try:
        flags = json.loads(meta.get("intent") or "{}")
    except (TypeError, ValueError):
        flags = {}
    labels = [short for name, short in INTENT_SHORT.items() if flags.get(name)]
    if not labels:
        return "<td class='sub'>—</td>"
    return "<td>" + " ".join(f"<span class='feat-chip'>{l}</span>"
                             for l in labels) + "</td>"


def features_cell(meta):
    try:
        feats = json.loads(meta.get("serp_features") or "[]")
    except (TypeError, ValueError):
        feats = []
    if not feats:
        return "<td class='sub'>—</td>"
    shown = "".join(f"<span class='feat-chip'>{esc(f)}</span>" for f in feats[:4])
    more = f"<span class='sub'>+{len(feats) - 4}</span>" if len(feats) > 4 else ""
    return f"<td>{shown}{more}</td>"


def rank_property_block(con, prop):
    cfg = PROPERTIES[prop]
    days = prop_days(con, prop)
    if not days:
        return ""
    rows = con.execute(
        "SELECT keyword, position, url FROM rank_snapshots "
        "WHERE day=? AND property=?", (days[0], prop)).fetchall()
    if not rows:
        return ""
    prev = {}
    if len(days) > 1:
        prev = dict(con.execute(
            "SELECT keyword, position FROM rank_snapshots "
            "WHERE day=? AND property=?", (days[1], prop)).fetchall())
    meta = {}
    for r in con.execute(
            "SELECT keyword, tag, volume, kd, cpc, intent, branded, serp_features,"
            " traffic_prev, traffic_cur FROM keyword_meta WHERE property=?",
            (prop,)):
        meta[r[0]] = {"tag": r[1] or "", "volume": r[2], "kd": r[3], "cpc": r[4],
                      "intent": r[5], "branded": r[6], "serp_features": r[7],
                      "traffic_prev": r[8], "traffic_cur": r[9]}
    rows.sort(key=lambda r: (r[1] is None, r[1] or NOT_FOUND, r[0]))
    tags = sorted({m["tag"] for m in meta.values() if m["tag"]})

    out = [f"<div class='rank-prop active' id='rank-{prop}'>"
           f"<div class='card'>"
           f"<div class='table-tools no-print'>"
           f"<input class='rank-search' type='search' placeholder='Search keywords or tags…'>"
           f"<select class='tag-filter'>"
           f"<option value=''>All tags</option>"]
    for t in tags:
        out.append(f"<option value='{esc(t.lower())}'>{esc(t)}</option>")
    out.append(f"<option value='__untagged__'>Untagged</option></select>"
               f"<span class='rank-count sub'>{len(rows)} keywords</span></div>"
               f"<table class='rank-table'><thead><tr>"
               f"<th class='sortable' data-sort='keyword'>Keyword <span class='arrow'></span></th>"
               f"<th>Tag</th>"
               f"<th class='sortable' data-sort='position'>Position <span class='arrow'></span></th>"
               f"<th class='sortable' data-sort='volume'>Volume <span class='arrow'></span></th>"
               f"<th class='sortable' data-sort='traffic'>Traffic <span class='arrow'></span></th>"
               f"<th class='sortable' data-sort='kd'>KD <span class='arrow'></span></th>"
               f"<th>Intent</th><th>Branded</th><th>SERP features</th><th>URL</th>"
               f"</tr></thead><tbody>")
    for keyword, pos, url in rows:
        m = meta.get(keyword, {"tag": "", "volume": None, "kd": None, "cpc": None,
                               "intent": None, "branded": 0, "serp_features": None,
                               "traffic_prev": None, "traffic_cur": None})
        prev_pos = prev.get(keyword) if days and len(days) > 1 else None
        has_prev = len(days) > 1 and keyword in prev
        pos_html, data_change = pos_cell(prev_pos, pos, has_prev)
        traffic_html, data_traffic = traffic_cell(m)
        short_url = url.replace("https://", "").replace("http://", "")[:50]
        vol = m["volume"]
        kd = m["kd"]
        out.append(
            f"<tr data-keyword='{esc(keyword.lower())}' "
            f"data-search='{esc((keyword + ' ' + m['tag']).lower())}' "
            f"data-tag='{esc(m['tag'].lower())}' "
            f"data-position='{'' if pos is None else pos}' "
            f"data-change='{data_change}' "
            f"data-volume='{'' if vol is None else vol}' "
            f"data-traffic='{data_traffic}' "
            f"data-kd='{'' if kd is None else kd}'>"
            f"<td>{esc(keyword)}</td>"
            f"<td class='tag-cell'>{esc(m['tag']) or '—'}</td>"
            f"{pos_html}"
            f"<td class='num'>{f'{vol:,}' if vol is not None else '<span class=sub>—</span>'}</td>"
            f"{traffic_html}"
            f"<td class='num'>{f'{kd:.0f}' if kd is not None else '<span class=sub>—</span>'}</td>"
            f"{intent_cell(m)}"
            f"<td>{'<span class=badge-b>B</span>' if m['branded'] else ''}</td>"
            f"{features_cell(m)}"
            f"<td class='sub'>{esc(short_url)}</td></tr>")
    out.append("</tbody></table><p class='sub'>Google US top 100 for "
               f"{esc(cfg['domain'])} — current: {esc(days[0])}"
               + (f", previous: {esc(days[1])}" if len(days) > 1 else "")
               + ". Volume / traffic / KD / intent from keyword_meta "
               "(Ahrefs overview import + monthly enrich.py). "
               "— = unranked or no data. "
               "<span class='no-print'>Type to filter, pick a tag, click a column header to sort.</span></p>"
               "</div></div>")
    return "".join(out)


def rank_property_page(con, prop):
    """Full rank-tracker page body for one property; '' when it has no data."""
    cfg = PROPERTIES[prop]
    days = prop_days(con, prop)
    if not days:
        return ""
    block = rank_property_block(con, prop)
    if not block:
        return ""
    return (f"<h2>Rank Tracker — {esc(cfg['label'])} · Google US top 100 "
            f"<span class='sub'>({esc(days[0])})</span></h2>" + block)


# ---------------------------------------------------------------- backlinks
def backlinks_section(con):
    days = table_days(con, "backlink_snapshots", limit=8)
    if not days:
        return ""
    out = ["<h2>Backlinks</h2>"]
    rows = [con.execute(
        "SELECT day, backlinks, refdomains, rank FROM backlink_snapshots "
        "WHERE day=?", (d,)).fetchone() for d in reversed(days)]
    mx = max(r[2] for r in rows) or 1
    out.append("<div class='card'><b>Profile totals</b><table>"
               "<tr><th>date</th><th>backlinks</th><th>refdomains</th>"
               "<th></th><th>DFS rank</th></tr>")
    for day, backlinks, refdomains, rank in rows:
        out.append(f"<tr><td><b>{esc(day)}</b></td>"
                   f"<td class='vol'>{backlinks:,}</td>"
                   f"<td class='vol'>{refdomains:,}</td>"
                   f"<td><div class='bar'><div style='width:{refdomains / mx * 100:.0f}%'>"
                   f"</div></div></td><td>{rank}</td></tr>")
    out.append("</table></div>")

    edays = table_days(con, "refdomain_events", limit=2)
    if edays:
        events = con.execute(
            "SELECT day, event, domain, rank FROM refdomain_events "
            "WHERE day IN (?, ?) ORDER BY day DESC, event, rank DESC",
            (edays[0], edays[-1])).fetchall()
        if events:
            out.append("<div class='card'><b>Recent new / lost referring domains</b>"
                       "<table><tr><th>date</th><th>event</th><th>domain</th>"
                       "<th>rank</th></tr>")
            for day, event, domain, rank in events[:40]:
                chip = (f"<span class='chip you'>{event}</span>" if event == "new"
                        else f"<span class='chip none'>{event}</span>")
                if domain == "(total)":
                    out.append(f"<tr><td>{esc(day)}</td><td>{chip}</td>"
                               f"<td class='sub'>API aggregate count</td>"
                               f"<td class='vol'>{rank}</td></tr>")
                else:
                    out.append(f"<tr><td>{esc(day)}</td><td>{chip}</td>"
                               f"<td>{esc(domain)}</td>"
                               f"<td class='vol'>{rank if rank is not None else '—'}</td></tr>")
            out.append("</table><p class='sub'>Weekly API runs record aggregate "
                       "counts; per-domain detail comes from the one-time Ahrefs "
                       "import (import_ahrefs.py).</p></div>")
    return "".join(out)


# ---------------------------------------------------------------- LLM sections
def sov_trend_section(con):
    try:
        rows = con.execute("SELECT day, mentions FROM llm_snapshots").fetchall()
    except sqlite3.OperationalError:
        return ""
    if not rows:
        return ""
    agg = {}
    for day, mj in rows:
        m = json.loads(mj)
        slot = agg.setdefault(day, {b: [0, 0] for b in BRANDS})
        for b in BRANDS:
            slot[b][0] += bool(m.get(b))
            slot[b][1] += 1
    days = sorted(agg, reverse=True)
    head = "".join(
        f"<th>{esc(b)}{' (you)' if b == YOU else ''}</th>" for b in BRANDS)
    body = ""
    for day in days:
        cells = ""
        for b in BRANDS:
            got, total = agg[day][b]
            pct = got / total * 100 if total else 0
            cls = "bar you" if b == YOU else "bar"
            cells += (f'<td><div class="{cls}"><div style="width:{pct:.0f}%"></div></div>'
                      f'<span class="sub">{pct:.0f}%</span></td>')
        body += f"<tr><td><b>{esc(day)}</b></td>{cells}</tr>"
    return (f"<h2>AI share of voice trend</h2><div class='card'><table>"
            f"<tr><th>run date</th>{head}</tr>{body}</table>"
            f"<p class='sub'>% of prompt × platform answers mentioning each brand.</p></div>")


def volume_section(con):
    try:
        rows = con.execute(
            "SELECT v.keyword, v.ai_search_volume, v.trend_json FROM volumes v "
            "JOIN (SELECT keyword, MAX(day) d FROM volumes GROUP BY keyword) m "
            "ON v.keyword = m.keyword AND v.day = m.d "
            "ORDER BY v.ai_search_volume DESC").fetchall()
    except sqlite3.OperationalError:
        return ""  # llm_discover.py has not run yet
    if not rows:
        return ""
    out = ["<h2>AI search volume — your seed keywords</h2><div class='card'><table>"
           "<tr><th>keyword</th><th>AI searches/mo</th><th>12-month trend</th></tr>"]
    for kw, vol, tj in rows:
        months = json.loads(tj or "[]")
        vals = [m.get("ai_search_volume") or 0 for m in reversed(months)]  # oldest → newest
        mx = max(vals) or 1
        spark = "".join(f"<i style='height:{max(1, round(v / mx * 18))}px'></i>"
                        for v in vals)
        out.append(f"<tr><td>{esc(kw)}</td><td class='vol'>{vol}</td>"
                   f"<td><span class='spark'>{spark}</span></td></tr>")
    out.append("</table><p class='sub'>How often each phrase is typed into AI tools per "
               "month (US). Updated monthly by llm_discover.py.</p></div>")
    return "".join(out)


def discovered_section(con):
    try:
        rows = con.execute(
            "SELECT query, platform, ai_search_volume, seed FROM discovered "
            "ORDER BY ai_search_volume DESC LIMIT 40").fetchall()
    except sqlite3.OperationalError:
        return ""
    if not rows:
        return ""
    tracked = {l.strip().lower() for l in open(PROMPTS_CSV, encoding="utf-8")
               if l.strip() and not l.startswith("#")}
    out = ["<h2>Discovered prompts — what people really ask AI</h2>"
           "<div class='card'><table>"
           "<tr><th>question</th><th>platform</th><th>AI searches/mo</th>"
           "<th>tracked?</th></tr>"]
    for q, platform, vol, seed in rows:
        mark = ("<span class='chip tracked'>in tracker</span>" if q.lower() in tracked
                else "<span class='chip'>—</span>")
        out.append(f"<tr><td>{esc(q)}</td>"
                   f"<td><span class='chip'>{esc(platform)}</span></td>"
                   f"<td class='vol'>{vol}</td><td>{mark}</td></tr>")
    out.append("</table><p class='sub'>Real user questions from the LLM Mentions "
               "database matched to your seeds. Add high-volume ones to prompts.csv "
               "to track them weekly.</p></div>")
    return "".join(out)


def silent_section(con):
    try:
        days = [r[0] for r in con.execute(
            "SELECT DISTINCT day FROM silent ORDER BY day DESC LIMIT 2")]
    except sqlite3.OperationalError:
        return ""
    if not days:
        return ""
    rows = con.execute(
        "SELECT query, platform, ai_search_volume FROM silent "
        "WHERE day=? ORDER BY ai_search_volume DESC", (days[0],)).fetchall()
    prev = None
    if len(days) > 1:
        prev = con.execute("SELECT COUNT(*) FROM silent WHERE day=?",
                           (days[1],)).fetchone()[0]
    trend = f" · was {prev} at previous check" if prev is not None else ""
    out = [f"<h2>Silent citations — your content, no brand credit "
           f"<span class='sub'>({len(rows)} found{esc(trend)})</span></h2>"
           f"<div class='card'><table>"
           f"<tr><th>query</th><th>platform</th><th>AI searches/mo</th></tr>"]
    for q, platform, vol in rows:
        out.append(f"<tr><td>{esc(q)}</td>"
                   f"<td><span class='chip'>{esc(platform)}</span></td>"
                   f"<td class='vol'>{vol}</td></tr>")
    out.append("</table><p class='sub'>AI answers that cite "
               f"{esc(MY_DOMAIN)} as a source but never name your brand. Fix: weave "
               "brand references into these pages so the AI lifts the name along "
               "with the content. Checked monthly (top-100 sample of answers "
               "referencing your domain).</p></div>")
    return "".join(out)


def latest_llm_section(con):
    try:
        row = con.execute("SELECT MAX(day) FROM llm_snapshots").fetchone()
    except sqlite3.OperationalError:
        return ""
    if not row or not row[0]:
        return ""
    day = row[0]
    rows = con.execute(
        "SELECT prompt, platform, mentions, cited_mine, answer "
        "FROM llm_snapshots WHERE day=? ORDER BY prompt, platform", (day,)).fetchall()
    by_prompt = {}
    for prompt, platform, mj, cited, answer in rows:
        by_prompt.setdefault(prompt, []).append((platform, json.loads(mj), cited, answer))
    out = [f"<h2>Latest LLM run — {esc(day)}</h2>"]
    for prompt, entries in by_prompt.items():
        chips = []
        for platform, m, cited, _ in entries:
            found = [b for b in BRANDS if m.get(b)]
            tag = " ".join(brand_chip(b) for b in found) if found else '<span class="chip none">no brands</span>'
            cite = '<span class="chip cite">your site cited</span>' if cited else ""
            chips.append(f'<div><span class="plat">{esc(platform)}</span> {tag} {cite}</div>')
        answers = "".join(
            f"<div><span class='plat'>{esc(p)}</span></div>"
            f"<div class='answer'>{esc(a[:4000])}</div>"
            for p, _, _, a in entries)
        out.append(f"<div class='card'><b>{esc(prompt)}</b>{''.join(chips)}"
                   f"<details><summary>show raw answers</summary>{answers}</details></div>")
    return "".join(out)


def keyword_row_html(seed, keyword, vol, kd, cpc, comp, intent, feats, is_seed=False):
    """Format one keyword/seed row for the research table."""
    feats_list = []
    try:
        feats_list = json.loads(feats or "[]") or []
    except (TypeError, ValueError):
        pass
    feat_html = "".join(f"<span class='feat-chip'>{esc(f)}</span>" for f in feats_list[:4])
    if len(feats_list) > 4:
        feat_html += f"<span class='sub'>+{len(feats_list) - 4}</span>"
    intent_html = (f"<span class='feat-chip'>{esc(intent)}</span>" if intent else "")
    vol_v = vol if vol is not None else ""
    kd_v = kd if kd is not None else ""
    cls = "seed-row" if is_seed else ""
    label = "<span class='seed-badge'>seed</span>" if is_seed else ""
    return (
        f"<tr class='{cls}' data-keyword='{esc(keyword.lower())}' "
        f"data-seed='{esc(seed)}' "
        f"data-volume='{vol_v}' data-kd='{kd_v}'>"
        f"<td>{esc(keyword)}{label}</td>"
        f"<td class='tag-cell'>{esc(seed)}</td>"
        f"<td class='num'>{f'{vol:,}' if vol is not None else '<span class=sub>—</span>'}</td>"
        f"<td class='num'>{f'{kd:.0f}' if kd is not None else '<span class=sub>—</span>'}</td>"
        f"<td class='num'>{f'${cpc:.2f}' if cpc is not None else '<span class=sub>—</span>'}</td>"
        f"<td class='num'>{f'{comp:.2f}' if comp is not None else '<span class=sub>—</span>'}</td>"
        f"<td>{intent_html or '<span class=sub>—</span>'}</td>"
        f"<td>{feat_html or '<span class=sub>—</span>'}</td>"
        f"</tr>")


def seed_details_card(con):
    """Hidden-by-default details card populated by JS when a seed is selected."""
    try:
        rows = con.execute(
            "SELECT seed, volume, kd, cpc, competition, intent, "
            "serp_features, fetched FROM seed_overview "
            "ORDER BY seed").fetchall()
    except sqlite3.OperationalError:
        return ""
    if not rows:
        return ""
    cards = []
    for seed, vol, kd, cpc, comp, intent, feats, fetched in rows:
        intent_html = (f"<span class='feat-chip'>{esc(intent)}</span>" if intent else "")
        cards.append(
            f"<div class='seed-detail-card card' data-seed='{esc(seed)}' style='display:none;'>"
            f"<div class='seed-detail-head'>"
            f"<div class='seed-detail-keyword'>{esc(seed)}</div>"
            f"<div class='seed-detail-meta'>seed keyword</div></div>"
            f"<div class='seed-detail-kpis'>"
            f"<div class='seed-detail-kpi'><div class='seed-detail-val'>"
            f"{f'{vol:,}' if vol is not None else '—'}</div>"
            f"<div class='seed-detail-label'>Volume</div></div>"
            f"<div class='seed-detail-kpi'><div class='seed-detail-val'>"
            f"{f'{kd:.0f}' if kd is not None else '—'}</div>"
            f"<div class='seed-detail-label'>KD</div></div>"
            f"<div class='seed-detail-kpi'><div class='seed-detail-val'>"
            f"{f'${cpc:.2f}' if cpc is not None else '—'}</div>"
            f"<div class='seed-detail-label'>CPC</div></div>"
            f"<div class='seed-detail-kpi'><div class='seed-detail-val'>"
            f"{f'{comp:.2f}' if comp is not None else '—'}</div>"
            f"<div class='seed-detail-label'>Competition</div></div>"
            f"<div class='seed-detail-kpi'><div class='seed-detail-val'>"
            f"{intent_html or '—'}</div>"
            f"<div class='seed-detail-label'>Intent</div></div>"
            f"</div></div>")
    return f"<div class='seed-detail-wrap'>{''.join(cards)}</div>"


def research_section(con):
    """Keyword Research panel: search card + seed details + ideas table."""
    rows = con.execute(
        "SELECT seed, keyword, volume, kd, cpc, competition, intent, "
        "serp_features, fetched FROM keyword_research "
        "ORDER BY seed, volume DESC NULLS LAST, keyword").fetchall()
    details = seed_details_card(con)
    if not rows:
        return details + _research_empty_card()

    seeds = sorted({r[0] for r in rows})
    seed_options = "".join(f"<option value='{esc(s)}'>{esc(s)}</option>" for s in seeds)

    body = [f"<h2>Keyword Research</h2>{_research_empty_card()}{details}"
            f"<div class='card research-wrap'>"
            f"<div class='table-tools no-print research-tools'>"
            f"<select class='research-seed'><option value=''>All seeds</option>"
            f"{seed_options}</select>"
            f"<input class='research-search' type='search' placeholder='Search keywords…'>"
            f"<input class='research-vol-min' type='number' placeholder='Min vol' min='0'>"
            f"<input class='research-vol-max' type='number' placeholder='Max vol' min='0'>"
            f"<input class='research-kd-min' type='number' placeholder='Min KD' min='0' max='100'>"
            f"<input class='research-kd-max' type='number' placeholder='Max KD' min='0' max='100'>"
            f"<span class='research-count sub'>{len(rows)} keywords</span></div>"
            f"<table class='research-table'><thead><tr>"
            f"<th>Keyword</th><th>Seed</th><th>Volume</th><th>KD</th>"
            f"<th>CPC</th><th>Competition</th><th>Intent</th><th>SERP features</th>"
            f"</tr></thead><tbody>"]

    # render seed rows first, then idea rows
    by_seed = {}
    for seed, keyword, vol, kd, cpc, comp, intent, feats, fetched in rows:
        by_seed.setdefault(seed, []).append((keyword, vol, kd, cpc, comp, intent, feats, fetched))

    for seed in sorted(by_seed):
        # seed overview from seed_overview table
        ov = con.execute(
            "SELECT volume, kd, cpc, competition, intent, serp_features "
            "FROM seed_overview WHERE seed=?", (seed,)).fetchone()
        if ov:
            body.append(keyword_row_html(seed, seed, *ov, is_seed=True))
        # idea rows
        for keyword, vol, kd, cpc, comp, intent, feats, fetched in by_seed[seed]:
            if keyword.lower() == seed.lower():
                continue  # already rendered as seed row
            body.append(keyword_row_html(seed, keyword, vol, kd, cpc, comp, intent, feats))

    body.append("</tbody></table></div>")
    return "".join(body)


def _research_empty_card():
    workflow_url = ("https://github.com/Milton-Talukdar/seo_tools/actions/workflows/"
                    "keyword-research.yml")
    if WORKER_URL and WORKER_KEY:
        return (f"<div class='card research-empty'>"
                f"<h3>Keywords Explorer</h3>"
                f"<p class='sub'>Get keyword ideas with Search Volume, Keyword Difficulty, "
                f"CPC and SERP features. Type a seed keyword and click Search.</p>"
                f"<div class='research-form no-print' data-worker-url='{esc(WORKER_URL)}' "
                f"data-worker-key='{esc(WORKER_KEY)}'>"
                f"<textarea class='research-seed-input' placeholder='Enter keywords separated by commas or new lines'>"
                f"</textarea>"
                f"<div class='research-form-foot'>"
                f"<span>🌎 United States</span>"
                f"<button type='button' class='research-search-btn'>Search</button></div></div>"
                f"<p class='research-status sub'></p>"
                f"</div>")
    return (f"<div class='card research-empty'>"
            f"<h3>Keywords Explorer</h3>"
            f"<p class='sub'>Get keyword ideas with Search Volume, Keyword Difficulty, "
            f"CPC and SERP features. Add seed keywords below, then run research on GitHub.</p>"
            f"<div class='research-form no-print'>"
            f"<textarea class='research-seed-input' placeholder='Enter keywords separated by commas or new lines'>"
            f"</textarea>"
            f"<div class='research-form-foot'>"
            f"<span>🌎 United States</span>"
            f"<a class='research-btn' href='{esc(workflow_url)}' target='_blank'>"
            f"Run on GitHub Actions →</a></div></div>"
            f"<p class='sub'>The workflow uses repository secrets, so API credentials are never exposed. "
            f"Copy the keywords above and paste them into the <b>seed</b> field.</p>"
            f"</div>")


# ---------------------------------------------------------------- page assembly
def build_panels(con):
    """[(panel_id, label, html, [(sub_id, sub_label), ...], group), ...] — only
    modules that actually have data. Panels sharing a group name are bundled
    under one sidebar heading, each as its own page."""
    panels = []
    ex = exec_summary(con)
    if ex:
        panels.append(("exec", "Executive Summary", ex, [], None))
    for prop in PROPERTIES:                     # one page per project
        page = rank_property_page(con, prop)
        if page:
            panels.append((f"rank-{prop}", PROPERTIES[prop]["label"],
                           page, [], "Rank Tracker"))
    bl = backlinks_section(con)
    if bl:
        panels.append(("backlinks", "Backlinks", bl, [], None))
    rs = research_section(con)
    if rs:
        panels.append(("research", "Keyword Research", rs, [], None))
    llm_subs = [(sid, label, section)
                for sid, label, section in [
                    ("llm-sov", "Share of voice", sov_trend_section(con)),
                    ("llm-vol", "AI search volume", volume_section(con)),
                    ("llm-disc", "Discovered prompts", discovered_section(con)),
                    ("llm-silent", "Silent citations", silent_section(con)),
                    ("llm-latest", "Latest run", latest_llm_section(con))]
                if section]
    if llm_subs:
        body = "".join(f"<div id='{sid}'>{section}</div>"
                       for sid, _, section in llm_subs)
        panels.append(("llm", "LLM Visibility", body,
                       [(sid, label) for sid, label, _ in llm_subs], None))
    return panels


def sidebar_html(panels, generated):
    nav, last_group, first = [], None, True
    for pid, label, _, subs, group in panels:
        if group != last_group:
            if group:
                nav.append(f"<div class='nav-group'>{esc(group)}</div>")
            last_group = group
        cls = "nav-item" + (" sub" if group else "") + (" active" if first else "")
        nav.append(f"<a class='{cls}' data-panel='{pid}'>{esc(label)}</a>")
        first = False
        for sid, slabel in subs:
            nav.append(f"<a class='nav-item sub' data-panel='{pid}' "
                       f"data-target='{sid}'>{esc(slabel)}</a>")
    return (f"<nav class='sidebar'>"
            f"<div class='side-brand'>Vantage Circle<span>SEO Suite</span></div>"
            f"{''.join(nav)}"
            f"<div class='side-foot'>{len(panels)} modules<br>"
            f"generated {esc(generated)}</div></nav>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()
    con = sqlite3.connect(DB_PATH)
    panels = build_panels(con)
    generated = f"{datetime.now():%Y-%m-%d %H:%M}"

    if panels:
        panels_html = "".join(
            f"<section class='panel{' active' if i == 0 else ''}' "
            f"id='panel-{pid}'>{body}</section>"
            for i, (pid, _, body, _, _) in enumerate(panels))
    else:
        panels_html = ("<div class='card'>No data yet — run the collectors "
                       "(rank_track.py, backlinks.py, llm_visibility.py) first.</div>")

    page = (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>Vantage Circle SEO Suite</title>"
            f"<link rel='preconnect' href='https://fonts.googleapis.com'>"
            f"<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>"
            f"<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap' rel='stylesheet'>"
            f"<style>{DASHBOARD_CSS}</style>"
            f"<script>document.documentElement.className += ' has-js';</script>"
            f"</head><body>"
            f"{sidebar_html(panels, generated)}"
            f"<div class='content'><div class='wrap'>"
            f"<div class='hero'>"
            f"<div class='eyebrow'>rank tracking · backlinks · AI search analytics</div>"
            f"<h1>Vantage Circle SEO Suite</h1>"
            f"<div class='sub'>domain: {esc(MY_DOMAIN)} · "
            f"platforms: {esc(', '.join(PLATFORMS))} · "
            f"generated {generated}</div></div>"
            f"{panels_html}"
            f"</div></div>"
            f"<script>{SCRIPT}</script>"
            f"</body></html>")
    OUT.write_text(page, encoding="utf-8")
    print(f"Dashboard written to: {OUT}")
    if args.open:
        webbrowser.open(OUT.as_uri())


if __name__ == "__main__":
    main()
