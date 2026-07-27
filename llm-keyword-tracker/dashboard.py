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
.kpis { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 12px; }
.kpi { flex: 1; min-width: 150px; background: #fff; border: 1px solid #e4e6eb;
       border-radius: 10px; padding: 14px 16px; }
.kpi .num { font-size: 26px; font-weight: 700; }
.kpi .label { color: #65676b; font-size: 12px; margin-top: 2px; }
.delta { font-size: 12px; font-weight: 600; }
.delta.up { color: #1a7f37; }
.delta.down { color: #9b1c1c; }
.lead-row { display: flex; align-items: center; gap: 10px; margin: 6px 0; font-size: 13px; }
.lead-row .name { min-width: 140px; }
.lead-row .bar { flex: 1; }
.insights { margin: 8px 0 0; padding-left: 20px; }
.insights li { margin: 6px 0; font-size: 14px; }
@media print {
  body { background: #fff; }
  details, .no-print { display: none; }
  .card, .kpi { break-inside: avoid; }
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
            f"<title>LLM Visibility Dashboard</title><style>{CSS}</style></head>"
            f"<body><div class='wrap'>"
            f"<h1>LLM Visibility Dashboard</h1>"
            f"<div class='sub'>brand: {esc(YOU)} · domain: {esc(MY_DOMAIN)} · "
            f"platforms: {esc(', '.join(PLATFORMS))} · "
            f"generated {datetime.now():%Y-%m-%d %H:%M}</div>"
            f"{exec_summary(con)}{trend_section(con)}{volume_section(con)}"
            f"{discovered_section(con)}{silent_section(con)}{latest_section(con)}"
            f"</div></body></html>")
    OUT.write_text(page, encoding="utf-8")
    print(f"Dashboard written to: {OUT}")
    if args.open:
        webbrowser.open(OUT.as_uri())


if __name__ == "__main__":
    main()
