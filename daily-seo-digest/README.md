# Daily SEO News Digest

> Automated daily report of SEO news — filtered, categorized, and prioritized for action.

## What It Does

Every day, this tool fetches the latest SEO news from 8 authoritative sources, scores each article for relevance to your work, and generates a clean Markdown report organized into:

- **🔴 Action Required** — Things to do today
- **🟡 Watch This Week** — Monitor and check back later
- **🟢 Learn** — New concepts worth studying
- **📰 FYI Headlines** — Everything else, summarized

## Sources

| Source | Priority | What You Get |
|--------|----------|--------------|
| Google Search Central | 🔴 High | Official algorithm updates |
| Search Engine Roundtable | 🔴 High | Breaking news, daily digest |
| Google Search Liaison | 🔴 High | Direct from Google |
| Search Engine Journal | 🟡 Medium | Industry analysis |
| Search Engine Land | 🟡 Medium | Platform updates |
| Moz Blog | 🟡 Medium | Technical SEO |
| Ahrefs Blog | 🟡 Medium | Data-backed research |
| SEMrush Blog | 🟡 Medium | Marketing trends |

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run Once (Test)

```bash
python run.py
```

This fetches today's news and saves a report to `reports/YYYY-MM-DD.md`.

### 3. Schedule Daily (Cron)

Open your crontab:
```bash
crontab -e
```

Add this line to run every weekday at 9 AM:
```bash
0 9 * * 1-5 cd /path/to/seo-news-tool && /usr/bin/python3 run.py
```

Or run manually whenever you want:
```bash
python run.py --open    # Generates + opens the report
python run.py --dry-run # Preview without saving
```

## Configuration

Edit `config.yaml` to customize:

```yaml
# Add/remove RSS sources
sources:
  - name: "Your Custom Source"
    url: "https://example.com/feed"
    priority: high

# Adjust relevance keywords
relevance_keywords:
  - "algorithm update"
  - "core web vitals"
  - "your company name"
  - "product page"

# Report settings
report:
  output_dir: "reports"
  max_headlines: 15
  max_action_items: 8
  max_learn_items: 5
```

## Report Example

```markdown
# Daily SEO Digest — 2026-05-11

## 🔴 Action Required

**[Google Confirms March 2026 Core Update](link)** — *Search Engine Roundtable*
> Google has confirmed a broad core update rolling out this week...
> 🏷️ `algorithm update`, `core update`, `ranking factor`

## 🟡 Watch This Week

**[Google Testing AI Overlays in Local Search](link)** — *Search Engine Land*
> Google is experimenting with AI-generated summaries...
> 🏷️ `AI overview`, `local SEO`

## 🟢 Learn

**[How to Optimize for Entity-Based Search](link)** — *Moz Blog*
> A deep dive into entity optimization techniques...
> 🏷️ `entity`, `E-E-A-T`, `content optimization`

## 📰 FYI Headlines

- **[SEMrush Acquires Tiny Analytics Startup](link)** — *SEMrush Blog*
- **[New Schema Types for Product Reviews](link)** — *Google Search Central*
```

## How It Works

1. **Fetch** — Pulls RSS feeds from all configured sources
2. **Deduplicate** — Removes duplicate articles across sources
3. **Score** — Matches titles/summaries against relevance keywords
4. **Categorize** — Sorts articles into Action/Watch/Learn/FYI using trigger keywords
5. **Generate** — Builds a clean Markdown report with summaries and tags
6. **Save** — Writes to `reports/YYYY-MM-DD.md`

## No API Keys Needed

This tool works entirely offline using RSS feeds and rule-based categorization. No OpenAI, no Claude, no paid APIs.

If you want AI-powered summarization, fork the repo and plug in your preferred LLM API in `generate_report.py`.

## Directory Structure

```
seo-news-tool/
├── config.yaml           # Sources, keywords, settings
├── fetch_news.py         # RSS fetching + relevance scoring
├── generate_report.py    # Markdown report builder
├── run.py                # Main orchestrator
├── requirements.txt      # Dependencies
├── reports/              # Generated reports
│   ├── 2026-05-11.md
│   ├── 2026-05-12.md
│   └── ...
└── README.md
```

## License

MIT
