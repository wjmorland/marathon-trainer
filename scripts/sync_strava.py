#!/usr/bin/env python3
"""Pull Strava activities and match them to plan sessions by date.

Auth: reads STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN from
the environment (see README for how to obtain these) and exchanges the
refresh token for a short-lived access token on every run.

For each Run/Ride/VirtualRide activity in range, fetches full activity
detail (GET /activities/{id}) to get splits, laps, heart rate, cadence,
elevation, and calories -- not just the summary fields from the list
endpoint. This costs one extra API request per activity (Strava allows
100 req/15min, 1000/day, which is plenty for a daily sync of a handful of
activities).

Writes/updates rows in the Supabase `activities` table, keyed by
(plan_id, session_id), so the site builder can merge planned vs. actual.
Reads SUPABASE_URL and SUPABASE_SECRET_KEY from the environment. Designed
to be safe to re-run: existing manual overrides (marked `source: manual`)
are never overwritten by Strava data.

Usage:
    .venv/bin/python3 scripts/sync_strava.py <plan_id>
"""
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"
STRAVA_ACTIVITY_DETAIL_URL = "https://www.strava.com/api/v3/activities/{id}"


def supabase_headers() -> dict:
    key = os.environ["SUPABASE_SECRET_KEY"]
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def fetch_existing_activities(plan_id: str) -> dict:
    base_url = os.environ["SUPABASE_URL"]
    resp = requests.get(
        f"{base_url}/rest/v1/activities",
        headers=supabase_headers(),
        params={"plan_id": f"eq.{plan_id}", "select": "session_id,data"},
        timeout=30,
    )
    resp.raise_for_status()
    return {row["session_id"]: row["data"] for row in resp.json()}


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

METERS_PER_MILE = 1609.34

RIDE_TYPES = {"Ride", "VirtualRide", "EBikeRide", "GravelRide", "MountainBikeRide"}
SUPPORTED_TYPES = {"Run", "VirtualRun"} | RIDE_TYPES


