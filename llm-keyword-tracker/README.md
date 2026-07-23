# LLM Keyword Tracker

Tracks how often your brand (and competitors) is mentioned by ChatGPT, Claude, Gemini,
and Perplexity for a fixed set of prompts, using the DataForSEO AI Optimization API.
Snapshots are stored in SQLite so you can watch share of voice trend week over week.

## Files

- `llm_track.py` — the tracker (all config constants are at the top of this file)
- `prompts.csv` — one prompt per line; `#` lines are comments
- `.env` — DataForSEO credentials (never commit; already git-ignored)
- `llm_visibility.db` — SQLite results, created on first run

## Usage

```bash
python3 llm_track.py --dry-run    # preview calls, zero cost
python3 llm_track.py --limit 2    # cheap smoke test (first 2 prompts only)
python3 llm_track.py              # full run: all prompts x 4 platforms
python3 llm_track.py --report     # share-of-voice trend, no API calls
python3 dashboard.py --open       # build dashboard.html and open it in your browser
```

## Weekly schedule (cron)

```cron
17 6 * * 1  cd /Users/miltontalukdar/Desktop/Kimiseo/seo_tools/llm-keyword-tracker && /usr/bin/python3 llm_track.py >> tracker.log 2>&1
```

Mondays 06:17. Weekly is enough — LLM answers drift slowly.

## Cost

~$0.01 per prompt per platform. The seeded 6 prompts x 4 platforms x weekly ≈ $1/month.

## Customizing

- **Prompts:** edit `prompts.csv` (max 500 chars each)
- **Brands / domain / models / location:** constants at the top of `llm_track.py`
- **Available model versions:** query
  `GET /v3/ai_optimization/{platform}/llm_responses/models` (see DataForSEO docs)

## Notes

- LLM answers are stochastic — trust trends over many prompts and weeks, not single runs.
- Rerunning on the same day replaces that day's rows (one snapshot per day/prompt/platform).
- DataForSEO docs: https://docs.dataforseo.com/v3/ai_optimization-overview/
