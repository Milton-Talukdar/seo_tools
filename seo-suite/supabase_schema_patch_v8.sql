-- Patch v8: Content Engine — inventory synced from content repos.
-- Run once in the Supabase SQL editor.

-- Raw inventory of every content item pulled from the Astro repo(s).
CREATE TABLE IF NOT EXISTS content_inventory (
  url TEXT NOT NULL,
  property TEXT NOT NULL DEFAULT 'vantagecircle',
  lang TEXT NOT NULL DEFAULT 'en',
  content_type TEXT NOT NULL,
  slug TEXT NOT NULL,
  title TEXT,
  meta_title TEXT,
  meta_description TEXT,
  excerpt TEXT,
  authors TEXT,
  tags TEXT,
  featured BOOLEAN DEFAULT false,
  published_date DATE,
  updated_date DATE,
  word_count INTEGER,
  internal_links INTEGER,
  external_links INTEGER,
  status TEXT NOT NULL DEFAULT 'published',
  repo_path TEXT,
  content_hash TEXT,
  synced_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (url, lang)
);

CREATE INDEX IF NOT EXISTS idx_content_inventory_property ON content_inventory(property, content_type);
CREATE INDEX IF NOT EXISTS idx_content_inventory_type ON content_inventory(content_type, lang);
CREATE INDEX IF NOT EXISTS idx_content_inventory_author ON content_inventory(authors);
CREATE INDEX IF NOT EXISTS idx_content_inventory_date ON content_inventory(updated_date DESC);
CREATE INDEX IF NOT EXISTS idx_content_inventory_status ON content_inventory(status);

-- Editorial pipeline / content calendar.
CREATE TABLE IF NOT EXISTS content_pipeline (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  url TEXT,
  lang TEXT DEFAULT 'en',
  title TEXT NOT NULL,
  property TEXT NOT NULL DEFAULT 'vantagecircle',
  content_type TEXT,
  stage TEXT NOT NULL CHECK (stage IN ('idea','brief','draft','review','scheduled','published','refresh','prune')),
  owner TEXT,
  due_date DATE,
  published_date DATE,
  target_keyword TEXT,
  cluster TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_content_pipeline_stage ON content_pipeline(stage, due_date);
CREATE INDEX IF NOT EXISTS idx_content_pipeline_owner ON content_pipeline(owner);

-- Topic clusters for content grouping.
CREATE TABLE IF NOT EXISTS content_clusters (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  property TEXT NOT NULL DEFAULT 'vantagecircle',
  cluster TEXT NOT NULL,
  pillar_url TEXT,
  target_keywords TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_content_clusters_property ON content_clusters(property, cluster);

NOTIFY pgrst, 'reload schema';
