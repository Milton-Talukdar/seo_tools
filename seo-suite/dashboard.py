#!/usr/bin/env python3
"""
dashboard.py — generate a self-contained HTML dashboard from seo_suite.db.

One page, one section per module; every section hides cleanly when its table
is missing or empty.

Usage:
    python3 dashboard.py           # writes index.html and prints its path
    python3 dashboard.py --open    # also opens it in your browser
"""
import argparse
import html
import json
import sqlite3
import webbrowser
from datetime import datetime
from pathlib import Path

from common import DASHBOARD_CSS, DB_PATH
from llm_visibility import BRANDS, MY_DOMAIN, PLATFORMS, PROMPTS_CSV

OUT = Path(__file__).parent / "index.html"  # index.html = clean GitHub Pages URL
YOU = BRANDS[0]  # first brand in the list = your brand
NOT_FOUND = 101  # rank sentinel: deeper than the tracked top 100


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

    # rank KPIs
    rdays = table_days(con, "rank_snapshots")
    if rdays:
        rows = con.execute(
            "SELECT keyword, position FROM rank_snapshots WHERE day=?",
            (rdays[0],)).fetchall()
        ranked = [p for _, p in rows if p is not None]
        cards.append((
            f"{sum(p <= 3 for p in ranked)}",
            f"keywords in Google top 3<br>{sum(p <= 10 for p in ranked)} in top 10 "
            f"· {sum(p <= 50 for p in ranked)} in top 50<br>"
            f"<span class='sub'>{len(ranked)}/{len(rows)} ranked ({esc(rdays[0])})</span>"))
        if len(rdays) > 1:
            prev = dict(con.execute(
                "SELECT keyword, position FROM rank_snapshots WHERE day=?",
                (rdays[1],)).fetchall())
            movers = sorted(
                (((prev.get(k) or NOT_FOUND) - (p or NOT_FOUND), k)
                 for k, p in rows if (prev.get(k) or NOT_FOUND) != (p or NOT_FOUND)),
                key=lambda m: -m[0])
            if movers:
                d, k = movers[0]
                cls, arrow = ("up", "▲") if d > 0 else ("down", "▼")
                cards.append((
                    f"<span class='delta {cls}'>{arrow}{abs(d)}</span>",
                    f"biggest rank move vs {esc(rdays[1])}<br>{esc(k[:60])}"))

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
def rank_sparkline(con, keyword):
    rows = con.execute(
        "SELECT day, position FROM rank_snapshots WHERE keyword=? "
        "ORDER BY day DESC LIMIT 8", (keyword,)).fetchall()
    vals = [p if p is not None else NOT_FOUND for _, p in reversed(rows)]
    if len(vals) < 2:
        return "<span class='sub'>—</span>"
    # better rank = taller bar
    bars = "".join(f"<i style='height:{max(1, round((NOT_FOUND - v) / NOT_FOUND * 18))}px'></i>"
                   for v in vals)
    return f"<span class='spark'>{bars}</span>"


def rank_section(con):
    days = table_days(con, "rank_snapshots")
    if not days:
        return ""
    rows = con.execute(
        "SELECT keyword, position, url FROM rank_snapshots WHERE day=?",
        (days[0],)).fetchall()
    if not rows:
        return ""
    prev = {}
    if len(days) > 1:
        prev = dict(con.execute(
            "SELECT keyword, position FROM rank_snapshots WHERE day=?",
            (days[1],)).fetchall())
    rows.sort(key=lambda r: (r[1] is None, r[1] or NOT_FOUND, r[0]))
    out = [f"<h2>Rank Tracker — Google US top 100 "
           f"<span class='sub'>({esc(days[0])}, {len(rows)} keywords)</span></h2>"
           "<div class='card'><table>"
           "<tr><th>keyword</th><th>position</th><th>vs prev</th>"
           "<th>recent trend</th><th>ranking url</th></tr>"]
    for keyword, pos, url in rows:
        if len(days) > 1 and keyword in prev:
            d = (prev[keyword] or NOT_FOUND) - (pos or NOT_FOUND)
            if d > 0:
                delta = f"<span class='delta up'>+{d}</span>"
            elif d < 0:
                delta = f"<span class='delta down'>{d}</span>"
            else:
                delta = "<span class='sub'>·</span>"
        else:
            delta = "<span class='sub'>—</span>"
        short_url = url.replace("https://", "").replace("http://", "")[:55]
        out.append(f"<tr><td>{esc(keyword)}</td>"
                   f"<td class='vol'>{fmt_pos(pos)}</td>"
                   f"<td>{delta}</td>"
                   f"<td>{rank_sparkline(con, keyword)}</td>"
                   f"<td class='sub'>{esc(short_url)}</td></tr>")
    out.append("</table><p class='sub'>First organic position for "
               f"{esc(MY_DOMAIN)} per keyword (US, weekly via DataForSEO). "
               "Trend bars: taller = better position; — = not in top 100.</p></div>")
    return "".join(out)


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()
    con = sqlite3.connect(DB_PATH)
    page = (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>Vantage Circle SEO Suite</title>"
            f"<link rel='preconnect' href='https://fonts.googleapis.com'>"
            f"<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>"
            f"<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap' rel='stylesheet'>"
            f"<style>{DASHBOARD_CSS}</style></head>"
            f"<body><div class='wrap'>"
            f"<div class='hero'>"
            f"<div class='eyebrow'>rank tracking · backlinks · AI search analytics</div>"
            f"<h1>Vantage Circle SEO Suite</h1>"
            f"<div class='sub'>domain: {esc(MY_DOMAIN)} · "
            f"platforms: {esc(', '.join(PLATFORMS))} · "
            f"generated {datetime.now():%Y-%m-%d %H:%M}</div></div>"
            f"{exec_summary(con)}{rank_section(con)}{backlinks_section(con)}"
            f"{sov_trend_section(con)}{volume_section(con)}"
            f"{discovered_section(con)}{silent_section(con)}{latest_llm_section(con)}"
            f"</div></body></html>")
    OUT.write_text(page, encoding="utf-8")
    print(f"Dashboard written to: {OUT}")
    if args.open:
        webbrowser.open(OUT.as_uri())


if __name__ == "__main__":
    main()
