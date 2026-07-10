# Will's Marathon Training

A static site that renders a marathon training plan session-by-session, with
actual workouts pulled in automatically from Strava.

## How it fits together

- `data/plans/*.yaml` — one file per training plan (generic schema: weeks of
  sessions with date, type, title, planned distance). Drop in a new plan by
  adding a new YAML file here; the site picks it up automatically.
- Actual workout data per plan, keyed by session id, lives in a Supabase
  Postgres table (`activities`, see `supabase/migrations/`) rather than in
  git. Populated by `scripts/sync_strava.py`. A session with `source: manual`
  is never overwritten by the sync (use this to log a run by hand, or to log
  data from a source other than Strava).
- `scripts/import_xlsx_plan.py` — one-time importer for spreadsheet-based
  training log exports. Reusable if you regenerate the xlsx.
- `scripts/sync_strava.py` — pulls recent runs from the Strava API, matches
  them to plan sessions by date, and upserts them into Supabase.
- `scripts/build_site.py` — renders `templates/*.html` (Jinja2), merged with
  activity data fetched from Supabase, into static HTML in `docs/`, which
  GitHub Pages serves.
- `.github/workflows/sync-and-deploy.yml` — runs daily, syncs Strava into
  Supabase, rebuilds the site, and deploys to Pages. No longer commits
  anything back to the repo.

## Local setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Import a plan from a spreadsheet:

```bash
.venv/bin/python3 scripts/import_xlsx_plan.py "path/to/plan.xlsx" my-plan-id
```

Build the site locally (needs `SUPABASE_URL` / `SUPABASE_SECRET_KEY` exported,
see below):

```bash
.venv/bin/python3 scripts/build_site.py
cd docs && python3 -m http.server 8000
```

## Setting up Strava sync

1. Create a Strava API application at https://www.strava.com/settings/api.
   Note the **Client ID** and **Client Secret**, and set the **Authorization
   Callback Domain** to `localhost`.
2. Authorize your account and get a refresh token with the `activity:read_all`
   scope by running:
   ```bash
   .venv/bin/python3 scripts/get_strava_refresh_token.py CLIENT_ID CLIENT_SECRET
   ```
   This opens a browser to Strava's authorization page and runs a local
   server to catch the redirect automatically, then prints the
   `refresh_token` — this is what the sync script needs (access tokens
   expire; the refresh token doesn't, unless revoked).
3. In the GitHub repo settings, add these **Actions secrets**:
   - `STRAVA_CLIENT_ID`
   - `STRAVA_CLIENT_SECRET`
   - `STRAVA_REFRESH_TOKEN`
4. To sync locally, export the same three env vars plus `SUPABASE_URL` /
   `SUPABASE_SECRET_KEY` (see below) and run:
   ```bash
   .venv/bin/python3 scripts/sync_strava.py my-plan-id
   ```

## Setting up Supabase

Activity data (the output of `sync_strava.py`) is stored in Supabase
Postgres instead of git, so the daily sync doesn't need to push commits.

1. Create a free project at https://supabase.com (no credit card required).
2. Install the [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started)
   (`brew install supabase/tap/supabase`), then link this repo to your
   project and apply the schema in `supabase/migrations/`:
   ```bash
   supabase login
   supabase link --project-ref <project-ref>
   supabase db push
   ```
   The project ref is the subdomain in your project URL
   (`https://<project-ref>.supabase.co`). `link` and `db push` will prompt
   for your database password (Project Settings → Database). Re-run
   `supabase db push` any time a new file is added to
   `supabase/migrations/` — it tracks what's already applied (in the
   `supabase_migrations.schema_migrations` table) and skips it.
3. In Project Settings → API Keys, copy the **Project URL** and the
   **secret key** (`sb_secret_...`).
4. Add these as **Actions secrets** in the GitHub repo settings, alongside
   the Strava ones:
   - `SUPABASE_URL`
   - `SUPABASE_SECRET_KEY`
5. To run `sync_strava.py` or `build_site.py` locally, export the same two
   env vars.

## Enabling GitHub Pages

In the repo's Settings → Pages, set **Source** to "GitHub Actions". The
`sync-and-deploy.yml` workflow will build and deploy `docs/` automatically on
every push to `main`, on a daily schedule, and can also be triggered manually
from the Actions tab (`workflow_dispatch`).

## Adding a new plan

- If it's another xlsx in the same row-per-day layout: run the importer with
  a new plan id.
- Otherwise, hand-write a YAML file under `data/plans/` following the same
  schema (`id`, `name`, `goal_time`, `goal_pace`, `race_date`, `weeks: [...]`
  each with `sessions: [...]`). No code changes needed — the build script and
  homepage discover plans automatically.

## Adding a new data source

`sync_strava.py` is one example of a "data source" script: it reads plan
session dates and upserts rows into the Supabase `activities` table with a
`source` field. Any other source (Garmin, Apple Health export, manual entry)
can follow the same pattern — write a script that populates the same
activities schema, and the site builder will render it without changes.
