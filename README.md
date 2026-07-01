# Will's Marathon Training

A static site that renders a marathon training plan session-by-session, with
actual workouts pulled in automatically from Strava.

## How it fits together

- `data/plans/*.yaml` — one file per training plan (generic schema: weeks of
  sessions with date, type, title, planned distance). Drop in a new plan by
  adding a new YAML file here; the site picks it up automatically.
- `data/activities/*.yaml` — actual workout data per plan, keyed by session
  id. Populated by `scripts/sync_strava.py`. A session with `source: manual`
  is never overwritten by the sync (use this to log a run by hand, or to log
  data from a source other than Strava).
- `scripts/import_xlsx_plan.py` — one-time importer for spreadsheet-based
  training log exports. Reusable if you regenerate the xlsx.
- `scripts/sync_strava.py` — pulls recent runs from the Strava API and
  matches them to plan sessions by date.
- `scripts/build_site.py` — renders `templates/*.html` (Jinja2) into static
  HTML in `docs/`, which GitHub Pages serves.
- `.github/workflows/sync-and-deploy.yml` — runs daily, syncs Strava,
  rebuilds the site, commits updated activity data, and deploys to Pages.

## Local setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Import a plan from a spreadsheet:

```bash
.venv/bin/python3 scripts/import_xlsx_plan.py "path/to/plan.xlsx" my-plan-id
```

Build the site locally:

```bash
.venv/bin/python3 scripts/build_site.py
cd docs && python3 -m http.server 8000
```

## Setting up Strava sync

1. Create a Strava API application at https://www.strava.com/settings/api.
   Note the **Client ID** and **Client Secret**.
2. Authorize your account and get a refresh token with the `activity:read_all`
   scope. Easiest path:
   - Visit (replace `CLIENT_ID`):
     `https://www.strava.com/oauth/authorize?client_id=CLIENT_ID&response_type=code&redirect_uri=http://localhost&approval_prompt=force&scope=activity:read_all`
   - After authorizing, copy the `code` param from the redirect URL.
   - Exchange it for tokens:
     ```bash
     curl -X POST https://www.strava.com/oauth/token \
       -d client_id=CLIENT_ID \
       -d client_secret=CLIENT_SECRET \
       -d code=AUTH_CODE \
       -d grant_type=authorization_code
     ```
   - The response includes a `refresh_token` — this is what the sync script
     needs (access tokens expire; the refresh token doesn't, unless revoked).
3. In the GitHub repo settings, add these **Actions secrets**:
   - `STRAVA_CLIENT_ID`
   - `STRAVA_CLIENT_SECRET`
   - `STRAVA_REFRESH_TOKEN`
4. To sync locally, export the same three env vars and run:
   ```bash
   .venv/bin/python3 scripts/sync_strava.py my-plan-id
   ```

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
session dates and writes `data/activities/<plan_id>.yaml` entries with a
`source` field. Any other source (Garmin, Apple Health export, manual entry)
can follow the same pattern — write a script that populates the same
activities schema, and the site builder will render it without changes.