def get_access_token() -> str:
    client_id = os.environ["STRAVA_CLIENT_ID"]
    client_secret = os.environ["STRAVA_CLIENT_SECRET"]
    refresh_token = os.environ["STRAVA_REFRESH_TOKEN"]
    resp = requests.post(
        STRAVA_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_activities(access_token: str, after_epoch: int) -> list[dict]:
    activities = []
    page = 1
    while True:
        resp = requests.get(
            STRAVA_ACTIVITIES_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"after": after_epoch, "per_page": 100, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        activities.extend(batch)
        page += 1
    return activities


def fetch_activity_detail(access_token: str, activity_id: int) -> dict:
    resp = requests.get(
        STRAVA_ACTIVITY_DETAIL_URL.format(id=activity_id),
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def format_pace(distance_m: float, moving_time_s: int) -> str | None:
    if not distance_m:
        return None
    miles = distance_m / METERS_PER_MILE
    if miles <= 0:
        return None
    sec_per_mile = moving_time_s / miles
    m, s = divmod(int(sec_per_mile), 60)
    return f"{m}:{s:02d}/mi"


def format_speed(distance_m: float, moving_time_s: int) -> str | None:
    if not distance_m or not moving_time_s:
        return None
    mph = (distance_m / METERS_PER_MILE) / (moving_time_s / 3600)
    return f"{mph:.1f} mph"


def build_activity_record(detail: dict) -> dict:
    distance_m = detail.get("distance", 0)
    moving_time_s = detail.get("moving_time", 0)
    activity_type = detail.get("type", "Run")
    is_ride = activity_type in RIDE_TYPES

    splits = []
    for split in detail.get("splits_standard") or []:
        splits.append(
            {
                "mile": split.get("split"),
                "distance_mi": round(split.get("distance", 0) / METERS_PER_MILE, 2),
                "moving_time_s": split.get("moving_time"),
                "pace": format_pace(split.get("distance", 0), split.get("moving_time", 0)),
                "elevation_diff_ft": round(split.get("elevation_difference", 0) * 3.28084, 1)
                if split.get("elevation_difference") is not None
                else None,
                "avg_heartrate": split.get("average_heartrate"),
            }
        )

    laps = []
    for lap in detail.get("laps") or []:
        laps.append(
            {
                "lap": lap.get("lap_index"),
                "name": lap.get("name"),
                "distance_mi": round(lap.get("distance", 0) / METERS_PER_MILE, 2),
                "moving_time_s": lap.get("moving_time"),
                "pace": format_pace(lap.get("distance", 0), lap.get("moving_time", 0)),
                "avg_heartrate": lap.get("average_heartrate"),
                "avg_cadence": lap.get("average_cadence"),
            }
        )

    return {
        "id": detail["id"],
        "name": detail.get("name"),
        "type": activity_type,
        "is_ride": is_ride,
        "distance_mi": round(distance_m / METERS_PER_MILE, 2),
        "moving_time_s": moving_time_s,
        "elapsed_time_s": detail.get("elapsed_time"),
        "avg_pace": None if is_ride else format_pace(distance_m, moving_time_s),
        "avg_speed_mph": format_speed(distance_m, moving_time_s) if is_ride else None,
        "elevation_gain_ft": round(detail.get("total_elevation_gain", 0) * 3.28084, 1),
        "avg_heartrate": detail.get("average_heartrate"),
        "max_heartrate": detail.get("max_heartrate"),
        "avg_cadence": detail.get("average_cadence"),
        "calories": detail.get("calories"),
        "perceived_exertion": detail.get("perceived_exertion"),
        "strava_url": f"https://www.strava.com/activities/{detail['id']}",
        "splits": splits,
        "laps": laps,
    }


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    plan_id = sys.argv[1]

    plan_path = Path(f"data/plans/{plan_id}.yaml")
    plan = yaml.safe_load(plan_path.read_text())

    sessions_by_date = defaultdict(list)
    for week in plan["weeks"]:
        for session in week["sessions"]:
            sessions_by_date[session["date"]].append(session["id"])

    plan_start = min(sessions_by_date)
    after_epoch = int(datetime.fromisoformat(plan_start).timestamp())

    access_token = get_access_token()
    summaries = [a for a in fetch_activities(access_token, after_epoch) if a.get("type") in SUPPORTED_TYPES]

    existing = fetch_existing_activities(plan_id)

    activities_by_date = defaultdict(list)
    for a in summaries:
        local_date = a["start_date_local"][:10]
        activities_by_date[local_date].append(a)

    changed_days = 0
    for local_date, day_summaries in activities_by_date.items():
        session_ids = sessions_by_date.get(local_date, [])
        if not session_ids:
            continue
        # If a day has multiple sessions logged (rare), attach all Strava
        # activities for that date to the first session; otherwise 1:1.
        session_id = session_ids[0]
        if existing.get(session_id, {}).get("source") == "manual":
            continue

        details = [fetch_activity_detail(access_token, a["id"]) for a in day_summaries]
        records = [build_activity_record(d) for d in details]

        total_distance_mi = round(sum(r["distance_mi"] for r in records), 2)
        total_moving_s = sum(r["moving_time_s"] for r in records)
        has_run = any(not r["is_ride"] for r in records)
        has_ride = any(r["is_ride"] for r in records)

        run_distance_m = sum(r["distance_mi"] for r in records if not r["is_ride"]) * METERS_PER_MILE
        run_moving_s = sum(r["moving_time_s"] for r in records if not r["is_ride"])
        ride_distance_m = sum(r["distance_mi"] for r in records if r["is_ride"]) * METERS_PER_MILE
        ride_moving_s = sum(r["moving_time_s"] for r in records if r["is_ride"])

        candidate = {
            "source": "strava",
            "distance_mi": total_distance_mi,
            "moving_time_s": total_moving_s,
            "has_run": has_run,
            "has_ride": has_ride,
            # Pace/speed only make sense when the day is one activity type;
            # left null for mixed run+ride days (see per-activity records).
            "avg_pace": format_pace(run_distance_m, run_moving_s) if has_run and not has_ride else None,
            "avg_speed_mph": format_speed(ride_distance_m, ride_moving_s) if has_ride and not has_run else None,
            "activities": records,
        }

        existing_entry = existing.get(session_id, {})
        existing_without_timestamp = {k: v for k, v in existing_entry.items() if k != "synced_at"}
        if candidate == existing_without_timestamp:
            continue

        candidate["synced_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        upsert_activity(plan_id, session_id, candidate)
        changed_days += 1

    print(f"Synced {changed_days} changed activity day(s) -> Supabase ({plan_id})")


if __name__ == "__main__":
    main()
