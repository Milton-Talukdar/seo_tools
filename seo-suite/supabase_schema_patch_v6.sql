-- Patch v6: add page URL to GSC LLM queries
-- Run once in the Supabase SQL editor.

ALTER TABLE gsc_llm_queries ADD COLUMN IF NOT EXISTS page TEXT;

CREATE INDEX IF NOT EXISTS idx_gsc_llm_queries_page ON gsc_llm_queries(page);
