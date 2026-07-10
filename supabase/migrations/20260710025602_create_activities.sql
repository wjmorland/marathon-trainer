-- Synced Strava activity data, one row per (plan, session), replacing
-- data/activities/*.yaml.
create table activities (
  plan_id text not null,
  session_id text not null,
  data jsonb not null,
  updated_at timestamptz not null default now(),
  primary key (plan_id, session_id)
);
