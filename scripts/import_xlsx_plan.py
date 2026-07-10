#!/usr/bin/env python3
"""Importer: spreadsheet-based training log -> Supabase `plans` table.

Usage:
    .venv/bin/python3 scripts/import_xlsx_plan.py <input.xlsx> <plan_id>

Reads SUPABASE_URL and SUPABASE_SECRET_KEY from the environment. The plan
schema produced here is generic (id, name, goal_time, goal_pace, race_date,
weeks of sessions) so any future plan of a similar row-per-day layout can be
imported by running this against a new xlsx.
"""
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import openpyxl
import requests

SESSION_TYPE_KEYWORDS = [
    ("race", "race"),
    ("tempo", "tempo"),
    ("strength", "strength"),
    ("speed", "speed"),
    ("long", "long"),
    ("easy", "easy"),
    ("rest", "rest"),
    ("cross", "cross-train"),
]


def classify(short_title: str) -> str:
    t = short_title.lower()
    for keyword, label in SESSION_TYPE_KEYWORDS:
        if keyword in t:
            return label
    return "other"


def parse_distance(text: str) -> float | None:
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:mi|mile)", text, re.IGNORECASE)
    return float(m.group(1)) if m else None


def upsert_plan(plan: dict) -> None:
    base_url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SECRET_KEY"]
    resp = requests.post(
        f"{base_url}/rest/v1/plans",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
        params={"on_conflict": "id"},
        json=[plan],
        timeout=30,
    )
    resp.raise_for_status()


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    xlsx_path = Path(sys.argv[1])
    plan_id = sys.argv[2]

    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    title_row = rows[0]
    title_text = str(title_row[0])
    goal_time_m = re.search(r"Goal:\s*([\d:]+)", title_text)
    race_day_m = re.search(r"Race Day:\s*\w+,\s*(.+)", title_text)

    goal_pace = rows[2][1]  # "8:47/mi (MP)"

    header_idx = 5  # 0-indexed row containing column headers ("Week", "Days\nOut", ...)
    data_rows = rows[header_idx + 1 :]

    # Race date: parsed from the title's race day text (e.g. "Race Day: Sunday, October 11, 2026").
    race_date = None
    if race_day_m:
        try:
            race_date = datetime.strptime(race_day_m.group(1).strip(), "%B %d, %Y").date()
        except ValueError:
            race_date = None
    if race_date is None:
        raise SystemExit("Could not determine race date from sheet title")

    weeks = {}
    current_week_label = None
    current_week_number = 0

    for row in data_rows:
        week_label_cell, days_out, _date_str, day_abbr, plan_short, plan_detail = row[0:6]
        weekly_total_plan_mi = row[13]
        if days_out is None:
            continue
        if week_label_cell:
            current_week_label = str(week_label_cell)
            current_week_number += 1

        session_date = race_date - timedelta(days=int(days_out))
        plan_short = str(plan_short) if plan_short is not None else ""
        plan_detail = str(plan_detail) if plan_detail is not None else ""

        session = {
            "id": f"w{current_week_number}-{session_date.isoformat()}",
            "date": session_date.isoformat(),
            "day": day_abbr,
            "type": classify(plan_short),
            "title": plan_short,
            "detail": plan_detail if plan_detail != "—" else None,
            "planned_distance_mi": parse_distance(plan_detail) or parse_distance(plan_short),
        }

        week = weeks.setdefault(
            current_week_number,
            {"number": current_week_number, "label": current_week_label, "sessions": [], "goal_mi": None},
        )
        week["sessions"].append(session)
        if weekly_total_plan_mi is not None:
            week["goal_mi"] = float(weekly_total_plan_mi)

    plan = {
        "id": plan_id,
        "name": "Beginner Marathon Training Plan",
        "goal_time": goal_time_m.group(1) if goal_time_m else None,
        "goal_pace": goal_pace,
        "race_date": race_date.isoformat(),
        "source": {"type": "xlsx_import", "file": xlsx_path.name},
        "weeks": [weeks[k] for k in sorted(weeks)],
    }

    upsert_plan(plan)
    n_sessions = sum(len(w["sessions"]) for w in plan["weeks"])
    print(f"Upserted plan {plan_id!r} to Supabase ({len(plan['weeks'])} weeks, {n_sessions} sessions)")


if __name__ == "__main__":
    main()
