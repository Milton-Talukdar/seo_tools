# Vantage Circle SEO Suite

One tool, four jobs: weekly Google rank tracking, weekly backlink profile
snapshots, LLM brand-visibility tracking, and monthly content freshness / decay
monitoring — all feeding one SQLite DB and one HTML dashboard. Python 3 standard
library only, using the DataForSEO API.

The LLM module is a port of `../llm-keyword-tracker` (the original keeps
running in parallel until you decide to retire it; its history was imported
into this DB).

## Files

- `rank_track.py` — Google US top-100 rank tracker, multi-property (config constants at the top)
- `backlinks.py` — backlink totals + new/lost refdomain counts
- `llm_visibility.py` — LLM share-of-voice tracker (port of llm_track.py)
- `llm_discover.py` — monthly job: AI search volumes + real user questions (self-throttled to once per 25 days, `--force` to override)
- `enrich.py` — monthly job: refreshes volume + KD + intent in keyword_meta (self-throttled to once per 25 days, `--force` to override)
- `freshness.py` — monthly job: crawl configured sitemaps, score pages on age/depth/rank, and flag decay risk + recommended action
- `freshness_sitemaps.csv` — sitemap config: `property,page_type,sitemap_url`
- `import_ahrefs.py` — importer: Ahrefs overview export (positions + tags + volume/KD/intent + traffic), rank CSV, lost-refdomains CSV, and old llm_visibility.db history
- `dashboard.py` — builds a single `index.html` with a section per module
- `common.py` — shared plumbing (credentials, API POST, DB schema, dashboard CSS)
- `keywords.csv` — Vantage Circle tracked keywords, `keyword,tag` per line; `#` lines are comments (seeded with the 994-keyword Ahrefs export)
- `keywords-fit.csv` — Vantage Fit tracked keywords, same format
- `prompts.csv` / `seeds.csv` — LLM prompts and discovery seeds
- `.env` — DataForSEO credentials (never commit; falls back to `../llm-keyword-tracker/.env`)
- `seo_suite.db` — SQLite results, created on first run

## Usage

```bash
python3 rank_track.py --dry-run      # preview calls, zero cost
python3 rank_track.py --limit 3      # cheap smoke test (first 3 keywords only)
python3 rank_track.py --property vantagefit  # track just one property
python3 rank_track.py                # full run: all properties, all keywords
python3 rank_track.py --report       # movers + top-3/10/50 counts, no API calls
python3 backlinks.py                 # backlink snapshot (~$0.02)
python3 backlinks.py --report        # net change + notable losses, no API calls
python3 llm_visibility.py            # LLM share-of-voice run
python3 llm_discover.py --force      # volumes + real-prompt mining (~$1.45)
python3 enrich.py --dry-run          # preview volume/KD/intent refresh cost
python3 enrich.py --force            # refresh keyword_meta now (~$0.85)
python3 freshness.py --dry-run       # preview which pages would be crawled
python3 freshness.py --limit 20      # smoke test: 20 URLs per sitemap
python3 freshness.py --force         # full monthly freshness/decay run
python3 dashboard.py --open          # build index.html and open it in your browser

# Ahrefs history imports (read-only on all sources):
python3 import_ahrefs.py overview ~/Downloads/vc-full-site_overview_….csv
python3 import_ahrefs.py overview ~/Downloads/fit_overview_….csv --property vantagefit
python3 import_ahrefs.py ranks ~/Downloads/ahrefs-rank-tracker.csv
python3 import_ahrefs.py refdomains ~/Downloads/ahrefs-lost-refdomains.csv
python3 import_ahrefs.py llm-history   # carries over old llm_visibility.db
```

## Schedule

The GitHub Action (`.github/workflows/seo-suite.yml`) fires every Monday 06:53 UTC:
rank tracking + backlinks weekly, LLM visibility on even ISO weeks (biweekly is
enough — LLM answers drift slowly), LLM discovery monthly (self-throttled), and
content freshness / decay on the 1st of every month (or `--force`).
Manual runs (Actions tab → Run workflow) always execute everything.

## Cost

- Rank tracking: ~$0.0006/keyword → 994 keywords weekly ≈ $0.60/run ≈ **$31/yr**
- Backlinks: two calls weekly — pennies (≈ $1/yr)
- LLM visibility + discovery: ≈ **$26/yr** (unchanged from llm-keyword-tracker)
- Keyword enrichment (volume/KD/intent): ≈ $0.85/month ≈ **$10/yr**
- Content freshness / decay: **free** (sitemap/page crawl only; optional GSC traffic data is also free)

Total run rate ≈ $68/yr on the existing DataForSEO subscription.

## Optional: Google Search Console traffic data

`freshness.py` Phase 2 can pull real 28-day traffic trends from GSC. To enable it
in CI, create a Google service account, download its JSON key, and paste the
entire JSON into a GitHub secret named `GSC_SERVICE_ACCOUNT_JSON`. Without this
secret the module still works using rank-trend data only.

## Customizing

- **Keywords:** tracked keywords live in `keywords.csv` (Vantage Circle, 994
  keywords seeded from the Ahrefs rank-tracker overview export, with owner tags
  preserved) and `keywords-fit.csv` (Vantage Fit — paste keyword+tag rows there
  or import a VF overview export with
  `python3 import_ahrefs.py overview <file> --property vantagefit`).
  Format: `keyword,tag` — one per line, tag optional.
- **Brands / domain / models / location:** constants at the top of each module
- **History:** `import_ahrefs.py overview` backfills previous/current positions,
  tags, volume, KD, CPC, intent, SERP features, and traffic in one pass; run it
  again any time you have a fresh Ahrefs export

## Notes

- The DataForSEO link index is smaller than Ahrefs' — `backlinks.py` covers
  trend monitoring; deep forensic exports may still warrant Ahrefs.
- LLM answers are stochastic — trust trends over many prompts and weeks, not single runs.
- Rerunning on the same day replaces that day's rows (INSERT OR REPLACE per day).
- DataForSEO docs: https://docs.dataforseo.com/v3/

## Later (out of scope for now)

- Keyword research / content gap on-demand screens (DataForSEO Labs API)
- GA panels
- Lighthouse site health module
