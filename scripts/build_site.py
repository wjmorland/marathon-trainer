#!/usr/bin/env python3
"""Render data/plans/*.yaml + data/activities/*.yaml into static HTML in docs/.

Discovers every plan under data/plans/ automatically, so dropping in a new
plan YAML file (hand-written or produced by an importer) is enough to add it
to the site with no code changes.

Usage:
    .venv/bin/python3 scripts/build_site.py
"""
import hashlib
import shutil
from datetime import date
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
PLANS_DIR = ROOT / "data" / "plans"
ACTIVITIES_DIR = ROOT / "data" / "activities"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
OUT_DIR = ROOT / "docs"

env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=True)

# Cache-busts static asset URLs so browsers (and the GitHub Pages CDN's
# 10-minute cache) pick up changes immediately after a deploy instead of
# serving a stale style.css/favicon.ico under the same URL.
ASSET_VERSION = hashlib.sha1((STATIC_DIR / "css" / "style.css").read_bytes()).hexdigest()[:10]
env.globals["asset_version"] = ASSET_VERSION


def load_plans():
    plans = []
    for path in sorted(PLANS_DIR.glob("*.yaml")):
        plan = yaml.safe_load(path.read_text())
        activities_path = ACTIVITIES_DIR / f"{plan['id']}.yaml"
        activities = {}
        if activities_path.exists():
            activities = yaml.safe_load(activities_path.read_text()) or {}

        today = date.today().isoformat()
        completed = 0
        total = 0
        for week in plan["weeks"]:
            actual_mi = 0
            for session in week["sessions"]:
                actual = activities.get(session["id"])
                session["actual"] = actual
                session["is_past"] = session["date"] < today
                session["is_today"] = session["date"] == today
                if session["type"] != "rest":
                    total += 1
                    if actual:
                        completed += 1
                if actual:
                    # Only count run mileage toward the weekly running total;
                    # ride distance is shown per-session but excluded here so
                    # it doesn't inflate progress against the run-mileage goal.
                    run_mi = sum(
                        a["distance_mi"] for a in actual.get("activities", []) if not a.get("is_ride")
                    )
                    actual_mi += run_mi
            week["actual_mi"] = round(actual_mi, 1) if actual_mi else None
        plan["progress"] = {
            "completed": completed,
            "total": total,
            "pct": round(100 * completed / total) if total else 0,
        }
        plans.append(plan)
    return plans


def build():
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)
    shutil.copytree(STATIC_DIR, OUT_DIR / "static")
    (OUT_DIR / ".nojekyll").touch()

    plans = load_plans()

    index_tpl = env.get_template("index.html")
    (OUT_DIR / "index.html").write_text(index_tpl.render(plans=plans, root=""))

    plan_tpl = env.get_template("plan.html")
    session_tpl = env.get_template("session.html")

    for plan in plans:
        plan_dir = OUT_DIR / "plans" / plan["id"]
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "index.html").write_text(plan_tpl.render(plan=plan, root="../../"))

        all_sessions = [s for week in plan["weeks"] for s in week["sessions"]]
        for i, session in enumerate(all_sessions):
            prev_s = all_sessions[i - 1] if i > 0 else None
            next_s = all_sessions[i + 1] if i < len(all_sessions) - 1 else None
            session_dir = plan_dir / "sessions" / session["id"]
            session_dir.mkdir(parents=True, exist_ok=True)
            (session_dir / "index.html").write_text(
                session_tpl.render(plan=plan, session=session, prev_s=prev_s, next_s=next_s, root="../../../../")
            )

    print(f"Built {len(plans)} plan(s) -> {OUT_DIR}")


if __name__ == "__main__":
    build()
