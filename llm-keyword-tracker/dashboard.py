#!/usr/bin/env python3
"""
dashboard.py — generate a self-contained HTML dashboard from llm_visibility.db.

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

from llm_track import BRANDS, MY_DOMAIN, PLATFORMS, DB_PATH, PROMPTS_CSV

OUT = Path(__file__).parent / "index.html"  # index.html = clean GitHub Pages URL
YOU = BRANDS[0]  # first brand in the list = your brand

CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, 'Segoe UI', sans-serif; margin: 0; background: #f5f6f8; color: #1c1e21; }
.wrap { max-width: 1000px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 22px; margin: 8px 0 2px; }
h2 { font-size: 16px; margin: 28px 0 10px; }
.sub { color: #65676b; font-size: 13px; }
.card { background: #fff; border: 1px solid #e4e6eb; border-radius: 10px; padding: 16px; margin-top: 12px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #f0f2f5; }
th { color: #65676b; font-weight: 600; }
.bar { height: 8px; border-radius: 4px; background: #e4e6eb; min-width: 60px; }
.bar > div { height: 8px; border-radius: 4px; background: #8a8d91; }
.bar.you > div { background: #1a7f37; }
.chip { display: inline-block; padding: 1px 8px; margin: 1px 2px; border-radius: 10px;
        background: #e4e6eb; font-size: 12px; }
.chip.you { background: #d3f0dc; color: #1a7f37; font-weight: 600; }
.chip.cite { background: #fff3cd; color: #8a6d00; }
.chip.none { background: #f8d7da; color: #9b1c1c; }
details { margin-top: 8px; }
summary { cursor: pointer; padding: 8px 4px; font-size: 14px; }
summary:hover { background: #f0f2f5; border-radius: 6px; }
.answer { white-space: pre-wrap; font-size: 12px; color: #444; background: #fafbfc;
          border: 1px solid #e4e6eb; border-radius: 8px; padding: 10px; margin: 6px 0 14px;
          max-height: 300px; overflow-y: auto; }
.plat { font-weight: 600; display: inline-block; min-width: 90px; }
.spark { display: inline-flex; align-items: flex-end; gap: 1px; height: 18px; }
.spark i { display: block; width: 6px; background: #7aa7d9; border-radius: 1px; }
.chip.tracked { background: #d3f0dc; color: #1a7f37; font-weight: 600; }
.vol { font-weight: 600; }
"""

def esc(s):
    return html.escape(str(s), quote=True)


def brand_chip(brand, cited=False):
    cls = "chip you" if brand == YOU else "chip"
    label = esc(brand)
    return f'<span class="{cls}">{label}</span>'


def trend_section(con):
    rows = con.execute("SELECT day, mentions FROM snapshots").fetchall()
    if not rows:
        return "<p>No data yet — run <code>llm_track.py</code> first.</p>"
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
    return (f"<h2>Share of voice trend</h2><div class='card'><table>"
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
        return ""  # discover.py has not run yet
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
               "month (US). Updated monthly by discover.py.</p></div>")
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


def latest_section(con):
    row = con.execute("SELECT MAX(day) FROM snapshots").fetchone()
    if not row or not row[0]:
        return ""
    day = row[0]
    rows = con.execute(
        "SELECT prompt, platform, mentions, cited_mine, answer "
        "FROM snapshots WHERE day=? ORDER BY prompt, platform", (day,)).fetchall()
    by_prompt = {}
    for prompt, platform, mj, cited, answer in rows:
        by_prompt.setdefault(prompt, []).append((platform, json.loads(mj), cited, answer))
    out = [f"<h2>Latest run — {esc(day)}</h2>"]
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
            f"<title>LLM Visibility Dashboard</title><style>{CSS}</style></head>"
            f"<body><div class='wrap'>"
            f"<h1>LLM Visibility Dashboard</h1>"
            f"<div class='sub'>brand: {esc(YOU)} · domain: {esc(MY_DOMAIN)} · "
            f"platforms: {esc(', '.join(PLATFORMS))} · "
            f"generated {datetime.now():%Y-%m-%d %H:%M}</div>"
            f"{trend_section(con)}{volume_section(con)}"
            f"{discovered_section(con)}{latest_section(con)}"
            f"</div></body></html>")
    OUT.write_text(page, encoding="utf-8")
    print(f"Dashboard written to: {OUT}")
    if args.open:
        webbrowser.open(OUT.as_uri())


if __name__ == "__main__":
    main()
