-- Patch v2 for already-created Supabase SEO Suite projects.
-- Apply in Supabase Dashboard → SQL Editor.

-- Ensure competitor_pages.id auto-increments for new rows even if the column
-- was originally created as INTEGER PRIMARY KEY without a sequence.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_sequences
        WHERE schemaname = 'public' AND sequencename = 'competitor_pages_id_seq'
    ) THEN
        CREATE SEQUENCE competitor_pages_id_seq;
        ALTER TABLE competitor_pages
            ALTER COLUMN id SET DEFAULT nextval('competitor_pages_id_seq');
        SELECT setval('competitor_pages_id_seq', COALESCE(MAX(id), 1))
            FROM competitor_pages;
        ALTER SEQUENCE competitor_pages_id_seq OWNED BY competitor_pages.id;
    END IF;
END
$$;

-- Enrichment run log (used by enrich.py)
CREATE TABLE IF NOT EXISTS enrich_log (
    day DATE PRIMARY KEY
);
