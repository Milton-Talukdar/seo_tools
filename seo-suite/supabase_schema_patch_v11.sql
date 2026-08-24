-- Patch v11: Keyword Research module — stored keyword opportunities + tracking.
-- Run once in the Supabase SQL editor.

CREATE TABLE IF NOT EXISTS keywords (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  keyword TEXT NOT NULL,
  property TEXT NOT NULL DEFAULT 'vantagecircle',
  country TEXT NOT NULL DEFAULT 'us',
  search_volume INTEGER DEFAULT 0,
  cpc REAL DEFAULT 0,
  competition REAL DEFAULT 0,
  keyword_difficulty INTEGER,
  search_intent TEXT,
  source TEXT NOT NULL DEFAULT 'manual',
  status TEXT NOT NULL DEFAULT 'idea' CHECK (status IN ('idea','targeting','ranking','ignored','pruned')),
  target_page TEXT,
  cluster TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  last_updated TIMESTAMPTZ DEFAULT now(),
  UNIQUE (keyword, property, country)
);

CREATE INDEX IF NOT EXISTS idx_keywords_property ON keywords(property, status);
CREATE INDEX IF NOT EXISTS idx_keywords_volume ON keywords(search_volume DESC);
CREATE INDEX IF NOT EXISTS idx_keywords_cluster ON keywords(cluster);
CREATE INDEX IF NOT EXISTS idx_keywords_keyword ON keywords USING gin (keyword gin_trgm_ops);

-- Helper view: keywords that exist in rank_snapshots but are not in keywords table.
-- Used to auto-suggest gaps without API cost.
CREATE OR REPLACE VIEW keyword_gaps AS
SELECT DISTINCT
  rs.property,
  rs.keyword,
  'rank' AS source,
  COUNT(*) OVER (PARTITION BY rs.property, rs.keyword) AS rank_signals
FROM rank_snapshots rs
LEFT JOIN keywords k ON k.property = rs.property AND lower(k.keyword) = lower(rs.keyword)
WHERE k.id IS NULL;

NOTIFY pgrst, 'reload schema';
