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
@media print {
  body { background: #fff; }
  .hero { background: #fff; color: #000; box-shadow: none; border: 1px solid #ccc; }
  .hero .sub, .eyebrow { color: #444; }
  details, .no-print { display: none; }
  .card, .kpi { break-inside: avoid; box-shadow: none; }
}
"""

def esc(s):
    return html.escape(str(s), quote=True)


def brand_chip(brand, cited=False):
    cls = "chip you" if brand == YOU else "chip"
    label = esc(brand)
    return f'<span class="{cls}">{label}</span>'


def exec_summary(con):
    days = [r[0] for r in con.execute(
        "SELECT DISTINCT day FROM snapshots ORDER BY day DESC LIMIT 2")]
    if not days:
        return ""

    def sov(day):
        rows = con.execute(
            "SELECT mentions, cited_mine FROM snapshots WHERE day=?", (day,)).fetchall()
        n = len(rows) or 1
        per = {b: sum(json.loads(m).get(b, False) for m, _ in rows) / n * 100 for b in BRANDS}
        return per, sum(c for _, c in rows), len(rows)

    latest, cited, total = sov(days[0])
    your = latest[YOU]
    ranking = sorted(latest.items(), key=lambda kv: -kv[1])
    rank = [b for b, _ in ranking].index(YOU) + 1
    leader, leader_v = ranking[0]

    if len(days) > 1:
        prev, _, _ = sov(days[1])
        d = your - prev[YOU]
        cls, arrow = ("up", "+") if d >= 0 else ("down", "-")
        delta_html = (f"<span class='delta {cls}'>{arrow}{abs(d):.0f} pts "
                      f"vs {esc(days[1])}</span>")
    else:
        delta_html = "<span class='sub'>first run — trend starts next week</span>"

    # prompt- and platform-level analysis of the latest run
    rows = con.execute("SELECT prompt, platform, mentions FROM snapshots WHERE day=?",
                       (days[0],)).fetchall()
    by_prompt, plat_you = {}, {}
    for prompt, platform, mj in rows:
        m = json.loads(mj)
        by_prompt.setdefault(prompt, []).append(m)
        plat_you.setdefault(platform, []).append(m.get(YOU, False))
    appear = sum(1 for ms in by_prompt.values() if any(m.get(YOU, False) for m in ms))
    opps = [(p, {b for m in ms for b in BRANDS if b != YOU and m.get(b, False)})
            for p, ms in by_prompt.items()
            if not any(m.get(YOU, False) for m in ms)]
    opps = [(p, cs) for p, cs in opps if len(cs) >= 2]
    present = [p for p in PLATFORMS if any(plat_you.get(p, []))]
    absent = [p for p in PLATFORMS if p not in present]

    # leaderboard
    board = "".join(
        f"<div class='lead-row'><span class='name'>{'&#9658; ' if b == YOU else ''}"
        f"{esc(b)}{' (you)' if b == YOU else ''}</span>"
        f"<div class='bar{' you' if b == YOU else ''}'>"
        f"<div style='width:{v:.0f}%'></div></div><b>{v:.0f}%</b></div>"
        for b, v in ranking)

    # insights
    insights = [
        f"Your AI share of voice is <b>{your:.0f}%</b> — rank <b>#{rank} of "
        f"{len(BRANDS)}</b> tracked brands. Current leader: <b>{esc(leader)}</b> "
        f"({leader_v:.0f}%).",
        f"You appear in answers for <b>{appear} of {len(by_prompt)}</b> tracked "
        f"prompts; present on <b>{esc(', '.join(present) or 'no platform')}</b>"
        + (f", absent on <b>{esc(', '.join(absent))}</b>." if absent else "."),
        f"Your site was cited as a source in <b>{cited} of {total}</b> AI answers "
        f"this run.",
    ]
    if opps:
        ex = esc(opps[0][0][:70])
        insights.append(
            f"<b>{len(opps)} prompts</b> show multiple competitors but not you — "
            f"top opportunity: \u201c{ex}\u201d.")
    try:
        row = con.execute(
            "SELECT COUNT(*) FROM discovered WHERE ai_search_volume > 100").fetchone()
        if row and row[0]:
            insights.append(
                f"<b>{row[0]} high-volume real user questions</b> found in AI search "
                f"(see Discovered prompts) — candidates to add to the tracker.")
    except sqlite3.OperationalError:
        pass
    try:
        row = con.execute(
            "SELECT COUNT(*) FROM silent WHERE day=(SELECT MAX(day) FROM silent)"
        ).fetchone()
        if row and row[0]:
            insights.append(
                f"<b>{row[0]} AI answers use your content without naming your brand</b> "
                f"(silent citations — see below).")
    except sqlite3.OperationalError:
        pass

    kpis = (
        f"<div class='kpis'>"
        f"<div class='kpi'><div class='num'>{your:.0f}%</div>"
        f"<div class='label'>AI share of voice<br>{delta_html}</div></div>"
        f"<div class='kpi'><div class='num'>#{rank}<span class='sub'> / "
        f"{len(BRANDS)}</span></div><div class='label'>competitive rank in AI answers</div></div>"
        f"<div class='kpi'><div class='num'>{appear}/{len(by_prompt)}</div>"
        f"<div class='label'>prompts where AI mentions you</div></div>"
        f"<div class='kpi'><div class='num'>{cited}/{total}</div>"
        f"<div class='label'>AI answers citing your site</div></div>"
        f"</div>")
    bullets = "".join(f"<li>{i}</li>" for i in insights)
    return (f"<h2>Executive summary — {esc(days[0])}</h2>{kpis}"
            f"<div class='card'><b>Competitive leaderboard"
            f" (% of AI answers mentioning each brand)</b>{board}"
            f"<ul class='insights'>{bullets}</ul></div>"
            f"<p class='sub no-print'>Presenting? Use your browser's Print "
            f"(Ctrl/Cmd+P) &rarr; Save as PDF — print view hides the raw answers.</p>")


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
            f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>LLM Visibility Dashboard</title>"
            f"<link rel='preconnect' href='https://fonts.googleapis.com'>"
            f"<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>"
            f"<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap' rel='stylesheet'>"
            f"<style>{CSS}</style></head>"
            f"<body><div class='wrap'>"
            f"<div class='hero'>"
            f"<div class='eyebrow'>AI search analytics</div>"
            f"<h1>LLM Visibility Dashboard</h1>"
            f"<div class='sub'>brand: {esc(YOU)} · domain: {esc(MY_DOMAIN)} · "
            f"platforms: {esc(', '.join(PLATFORMS))} · "
            f"generated {datetime.now():%Y-%m-%d %H:%M}</div></div>"
            f"{exec_summary(con)}{trend_section(con)}{volume_section(con)}"
            f"{discovered_section(con)}{silent_section(con)}{latest_section(con)}"
            f"</div></body></html>")
    OUT.write_text(page, encoding="utf-8")
    print(f"Dashboard written to: {OUT}")
    if args.open:
        webbrowser.open(OUT.as_uri())


if __name__ == "__main__":
    main()
