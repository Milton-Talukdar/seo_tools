-- Patch v14: site_audit_pages gains Screaming Frog-derived metrics.
-- Run once in the Supabase SQL editor.

ALTER TABLE site_audit_pages
    ADD COLUMN IF NOT EXISTS inlinks INTEGER,
    ADD COLUMN IF NOT EXISTS outlinks INTEGER,
    ADD COLUMN IF NOT EXISTS response_time_ms INTEGER,
    ADD COLUMN IF NOT EXISTS structured_data_types TEXT,
    ADD COLUMN IF NOT EXISTS lighthouse_performance INTEGER;

NOTIFY pgrst, 'reload schema';
