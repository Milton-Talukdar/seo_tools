# SEO Tools & Autonomous Growth Engines

A monorepo of custom-engineered SEO software, algorithmic diagnostics, LLM citation trackers, and daily search intelligence scrapers built by **Milton Talukdar** (SEO Manager & Organic Growth Lead).

---

## 📂 Repository Directory

```
seo_tools/
├── seo-suite/                  # Multi-property enterprise SEO engine (Python 3, DataForSEO, Supabase, Cloudflare)
├── daily-seo-digest/           # Daily automated SEO news intelligence digest (Python + Astro)
├── llm-keyword-tracker/        # AI search engine citation & prompt discovery tracker (SQLite, GSC)
├── traffic-drop-diagnostic/    # Interactive diagnostic engine for post-update traffic drop triage
├── content-freshness-scanner/  # Content decay & crawl-equity triage scoring microtool
├── title-pixel-counter/        # Pixel-accurate Google SERP title tag counter
└── workers/                    # Cloudflare Workers for edge keyword research & routing
```

---

## 🛠️ Tool & Module Breakdown

### 1. `seo-suite` — Enterprise SEO Automation & Orbit Dashboard
* **Stack:** Python 3 standard library, DataForSEO API, Supabase (PostgreSQL), Cloudflare R2 & Pages.
* **Capabilities:**
  - **Weekly Rank Tracking (`rank_track.py`):** Multi-property US Top-100 Google rank tracker for Vantage Circle and Vantage Fit across 994+ high-intent commercial keywords.
  - **Backlink Delta Engine (`backlinks.py`):** Automated weekly backlink profile diffing and net referring domain loss alerts.
  - **LLM Share-of-Voice (`llm_visibility.py`, `llm_discover.py`):** AI search volume and real-user prompt discovery across Gemini, ChatGPT, Claude, and Perplexity.
  - **Content Freshness & Decay Crawler (`freshness.py`):** Automated sitemap crawler evaluating URL age, directory depth, and rank velocity.
  - **Technical Site Audit Crawlers (`site_audit.py`, `screamingfrog_site_audit.py`, `dataforseo_site_audit.py`):** Automated crawl health, redirect chains, canonical consistency, and PageSpeed Insights Core Web Vitals.
  - **Cloud Automation:** Automated GitHub Actions cron workflows (`weekly-sync.yml`, `monthly-sync.yml`, `snapshot-r2.yml`).

### 2. `daily-seo-digest` — Automated Daily SEO Intelligence Digest
* **Stack:** Python, Astro, Tailwind CSS, GitHub Actions.
* **Capabilities:**
  - Scrapes and parses breaking updates from 8 authoritative search industry sources (*Google Search Central, Search Engine Roundtable, Google Search Liaison, SEJ, Search Engine Land, Moz, Ahrefs, SEMrush*).
  - Categorizes findings by operational urgency:
    - 🔴 **Action Required:** Urgent algorithmic shifts or immediate technical remediations.
    - 🟡 **Watch This Week:** SERP volatility, feature rollouts, and competitor movements.
    - 🟢 **Learn:** New architectural concepts, patents, and technical research.
    - 📰 **FYI Headlines:** Industry updates and platform announcements.
  - Compiles daily and weekly digests with clean Markdown reports and publishes to a high-speed Astro static frontend.

### 3. `llm-keyword-tracker` — LLM Brand Citation & Prompt Tracker
* **Stack:** Python, SQLite, DataForSEO / LLM APIs.
* **Capabilities:**
  - Tracks brand citation frequency and positioning in generative search answers (Google AI Overviews, ChatGPT Search, Perplexity, Claude).
  - Automates extraction of conversational question keywords directly from Google Search Console (GSC) search query exports.

### 4. `traffic-drop-diagnostic` — Organic Drop Diagnostic Engine
* **Stack:** Modern HTML5 / Vanilla JavaScript / CSS.
* **Capabilities:**
  - A guided decision-tree diagnostic tool designed for SEO teams to classify traffic drops accurately.
  - Differentiates algorithmic penalties (Helpful Content Updates, Core Updates) from technical breakages (indexation drops, 4xx/5xx spikes, canonical loops) and intentional cannibalization.

### 5. `content-freshness-scanner` — Content Decay & Triage Scanner
* **Stack:** HTML5, CSS3, JavaScript.
* **Capabilities:**
  - Evaluates page-level organic clicks, quarterly conversions, and category topical relevance.
  - Automatically outputs one of three clear algorithmic dispositions:
    - **Keep & Optimize:** High commercial value; update schema and inject primary data.
    - **Consolidate & 301 Redirect:** Overlapping intent; merge into parent pillar URL.
    - **Prune & 410 Gone:** Zero pipeline value off-niche; permanently remove to reclaim crawl equity.

### 6. `title-pixel-counter` — Google SERP Title Tag Pixel Counter
* **Stack:** Lightweight client-side DOM canvas pixel calculator.
* **Capabilities:**
  - Calculates the exact proportional pixel width of SEO `<title>` tags based on standard Google SERP typography (Arial 20px) to prevent truncation dots (`...`) before deployment.

### 7. `workers` — Cloudflare Edge Functions
* **Stack:** Cloudflare Workers JavaScript.
* **Capabilities:**
  - Serverless edge functions handling high-velocity keyword research endpoints and programmatic routing.

---

## 👤 Author
**Milton Talukdar**  
SEO Manager & Organic Growth Lead | Vantage Circle  
- LinkedIn: [linkedin.com/in/milton-talukdar](https://linkedin.com/in/milton-talukdar)
- Portfolio: [milton-talukdar.github.io](https://milton-talukdar.github.io/)
