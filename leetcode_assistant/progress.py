"""Local solve log + streak calculation (~/.leetcode-assistant/progress.json)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from .config import PROGRESS_PATH, ensure_home


def _load() -> dict[str, Any]:
    if not PROGRESS_PATH.exists():
        return {"solved": []}
    try:
        data = json.loads(PROGRESS_PATH.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {"solved": []}
    data.setdefault("solved", [])
    return data


def _save(data: dict[str, Any]) -> None:
    ensure_home()
    PROGRESS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def record_solve(number: int, slug: str, title: str, difficulty: str,
                 topic: str | None = None, optimality: str | None = None,
                 url: str | None = None, seconds: int | None = None) -> dict[str, Any]:
    data = _load()
    today = date.today().isoformat()
    entry = {
        "date": today,
        "number": number,
        "slug": slug,
        "title": title,
        "difficulty": difficulty,
        "topic": topic or "",
        "optimality": optimality or "unknown",
        "url": url or f"https://leetcode.com/problems/{slug}/",
    }
    if seconds is not None and seconds > 0:
        entry["seconds"] = int(seconds)
    # Update in place if this problem was already logged (keep latest verdict).
    for i, existing in enumerate(data["solved"]):
        if existing.get("slug") == slug and existing.get("date") == today:
            data["solved"][i] = entry
            _save(data)
            return data
    data["solved"].append(entry)
    _save(data)
    return data


def solved_slugs() -> set[str]:
    """Set of title-slugs the user has solved (used for per-topic progress)."""
    return {e["slug"] for e in _load()["solved"] if e.get("slug")}


def _solved_dates() -> set[date]:
    dates: set[date] = set()
    for entry in _load()["solved"]:
        try:
            dates.add(datetime.strptime(entry["date"], "%Y-%m-%d").date())
        except (KeyError, ValueError):
            continue
    return dates


def current_streak() -> int:
    """Consecutive days (ending today or yesterday) with at least one solve."""
    dates = _solved_dates()
    if not dates:
        return 0
    today = date.today()
    if today in dates:
        cursor = today
    elif (today - timedelta(days=1)) in dates:
        cursor = today - timedelta(days=1)
    else:
        return 0
    streak = 0
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def longest_streak() -> int:
    """The longest run of consecutive solved days, ever."""
    dates = sorted(_solved_dates())
    if not dates:
        return 0
    best = run = 1
    for prev, cur in zip(dates, dates[1:]):
        run = run + 1 if (cur - prev).days == 1 else 1
        best = max(best, run)
    return best


def solves_by_date() -> dict[str, int]:
    """date-string -> number of solves that day (for a heatmap)."""
    counts: dict[str, int] = {}
    for e in _load()["solved"]:
        d = e.get("date")
        if d:
            counts[d] = counts.get(d, 0) + 1
    return counts


def _latest_per_slug() -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for e in _load()["solved"]:
        slug, d = e.get("slug"), e.get("date")
        if not slug or not d:
            continue
        if slug not in latest or d > latest[slug].get("date", ""):
            latest[slug] = e
    return latest


def due_for_review(days: int = 7) -> list[dict[str, Any]]:
    """Problems whose most-recent solve is at least `days` days old -- the
    spaced-repetition queue. Most overdue first."""
    today = date.today()
    due = []
    for entry in _latest_per_slug().values():
        try:
            solved_on = datetime.strptime(entry["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        age = (today - solved_on).days
        if age >= days:
            due.append({**entry, "days_ago": age})
    due.sort(key=lambda x: x["days_ago"], reverse=True)
    return due


def stats() -> dict[str, Any]:
    data = _load()
    solved = data["solved"]
    by_diff: dict[str, int] = {}
    optimal = 0
    for e in solved:
        by_diff[e.get("difficulty", "unknown")] = by_diff.get(
            e.get("difficulty", "unknown"), 0
        ) + 1
        if e.get("optimality") == "optimal":
            optimal += 1
    return {
        "total": len(solved),
        "by_difficulty": by_diff,
        "streak": current_streak(),
        "longest_streak": longest_streak(),
        "optimal": optimal,
        "last": solved[-1] if solved else None,
    }
