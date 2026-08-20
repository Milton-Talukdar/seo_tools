-- Patch v4: agency workflow tables + discovered volume delta
-- Run once in the Supabase SQL editor.

-- Mutable team workflow state
CREATE TABLE IF NOT EXISTS annotations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  day date NOT NULL,
  label text NOT NULL,
  note text,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_annotations_day ON annotations(day desc);

CREATE TABLE IF NOT EXISTS freshness_status (
  url text PRIMARY KEY,
  status text NOT NULL CHECK (status IN ('todo','in_progress','done','ignored')),
  owner text,
  note text,
  updated_at timestamptz DEFAULT now()
);

-- Month-over-month volume change for AI discovered prompts
ALTER TABLE discovered ADD COLUMN IF NOT EXISTS prev_volume integer;
ALTER TABLE discovered ADD COLUMN IF NOT EXISTS volume_delta integer;
