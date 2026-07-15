-- Enable Row-Level Security on both tables. All access to this database is
-- server-side (build_site.py, sync_strava.py, import_xlsx_plan.py) using the
-- Supabase secret key, which bypasses RLS. The public site is fully static and
-- never queries Supabase from the browser, so no anon/public policies are
-- needed. Enabling RLS with no policies denies all access through the public
-- API, resolving the `rls_disabled_in_public` / `sensitive_columns_exposed`
-- security warnings.
alter table plans enable row level security;
alter table activities enable row level security;
