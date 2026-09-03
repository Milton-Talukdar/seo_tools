-- SaaS schema for Orbit
-- Run this in a fresh Supabase project SQL Editor.
-- This extends the original seo-suite schema with workspaces and multi-tenancy.

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------- workspaces
CREATE TABLE IF NOT EXISTS workspaces (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    owner_user_id UUID NOT NULL,
    plan TEXT NOT NULL DEFAULT 'free',
    dataforseo_login TEXT,
    dataforseo_password TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workspace_members (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'admin', 'member')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (workspace_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_members_user ON workspace_members(user_id);

-- ---------------------------------------------------------------- properties (domains / projects within a workspace)
CREATE TABLE IF NOT EXISTS properties (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,
    label TEXT NOT NULL,
    domain TEXT NOT NULL,
    you TEXT,
    brands TEXT,
    config_json JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (workspace_id, slug)
);

CREATE INDEX IF NOT EXISTS idx_properties_workspace ON properties(workspace_id);

-- ---------------------------------------------------------------- rank tracking
CREATE TABLE IF NOT EXISTS rank_snapshots (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    day DATE NOT NULL,
    keyword TEXT NOT NULL,
    property TEXT NOT NULL,
    position INTEGER,
    url TEXT,
    serp_features TEXT,
    PRIMARY KEY (workspace_id, day, keyword, property)
);
CREATE INDEX IF NOT EXISTS idx_rank_snapshots_workspace_day ON rank_snapshots(workspace_id, day DESC);
CREATE INDEX IF NOT EXISTS idx_rank_snapshots_url ON rank_snapshots(workspace_id, url);

-- ---------------------------------------------------------------- keyword metadata
CREATE TABLE IF NOT EXISTS keyword_meta (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
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
    PRIMARY KEY (workspace_id, property, keyword)
);

-- ---------------------------------------------------------------- backlinks
CREATE TABLE IF NOT EXISTS backlink_snapshots (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    day DATE NOT NULL,
    property TEXT NOT NULL,
    backlinks INTEGER,
    refdomains INTEGER,
    rank INTEGER,
    PRIMARY KEY (workspace_id, day, property)
);

CREATE TABLE IF NOT EXISTS refdomain_events (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    day DATE NOT NULL,
    property TEXT NOT NULL,
    event TEXT CHECK (event IN ('new', 'lost')),
    domain TEXT NOT NULL,
    rank INTEGER,
    PRIMARY KEY (workspace_id, day, property, event, domain)
);

-- ---------------------------------------------------------------- LLM visibility
CREATE TABLE IF NOT EXISTS llm_snapshots (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    day DATE NOT NULL,
    property TEXT NOT NULL,
    platform TEXT NOT NULL,
    prompt TEXT NOT NULL,
    mentions TEXT,
    cited_mine INTEGER,
    links TEXT,
    answer TEXT,
    PRIMARY KEY (workspace_id, day, property, platform, prompt)
);
CREATE INDEX IF NOT EXISTS idx_llm_snapshots_workspace_day ON llm_snapshots(workspace_id, day DESC);

CREATE TABLE IF NOT EXISTS volumes (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    day DATE NOT NULL,
    property TEXT NOT NULL,
    keyword TEXT NOT NULL,
    ai_search_volume INTEGER,
    trend_json TEXT,
    PRIMARY KEY (workspace_id, day, property, keyword)
);

CREATE TABLE IF NOT EXISTS discovered (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    property TEXT NOT NULL,
    query TEXT NOT NULL,
    platform TEXT,
    ai_search_volume INTEGER,
    seed TEXT,
    first_seen DATE,
    last_seen DATE,
    PRIMARY KEY (workspace_id, property, query)
);

CREATE TABLE IF NOT EXISTS silent (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    day DATE NOT NULL,
    property TEXT NOT NULL,
    query TEXT NOT NULL,
    platform TEXT,
    ai_search_volume INTEGER,
    PRIMARY KEY (workspace_id, day, property, query, platform)
);

-- ---------------------------------------------------------------- keyword research
CREATE TABLE IF NOT EXISTS keyword_research (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
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
    PRIMARY KEY (workspace_id, seed, source, keyword)
);

CREATE TABLE IF NOT EXISTS seed_overview (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    seed TEXT NOT NULL,
    volume INTEGER,
    kd REAL,
    cpc REAL,
    competition REAL,
    intent TEXT,
    serp_features TEXT,
    fetched DATE,
    PRIMARY KEY (workspace_id, seed)
);

-- ---------------------------------------------------------------- competitor tracker
CREATE TABLE IF NOT EXISTS competitor_pages (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    id SERIAL,
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
    PRIMARY KEY (workspace_id, property, competitor, url)
);
CREATE INDEX IF NOT EXISTS idx_competitor_pages_workspace ON competitor_pages(workspace_id, property, competitor, url);

CREATE TABLE IF NOT EXISTS competitor_changes (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
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
CREATE INDEX IF NOT EXISTS idx_competitor_changes_workspace ON competitor_changes(workspace_id, url);
CREATE INDEX IF NOT EXISTS idx_competitor_changes_workspace_ts ON competitor_changes(workspace_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS competitor_snapshots (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    day DATE NOT NULL,
    property TEXT NOT NULL,
    competitor TEXT NOT NULL,
    domain TEXT,
    total_urls INTEGER,
    last_crawl DATE,
    last_successful_crawl DATE,
    pages_hashed INTEGER,
    hash_failures INTEGER,
    PRIMARY KEY (workspace_id, day, property, competitor)
);

-- ---------------------------------------------------------------- content freshness / decay
CREATE TABLE IF NOT EXISTS freshness_scores (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
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
    canonical_ok INTEGER,
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
    PRIMARY KEY (workspace_id, day, url)
);
CREATE INDEX IF NOT EXISTS idx_freshness_scores_workspace_property ON freshness_scores(workspace_id, property, day DESC);
CREATE INDEX IF NOT EXISTS idx_freshness_scores_workspace_action ON freshness_scores(workspace_id, action);

-- ---------------------------------------------------------------- site health / audit
CREATE TABLE IF NOT EXISTS site_audit_runs (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    day DATE NOT NULL,
    property TEXT NOT NULL,
    pages_crawled INTEGER,
    pages_failed INTEGER,
    issues_found INTEGER,
    psi_calls INTEGER,
    run_duration_seconds INTEGER,
    crawl_source TEXT DEFAULT 'custom',
    PRIMARY KEY (workspace_id, day, property)
);

CREATE TABLE IF NOT EXISTS site_audit_pages (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    day DATE NOT NULL,
    property TEXT NOT NULL,
    url TEXT NOT NULL,
    status_code INTEGER,
    final_url TEXT,
    title TEXT,
    meta_description TEXT,
    h1 TEXT,
    canonical TEXT,
    canonical_ok INTEGER,
    word_count INTEGER,
    internal_links INTEGER,
    external_links INTEGER,
    has_viewport INTEGER,
    redirect_count INTEGER,
    lcp REAL,
    inp REAL,
    cls REAL,
    performance_score INTEGER,
    seo_score INTEGER,
    psi_status TEXT,
    fetch_error TEXT,
    inlinks INTEGER,
    outlinks INTEGER,
    response_time_ms INTEGER,
    structured_data_types TEXT,
    lighthouse_performance INTEGER,
    PRIMARY KEY (workspace_id, day, property, url)
);

CREATE TABLE IF NOT EXISTS site_audit_issues (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    day DATE NOT NULL,
    property TEXT NOT NULL,
    url TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    severity TEXT CHECK (severity IN ('critical', 'warning', 'info')),
    details TEXT,
    PRIMARY KEY (workspace_id, day, property, url, issue_type)
);

CREATE INDEX IF NOT EXISTS idx_site_audit_issues_workspace ON site_audit_issues(workspace_id, day, property);
CREATE INDEX IF NOT EXISTS idx_site_audit_issues_workspace_severity ON site_audit_issues(workspace_id, day, severity);
CREATE INDEX IF NOT EXISTS idx_site_audit_pages_workspace ON site_audit_pages(workspace_id, day, property);

-- ---------------------------------------------------------------- enrichment run log
CREATE TABLE IF NOT EXISTS enrich_log (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    day DATE PRIMARY KEY
);

-- ---------------------------------------------------------------- Row Level Security (RLS)
ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE workspace_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE properties ENABLE ROW LEVEL SECURITY;
ALTER TABLE rank_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE keyword_meta ENABLE ROW LEVEL SECURITY;
ALTER TABLE backlink_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE refdomain_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE volumes ENABLE ROW LEVEL SECURITY;
ALTER TABLE discovered ENABLE ROW LEVEL SECURITY;
ALTER TABLE silent ENABLE ROW LEVEL SECURITY;
ALTER TABLE keyword_research ENABLE ROW LEVEL SECURITY;
ALTER TABLE seed_overview ENABLE ROW LEVEL SECURITY;
ALTER TABLE competitor_pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE competitor_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE competitor_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE freshness_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE site_audit_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE site_audit_pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE site_audit_issues ENABLE ROW LEVEL SECURITY;
ALTER TABLE enrich_log ENABLE ROW LEVEL SECURITY;

-- Policies: users can read/write data for workspaces they are members of.
-- The worker will send the authenticated user's JWT as the Authorization header
-- and use `request.jwt.claims.sub` to match user_id.

CREATE POLICY workspaces_member_select ON workspaces
    FOR SELECT USING (EXISTS (
        SELECT 1 FROM workspace_members m
        WHERE m.workspace_id = workspaces.id AND m.user_id = auth.uid()
    ));

CREATE POLICY workspaces_owner_update ON workspaces
    FOR UPDATE USING (owner_user_id = auth.uid());

CREATE POLICY workspace_members_select ON workspace_members
    FOR SELECT USING (user_id = auth.uid());

CREATE POLICY workspace_members_owner_insert ON workspace_members
    FOR INSERT WITH CHECK (EXISTS (
        SELECT 1 FROM workspaces w WHERE w.id = workspace_members.workspace_id AND w.owner_user_id = auth.uid()
    ));

CREATE POLICY properties_select ON properties
    FOR SELECT USING (EXISTS (
        SELECT 1 FROM workspace_members m
        WHERE m.workspace_id = properties.workspace_id AND m.user_id = auth.uid()
    ));

CREATE POLICY properties_insert ON properties
    FOR INSERT WITH CHECK (EXISTS (
        SELECT 1 FROM workspace_members m
        WHERE m.workspace_id = properties.workspace_id AND m.user_id = auth.uid()
    ));

-- Generic policy template for data tables
DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOR tbl IN VALUES
        ('rank_snapshots'), ('keyword_meta'), ('backlink_snapshots'), ('refdomain_events'),
        ('llm_snapshots'), ('volumes'), ('discovered'), ('silent'),
        ('keyword_research'), ('seed_overview'),
        ('competitor_pages'), ('competitor_changes'), ('competitor_snapshots'),
        ('freshness_scores'), ('site_audit_runs'), ('site_audit_pages'), ('site_audit_issues'),
        ('enrich_log')
    LOOP
        EXECUTE format(
            'CREATE POLICY %I_select ON %I FOR SELECT USING (EXISTS (
                SELECT 1 FROM workspace_members m
                WHERE m.workspace_id = %I.workspace_id AND m.user_id = auth.uid()
            ))',
            tbl || '_member', tbl, tbl
        );
        EXECUTE format(
            'CREATE POLICY %I_insert ON %I FOR INSERT WITH CHECK (EXISTS (
                SELECT 1 FROM workspace_members m
                WHERE m.workspace_id = %I.workspace_id AND m.user_id = auth.uid()
            ))',
            tbl || '_member_insert', tbl, tbl
        );
    END LOOP;
END $$;

NOTIFY pgrst, 'reload schema';
