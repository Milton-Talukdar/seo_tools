-- Patch v7: expanded backlink tables (DataForSEO)
-- Run once in the Supabase SQL editor.
-- Note: GSC does not expose its Links report via public API, so this phase
-- uses DataForSEO only. Free link sources (Bing Webmaster Tools) can be added later.

-- Backlink snapshots now need a property column to store VC and VFit separately.
ALTER TABLE backlink_snapshots ADD COLUMN IF NOT EXISTS property TEXT NOT NULL DEFAULT 'vantagecircle';
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'backlink_snapshots_pkey'
  ) THEN
    ALTER TABLE backlink_snapshots DROP CONSTRAINT backlink_snapshots_pkey;
    ALTER TABLE backlink_snapshots ADD PRIMARY KEY (day, property);
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_backlink_snapshots_property ON backlink_snapshots(property, day DESC);

-- Top individual backlinks from DataForSEO
CREATE TABLE IF NOT EXISTS backlink_details (
  day DATE NOT NULL,
  property TEXT NOT NULL,
  source_url TEXT NOT NULL,
  target_url TEXT NOT NULL,
  domain TEXT NOT NULL,
  anchor TEXT,
  dofollow BOOLEAN DEFAULT true,
  first_seen DATE,
  rank INTEGER,
  PRIMARY KEY (day, property, source_url, target_url)
);
CREATE INDEX IF NOT EXISTS idx_backlink_details_day ON backlink_details(day DESC, property);
CREATE INDEX IF NOT EXISTS idx_backlink_details_domain ON backlink_details(domain);

-- Referring domains summary
CREATE TABLE IF NOT EXISTS referring_domains (
  day DATE NOT NULL,
  property TEXT NOT NULL,
  domain TEXT NOT NULL,
  backlinks INTEGER DEFAULT 0,
  ref_ips INTEGER DEFAULT 0,
  rank INTEGER,
  PRIMARY KEY (day, property, domain)
);
CREATE INDEX IF NOT EXISTS idx_referring_domains_day ON referring_domains(day DESC, property);
CREATE INDEX IF NOT EXISTS idx_referring_domains_rank ON referring_domains(rank DESC);

-- Anchor text distribution
CREATE TABLE IF NOT EXISTS anchor_distribution (
  day DATE NOT NULL,
  property TEXT NOT NULL,
  anchor TEXT NOT NULL,
  backlinks INTEGER DEFAULT 0,
  dofollow_backlinks INTEGER DEFAULT 0,
  PRIMARY KEY (day, property, anchor)
);
CREATE INDEX IF NOT EXISTS idx_anchor_distribution_day ON anchor_distribution(day DESC, property);

-- New/lost referring domain events are also per-property so VC and VFit don't overwrite each other.
ALTER TABLE refdomain_events ADD COLUMN IF NOT EXISTS property TEXT NOT NULL DEFAULT 'vantagecircle';
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'refdomain_events_pkey'
  ) THEN
    ALTER TABLE refdomain_events DROP CONSTRAINT refdomain_events_pkey;
    ALTER TABLE refdomain_events ADD PRIMARY KEY (day, property, event, domain);
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_refdomain_events_property ON refdomain_events(property, day DESC);

-- Force PostgREST to pick up the new columns immediately.
NOTIFY pgrst, 'reload schema';
