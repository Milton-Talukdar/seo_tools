# Vantage Circle SEO Suite

One tool, three jobs: weekly Google rank tracking, weekly backlink profile
snapshots, and LLM brand-visibility tracking — all feeding one SQLite DB and
one HTML dashboard. Python 3 standard library only, using the DataForSEO API.

The LLM module is a port of `../llm-keyword-tracker` (the original keeps
running in parallel until you decide to retire it; its history was imported
into this DB).

## Files

- `rank_track.py` — Google US top-100 rank tracker (config constants at the top)
- `backlinks.py` — backlink totals + new/lost refdomain counts
- `llm_visibility.py` — LLM share-of-voice tracker (port of llm_track.py)
- `llm_discover.py` — monthly job: AI search volumes + real user questions (self-throttled to once per 25 days, `--force` to override)
- `import_ahrefs.py` — ONE-TIME importer: Ahrefs rank CSV, lost-refdomains CSV, and old llm_visibility.db history
- `dashboard.py` — builds a single `index.html` with a section per module
- `common.py` — shared plumbing (credentials, API POST, DB schema, dashboard CSS)
- `keywords.csv` — tracked keywords, one per line; `#` lines are comments
- `prompts.csv` / `seeds.csv` — LLM prompts and discovery seeds
- `.env` — DataForSEO credentials (never commit; falls back to `../llm-keyword-tracker/.env`)
- `seo_suite.db` — SQLite results, created on first run

## Usage

```bash
python3 rank_track.py --dry-run      # preview calls, zero cost
python3 rank_track.py --limit 3      # cheap smoke test (first 3 keywords only)
python3 rank_track.py                # full run: all keywords
python3 rank_track.py --report       # movers + top-3/10/50 counts, no API calls
python3 backlinks.py                 # backlink snapshot (~$0.02)
python3 backlinks.py --report        # net change + notable losses, no API calls
python3 llm_visibility.py            # LLM share-of-voice run
python3 llm_discover.py --force      # volumes + real-prompt mining (~$1.45)
python3 dashboard.py --open          # build index.html and open it in your browser

# one-time history imports (read-only on all sources):
python3 import_ahrefs.py ranks ~/Downloads/ahrefs-rank-tracker.csv
python3 import_ahrefs.py refdomains ~/Downloads/ahrefs-lost-refdomains.csv
python3 import_ahrefs.py llm-history   # carries over old llm_visibility.db
```

## Schedule

The GitHub Action (`.github/workflows/seo-suite.yml`) fires every Monday 06:53 UTC:
rank tracking + backlinks weekly, LLM visibility on even ISO weeks (biweekly is
enough — LLM answers drift slowly), LLM discovery monthly (self-throttled).
Manual runs (Actions tab → Run workflow) always execute everything.

## Cost

- Rank tracking: ~$0.0006/keyword → 182 keywords weekly ≈ $0.11/run ≈ **$6/yr**
- Backlinks: two calls weekly — pennies (≈ $1/yr)
- LLM visibility + discovery: ≈ **$26/yr** (unchanged from llm-keyword-tracker)

Total run rate ≈ $33/yr on the existing DataForSEO subscription.

## Customizing

- **Keywords:** replace `keywords.csv` with the keyword column from your Ahrefs
  Rank Tracker export (one per line). The starter file holds the 20
  highest-value keywords from the Apr–Jun 2026 MoM analysis.
- **Brands / domain / models / location:** constants at the top of each module
- **History:** if you have Ahrefs exports, run `import_ahrefs.py` once to
  backfill rank and lost-refdomain history before the weekly runs start

## Notes

- The DataForSEO link index is smaller than Ahrefs' — `backlinks.py` covers
  trend monitoring; deep forensic exports may still warrant Ahrefs.
- LLM answers are stochastic — trust trends over many prompts and weeks, not single runs.
- Rerunning on the same day replaces that day's rows (INSERT OR REPLACE per day).
- DataForSEO docs: https://docs.dataforseo.com/v3/

## Later (out of scope for now)

- Keyword research / content gap on-demand screens (DataForSEO Labs API)
- GSC / GA panels (needs Google service-account credentials in CI)
- Lighthouse site health module
