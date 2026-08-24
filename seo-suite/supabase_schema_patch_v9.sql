-- Patch v9: Content Engine — page-level GSC performance for Content Performance view.
-- Run once in the Supabase SQL editor.

CREATE TABLE IF NOT EXISTS gsc_page_stats (
  property TEXT NOT NULL,
  day DATE NOT NULL,
  page TEXT NOT NULL,
  clicks INTEGER NOT NULL DEFAULT 0,
  impressions INTEGER NOT NULL DEFAULT 0,
  ctr REAL NOT NULL DEFAULT 0,
  position REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (property, day, page)
);

CREATE INDEX IF NOT EXISTS idx_gsc_page_stats_day ON gsc_page_stats(day DESC);
CREATE INDEX IF NOT EXISTS idx_gsc_page_stats_page ON gsc_page_stats(page);

NOTIFY pgrst, 'reload schema';
