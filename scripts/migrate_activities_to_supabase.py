#!/usr/bin/env python3
"""One-time migration: load data/activities/*.yaml into the Supabase
`activities` table (see supabase/migrations/), then those files can be
deleted from the repo.

Reads SUPABASE_URL and SUPABASE_SECRET_KEY from the environment.

Usage:
    .venv/bin/python3 scripts/migrate_activities_to_supabase.py
"""
import os
from pathlib import Path

import requests
import yaml

ACTIVITIES_DIR = Path(__file__).resolve().parent.parent / "data" / "activities"


def main():
    base_url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SECRET_KEY"]
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }

    for path in sorted(ACTIVITIES_DIR.glob("*.yaml")):
        plan_id = path.stem
        activities = yaml.safe_load(path.read_text()) or {}
        rows = [{"plan_id": plan_id, "session_id": sid, "data": data} for sid, data in activities.items()]
        if not rows:
            continue
        resp = requests.post(
            f"{base_url}/rest/v1/activities",
            headers=headers,
            params={"on_conflict": "plan_id,session_id"},
            json=rows,
            timeout=30,
        )
        resp.raise_for_status()
        print(f"Migrated {len(rows)} session(s) from {path}")


if __name__ == "__main__":
    main()
