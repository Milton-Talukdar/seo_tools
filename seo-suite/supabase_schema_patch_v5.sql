-- Patch v5: GSC-derived probable LLM queries
-- Run once in the Supabase SQL editor.

-- Queries pulled from GSC that look like LLM / AI / conversational searches.
-- Kept per-property and per-day so historical comparisons are possible.
CREATE TABLE IF NOT EXISTS gsc_llm_queries (
  property TEXT NOT NULL,
  day DATE NOT NULL,
  query TEXT NOT NULL,
  clicks INTEGER NOT NULL DEFAULT 0,
  impressions INTEGER NOT NULL DEFAULT 0,
  ctr REAL NOT NULL DEFAULT 0,
  position REAL NOT NULL DEFAULT 0,
  llm_score INTEGER NOT NULL DEFAULT 0,
  llm_signals TEXT,
  PRIMARY KEY (property, day, query)
);

CREATE INDEX IF NOT EXISTS idx_gsc_llm_queries_day ON gsc_llm_queries(day DESC);
CREATE INDEX IF NOT EXISTS idx_gsc_llm_queries_score ON gsc_llm_queries(llm_score DESC);
