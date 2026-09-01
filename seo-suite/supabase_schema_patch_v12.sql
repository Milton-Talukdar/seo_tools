-- Patch v12: Site Health / Site Audit module tables.
-- Run once in the Supabase SQL editor.

CREATE TABLE IF NOT EXISTS site_audit_runs (
  day DATE NOT NULL,
  property TEXT NOT NULL DEFAULT 'vantagecircle',
  pages_crawled INTEGER,
  pages_failed INTEGER,
  issues_found INTEGER,
  psi_calls INTEGER,
  run_duration_seconds INTEGER,
  PRIMARY KEY (day, property)
);

CREATE TABLE IF NOT EXISTS site_audit_pages (
  day DATE NOT NULL,
  property TEXT NOT NULL DEFAULT 'vantagecircle',
  url TEXT NOT NULL,
  status_code INTEGER,
  final_url TEXT,
  title TEXT,
  meta_description TEXT,
  h1 TEXT,
  canonical TEXT,
  canonical_ok INTEGER,
  word_count INTEGER,
  internal_links INTEGER,
  external_links INTEGER,
  has_viewport INTEGER,
  redirect_count INTEGER,
  lcp REAL,
  inp REAL,
  cls REAL,
  performance_score INTEGER,
  seo_score INTEGER,
  psi_status TEXT,
  fetch_error TEXT,
  PRIMARY KEY (day, property, url)
);

CREATE TABLE IF NOT EXISTS site_audit_issues (
  day DATE NOT NULL,
  property TEXT NOT NULL DEFAULT 'vantagecircle',
  url TEXT NOT NULL,
  issue_type TEXT NOT NULL,
  severity TEXT CHECK (severity IN ('critical', 'warning', 'info')),
  details TEXT,
  PRIMARY KEY (day, property, url, issue_type)
);

CREATE INDEX IF NOT EXISTS idx_site_audit_issues_day ON site_audit_issues(day, property);
CREATE INDEX IF NOT EXISTS idx_site_audit_issues_severity ON site_audit_issues(day, severity);
CREATE INDEX IF NOT EXISTS idx_site_audit_pages_day ON site_audit_pages(day, property);

NOTIFY pgrst, 'reload schema';
