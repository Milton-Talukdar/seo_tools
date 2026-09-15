-- Patch v13: site audit runs gain a crawl_source column.
-- Run once in the Supabase SQL editor.

ALTER TABLE site_audit_runs ADD COLUMN IF NOT EXISTS crawl_source TEXT DEFAULT 'custom';

NOTIFY pgrst, 'reload schema';
