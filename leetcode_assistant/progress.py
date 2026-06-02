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
                 url: str | None = None) -> dict[str, Any]:
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


def stats() -> dict[str, Any]:
    data = _load()
    solved = data["solved"]
    by_diff: dict[str, int] = {}
    for e in solved:
        by_diff[e.get("difficulty", "unknown")] = by_diff.get(
            e.get("difficulty", "unknown"), 0
        ) + 1
    return {
        "total": len(solved),
        "by_difficulty": by_diff,
        "streak": current_streak(),
        "last": solved[-1] if solved else None,
    }
