-- Supabase schema for Vantage Circle SEO Suite
-- Run this in Supabase Dashboard → SQL Editor

-- Rank tracking
CREATE TABLE IF NOT EXISTS rank_snapshots (
    day DATE NOT NULL,
    keyword TEXT NOT NULL,
    property TEXT NOT NULL DEFAULT 'vantagecircle',
    position INTEGER,
    url TEXT,
    serp_features TEXT,
    PRIMARY KEY (day, keyword, property)
);
CREATE INDEX IF NOT EXISTS idx_rank_snapshots_url ON rank_snapshots(url);
CREATE INDEX IF NOT EXISTS idx_rank_snapshots_day ON rank_snapshots(day DESC);

-- Keyword metadata
CREATE TABLE IF NOT EXISTS keyword_meta (
    property TEXT NOT NULL,
    keyword TEXT NOT NULL,
    tag TEXT,
    volume INTEGER,
    kd REAL,
    cpc REAL,
    intent TEXT,
    branded INTEGER,
    serp_features TEXT,
    traffic_prev REAL,
    traffic_cur REAL,
    PRIMARY KEY (property, keyword)
);

-- Backlinks
CREATE TABLE IF NOT EXISTS backlink_snapshots (
    day DATE NOT NULL PRIMARY KEY,
    backlinks INTEGER,
    refdomains INTEGER,
    rank INTEGER
);

CREATE TABLE IF NOT EXISTS refdomain_events (
    day DATE NOT NULL,
    event TEXT CHECK (event IN ('new', 'lost')),
    domain TEXT NOT NULL,
    rank INTEGER,
    PRIMARY KEY (day, event, domain)
);

-- LLM visibility
CREATE TABLE IF NOT EXISTS llm_snapshots (
    day DATE NOT NULL,
    platform TEXT NOT NULL,
    prompt TEXT NOT NULL,
    mentions TEXT,
    cited_mine INTEGER,
    links TEXT,
    answer TEXT,
    PRIMARY KEY (day, platform, prompt)
);
CREATE INDEX IF NOT EXISTS idx_llm_snapshots_day ON llm_snapshots(day DESC);

-- LLM discovery / volumes
CREATE TABLE IF NOT EXISTS volumes (
    day DATE NOT NULL,
    keyword TEXT NOT NULL,
    ai_search_volume INTEGER,
    trend_json TEXT,
    PRIMARY KEY (day, keyword)
);

CREATE TABLE IF NOT EXISTS discovered (
    query TEXT PRIMARY KEY,
    platform TEXT,
    ai_search_volume INTEGER,
    seed TEXT,
    first_seen DATE,
    last_seen DATE
);

CREATE TABLE IF NOT EXISTS silent (
    day DATE NOT NULL,
    query TEXT NOT NULL,
    platform TEXT,
    ai_search_volume INTEGER,
    PRIMARY KEY (day, query, platform)
);

-- Keyword research
CREATE TABLE IF NOT EXISTS keyword_research (
    seed TEXT NOT NULL,
    source TEXT NOT NULL,
    keyword TEXT NOT NULL,
    volume INTEGER,
    kd REAL,
    cpc REAL,
    competition REAL,
    intent TEXT,
    serp_features TEXT,
    parent_topic TEXT,
    fetched DATE,
    PRIMARY KEY (seed, source, keyword)
);

CREATE TABLE IF NOT EXISTS seed_overview (
    seed TEXT PRIMARY KEY,
    volume INTEGER,
    kd REAL,
    cpc REAL,
    competition REAL,
    intent TEXT,
    serp_features TEXT,
    fetched DATE
);

-- Competitor tracker
CREATE TABLE IF NOT EXISTS competitor_pages (
    id SERIAL PRIMARY KEY,
    property TEXT NOT NULL,
    competitor TEXT NOT NULL,
    domain TEXT NOT NULL,
    url TEXT NOT NULL,
    last_seen DATE,
    title TEXT,
    meta TEXT,
    h1 TEXT,
    schemas TEXT,
    word_count INTEGER,
    content_hash TEXT,
    first_seen DATE,
    UNIQUE (property, competitor, url)
);
CREATE INDEX IF NOT EXISTS idx_competitor_pages_url ON competitor_pages(property, competitor, url);

CREATE TABLE IF NOT EXISTS competitor_changes (
    id TEXT PRIMARY KEY,
    timestamp TIMESTAMPTZ,
    property TEXT,
    competitor TEXT,
    domain TEXT,
    url TEXT,
    change_type TEXT,
    title TEXT,
    details_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_competitor_changes_url ON competitor_changes(url);
CREATE INDEX IF NOT EXISTS idx_competitor_changes_ts ON competitor_changes(timestamp DESC);

CREATE TABLE IF NOT EXISTS competitor_snapshots (
    day DATE NOT NULL,
    property TEXT NOT NULL,
    competitor TEXT NOT NULL,
    domain TEXT,
    total_urls INTEGER,
    last_crawl DATE,
    last_successful_crawl DATE,
    pages_hashed INTEGER,
    hash_failures INTEGER,
    PRIMARY KEY (day, property, competitor)
);

-- Content freshness / decay
CREATE TABLE IF NOT EXISTS freshness_scores (
    day DATE NOT NULL,
    url TEXT NOT NULL,
    property TEXT,
    page_type TEXT,
    title TEXT,
    h1 TEXT,
    published_date DATE,
    modified_date DATE,
    age_days INTEGER,
    word_count INTEGER,
    internal_links INTEGER,
    external_links INTEGER,
    schema_types TEXT,
    status_code INTEGER,
    canonical TEXT,
    freshness_score INTEGER,
    depth_score INTEGER,
    decay_risk TEXT,
    target_keyword TEXT,
    position INTEGER,
    volume INTEGER,
    rank_drop_30d REAL,
    rank_drop_60d REAL,
    rank_drop_90d REAL,
    traffic_28d INTEGER,
    traffic_prev_28d INTEGER,
    traffic_drop_pct REAL,
    decay_score REAL,
    priority_score REAL,
    action TEXT,
    reason TEXT,
    last_crawled TIMESTAMPTZ,
    PRIMARY KEY (day, url)
);
CREATE INDEX IF NOT EXISTS idx_freshness_scores_property ON freshness_scores(property, day DESC);
CREATE INDEX IF NOT EXISTS idx_freshness_scores_action ON freshness_scores(action);
