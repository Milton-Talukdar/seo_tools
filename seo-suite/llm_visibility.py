#!/usr/bin/env python3
"""
llm_visibility.py — weekly brand-visibility tracker across ChatGPT, Claude, Gemini, Perplexity.

Port of llm-keyword-tracker/llm_track.py writing into the shared seo_suite.db
(table llm_snapshots). Reads prompts from prompts.csv, asks each LLM via the
DataForSEO AI Optimization API, detects brand mentions and citations, and
stores dated snapshots.

Usage:
    python3 llm_visibility.py              # run all prompts on all platforms, save + report
    python3 llm_visibility.py --dry-run    # show what would run; no API calls, no cost
    python3 llm_visibility.py --limit 2    # only the first 2 prompts (cheap smoke test)
    python3 llm_visibility.py --report     # no API calls; show share-of-voice trend from DB
"""
import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

from common import DB_PATH, dfs_post, init_db, load_env, supabase_upsert

HERE = Path(__file__).parent
PROMPTS_CSV = HERE / "prompts.csv"

# ---- edit these ------------------------------------------------------------
BRANDS = ["vantage circle", "bonusly", "kudos", "achievers", "awardco",
          "nectar", "motivosity", "o.c. tanner", "workhuman"]
MY_DOMAIN = "vantagecircle.com"      # used to detect citations of your site
PLATFORMS = ["chat_gpt", "perplexity"]  # claude/gemini dropped 2026-07-27 to halve cost — re-add anytime
MODELS = {"chat_gpt": "gpt-5.5",     # pinned for comparable runs over time
          "claude": "claude-sonnet-4-6",
          "gemini": "gemini-2.5-flash",
          "perplexity": "sonar"}     # run --models flag to list available versions
LOCATION_CODE = 2840                 # 2840 = United States
LANGUAGE = "English"
DELAY_SECONDS = 1                    # pause between API calls
MAX_RUNTIME_SECONDS = 45 * 60        # hard ceiling so GitHub Actions never hangs
LLM_TIMEOUT = 60                     # per-call timeout for the AI Optimization API
LLM_RETRIES = 1                      # one retry on transient timeout/error
# -----------------------------------------------------------------------------

URL_RE = re.compile(r"https?://[^\s)\]>\"']+")


def extract(obj):
    """Schema-agnostic: pull all answer text and URLs out of a result object."""
    texts, links = [], set()

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("text", "answer", "markdown", "content") and isinstance(v, str):
                    texts.append(v)
                elif k in ("url", "link") and isinstance(v, str):
                    links.add(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(obj)
    answer = "\n".join(texts)
    links.update(URL_RE.findall(answer))  # inline markdown links live in the text
    return answer, sorted(links)


def ask_llm(platform, prompt):
    task = {"user_prompt": prompt,
            "language_name": LANGUAGE,
            "location_code": LOCATION_CODE}
    if MODELS.get(platform):
        task["model_name"] = MODELS[platform]
    result = dfs_post(f"/ai_optimization/{platform}/llm_responses/live", [task],
                      retries=LLM_RETRIES, timeout=LLM_TIMEOUT)
    return extract(result)


def detect_mentions(answer):
    # strip dots so "O.C. Tanner", "OC Tanner" etc. all match one brand entry
    low = answer.lower().replace(".", "")
    return {b: bool(re.search(r"(?<![a-z])" + re.escape(b.lower().replace(".", ""))
                              + r"(?![a-z])", low))
            for b in BRANDS}


def report(con):
    days = [r[0] for r in con.execute(
        "SELECT DISTINCT day FROM llm_snapshots ORDER BY day DESC LIMIT 8")]
    if not days:
        print("No data yet. Run the tracker first.")
        return
    for day in days:
        print(f"\n=== {day} — share of voice (% of prompts mentioning each brand) ===")
        for platform in PLATFORMS:
            rows = con.execute(
                "SELECT mentions, cited_mine FROM llm_snapshots WHERE day=? AND platform=?",
                (day, platform)).fetchall()
            if not rows:
                continue
            n = len(rows)
            sov = {b: sum(json.loads(m).get(b, False) for m, _ in rows) / n * 100 for b in BRANDS}
            cited = sum(c for _, c in rows) / n * 100
            top = "  ".join(f"{b}: {v:.0f}%" for b, v in sov.items() if v > 0) or "—"
            print(f"  {platform:11s} {top}   | your site cited: {cited:.0f}%")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    con = init_db()
    if args.report:
        report(con)
        return

    prompts = [l.strip() for l in open(PROMPTS_CSV, encoding="utf-8")
               if l.strip() and not l.startswith("#")]
    if args.limit:
        prompts = prompts[:args.limit]
    total = len(prompts) * len(PLATFORMS)
    print(f"{len(prompts)} prompts x {len(PLATFORMS)} platforms = {total} API calls"
          f"  (~${total * 0.01:.2f} max)")
    if args.dry_run:
        for p in prompts:
            print("  -", p)
        return

    load_env()
    today = date.today().isoformat()
    done = 0
    rows = []
    started_at = time.time()
    time_exceeded = False
    for prompt in prompts:
        for platform in PLATFORMS:
            if time.time() - started_at > MAX_RUNTIME_SECONDS:
                time_exceeded = True
                print(f"\nWARNING: stopping after ~{MAX_RUNTIME_SECONDS // 60} min runtime ceiling",
                      file=sys.stderr)
                break
            try:
                answer, links = ask_llm(platform, prompt)
            except Exception as e:
                print(f"ERROR {platform} | {prompt[:40]}: {e}", file=sys.stderr)
                continue
            mentions = detect_mentions(answer)
            cited = any(MY_DOMAIN in u for u in links)
            con.execute("INSERT OR REPLACE INTO llm_snapshots VALUES (?,?,?,?,?,?,?)",
                        (today, platform, prompt, json.dumps(mentions),
                         int(cited), json.dumps(links), answer))
            con.commit()
            rows.append({
                "day": today,
                "platform": platform,
                "prompt": prompt,
                "mentions": json.dumps(mentions),
                "cited_mine": int(cited),
                "links": json.dumps(links),
                "answer": answer,
            })
            done += 1
            found = " ".join(b for b, m in mentions.items() if m) or "—"
            print(f"[{done}/{total}] {platform:11s} {prompt[:45]:45s} "
                  f"mentions: {found}{'  +CITED' if cited else ''}")
            time.sleep(DELAY_SECONDS)
        if time_exceeded:
            break
    print(f"\nSaved {done}/{total} results to {DB_PATH.name}")
    supabase_upsert("llm_snapshots", rows)
    report(con)


if __name__ == "__main__":
    main()
