-- Patch v10: Content Engine enhancements — pipeline briefs + author index.
-- Run once in the Supabase SQL editor.

-- Editorial brief fields for the pipeline / content calendar.
ALTER TABLE content_pipeline ADD COLUMN IF NOT EXISTS brief_goal TEXT;
ALTER TABLE content_pipeline ADD COLUMN IF NOT EXISTS brief_outline TEXT;
ALTER TABLE content_pipeline ADD COLUMN IF NOT EXISTS brief_word_count INTEGER;
ALTER TABLE content_pipeline ADD COLUMN IF NOT EXISTS brief_keywords TEXT;
ALTER TABLE content_pipeline ADD COLUMN IF NOT EXISTS brief_competitors TEXT;

-- Make author lookups faster for the author analytics panel.
CREATE INDEX IF NOT EXISTS idx_content_inventory_authors ON content_inventory USING gin (authors gin_trgm_ops);

NOTIFY pgrst, 'reload schema';
