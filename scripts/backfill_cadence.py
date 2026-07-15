#!/usr/bin/env python3
"""One-off backfill: double stored running cadence to steps-per-minute.

Strava's API reports running cadence per leg (~70-100); its UI doubles it to
steps per minute for both feet (~140-200). sync_strava.py now doubles running
cadence at sync time, but the sync's cheap fingerprint pre-check (distance /
moving_time only) means unchanged days never get re-fetched -- so previously
synced activities keep their halved values indefinitely. This script rewrites
them in place.

Cycling cadence is pedal RPM and is left untouched (records/laps where
is_ride is true).

Idempotent: only values below CADENCE_THRESHOLD are doubled, so re-running
never doubles an already-corrected value. Running cadence is cleanly bimodal
(single-leg ~85 vs. both-feet ~170), so the threshold reliably tells them
apart.

Reads SUPABASE_URL and SUPABASE_SECRET_KEY from the environment (same as
sync_strava.py).

Usage:
    .venv/bin/python3 scripts/backfill_cadence.py [--dry-run]
"""
import os
import sys

import requests

# Above any plausible single-leg cadence, below any plausible both-feet value.
CADENCE_THRESHOLD = 120


def supabase_headers() -> dict:
    key = os.environ["SUPABASE_SECRET_KEY"]
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def fetch_all_activities() -> list[dict]:
    base_url = os.environ["SUPABASE_URL"]
    resp = requests.get(
        f"{base_url}/rest/v1/activities",
        headers=supabase_headers(),
        params={"select": "plan_id,session_id,data"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def upsert_activity(plan_id: str, session_id: str, data: dict) -> None:
    base_url = os.environ["SUPABASE_URL"]
    resp = requests.post(
        f"{base_url}/rest/v1/activities",
        headers={**supabase_headers(), "Prefer": "resolution=merge-duplicates"},
        params={"on_conflict": "plan_id,session_id"},
        json=[{"plan_id": plan_id, "session_id": session_id, "data": data}],
        timeout=30,
    )
    resp.raise_for_status()


def needs_double(cadence) -> bool:
    return cadence is not None and cadence < CADENCE_THRESHOLD


def fix_record(record: dict) -> int:
    """Double running cadence on a single activity record and its laps.
    Returns the number of values changed."""
    if record.get("is_ride"):
        return 0

    changed = 0
    if needs_double(record.get("avg_cadence")):
        record["avg_cadence"] *= 2
        changed += 1
    for lap in record.get("laps") or []:
        if needs_double(lap.get("avg_cadence")):
            lap["avg_cadence"] *= 2
            changed += 1
    return changed


def main() -> None:
    dry_run = "--dry-run" in sys.argv[1:]

    rows = fetch_all_activities()
    days_changed = 0
    values_changed = 0

    for row in rows:
        data = row["data"]
        if data.get("source") == "manual":
            continue

        day_changed = sum(fix_record(r) for r in data.get("activities") or [])
        if not day_changed:
            continue

        days_changed += 1
        values_changed += day_changed
        print(
            f"{'[dry-run] ' if dry_run else ''}"
            f"plan={row['plan_id']} session={row['session_id']}: "
            f"{day_changed} cadence value(s) doubled"
        )
        if not dry_run:
            upsert_activity(row["plan_id"], row["session_id"], data)

    print(
        f"\n{'Would update' if dry_run else 'Updated'} {days_changed} day(s), "
        f"{values_changed} cadence value(s)."
    )


if __name__ == "__main__":
    main()
