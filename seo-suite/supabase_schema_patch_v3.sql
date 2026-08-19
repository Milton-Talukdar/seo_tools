-- Patch v3: LLM visibility split into per-property projects
-- (Vantage Circle / Vantage Fit). Run in the Supabase SQL editor.
-- Existing rows become 'vantagecircle' via the column default.
-- The worker filters llm_snapshots / volumes / discovered / silent by
-- property, so all four tables need the column and a PK that includes it.

alter table llm_snapshots add column if not exists property text not null default 'vantagecircle';
alter table llm_snapshots drop constraint if exists llm_snapshots_pkey;
alter table llm_snapshots add primary key (day, platform, prompt, property);

alter table volumes add column if not exists property text not null default 'vantagecircle';
alter table volumes drop constraint if exists volumes_pkey;
alter table volumes add primary key (day, keyword, property);

alter table discovered add column if not exists property text not null default 'vantagecircle';
alter table discovered drop constraint if exists discovered_pkey;
alter table discovered add primary key (query, property);

alter table silent add column if not exists property text not null default 'vantagecircle';
alter table silent drop constraint if exists silent_pkey;
alter table silent add primary key (day, query, platform, property);

create index if not exists idx_llm_snapshots_property_day
  on llm_snapshots(property, day desc);
