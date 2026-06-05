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
        "url": url or f"https://leetcode.com/problems/{slug}/",
    }
    # Self-reported at submit time ("optimal" / "suboptimal"); omitted when the
    # user skips, so it simply shows as unmarked in the README.
    if optimality in ("optimal", "suboptimal"):
        entry["optimality"] = optimality
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


# --------------------------------------------------------------------------- #
# Spaced-repetition review schedule ("Refresh")
# --------------------------------------------------------------------------- #
DEFAULT_REVIEW_INTERVALS = [7, 30, 90, 365]   # days, per level
LEVEL_NAMES = ["Learning", "Familiar", "Confident", "Mastered"]
# rating -> how the level moves
_RATING_DELTA = {"aced": +1, "good": 0, "hard": "reset"}


def review_intervals() -> list[int]:
    from .config import load_config
    cfg = load_config() or {}
    iv = cfg.get("review_intervals")
    if isinstance(iv, list) and iv and all(isinstance(x, int) and x > 0 for x in iv):
        return iv
    return DEFAULT_REVIEW_INTERVALS


def level_name(level: int) -> str:
    return LEVEL_NAMES[min(level, len(LEVEL_NAMES) - 1)] if level < len(LEVEL_NAMES) \
        else f"L{level}"


def schedule_review(slug: str, meta: dict[str, Any],
                    rating: str | None = None) -> dict[str, Any]:
    """Create/update a problem's review schedule after a solve.

    rating: 'aced' (level up), 'good' (stay), 'hard' (reset to level 0), or
    None for a first solve (start at level 0) / casual re-solve (re-anchor at
    the current level).
    """
    data = _load()
    reviews = data.setdefault("reviews", {})
    iv = review_intervals()
    existing = reviews.get(slug)
    today = date.today()

    # Re-solving the same problem BEFORE its review is due (e.g. a brute-force
    # warm-up followed immediately by the optimal version) is just practice --
    # it must not advance the spaced-repetition clock. Leave the schedule as it
    # is and only bump the practice counter. The level can only move on a
    # genuine retest, i.e. once the problem is actually due.
    if existing and rating is None:
        try:
            due = datetime.strptime(existing["due"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            due = today  # malformed -> treat as due so it can be re-anchored
        if today < due:
            existing["reps"] = existing.get("reps", 0) + 1
            existing["last_practiced"] = today.isoformat()
            _save(data)
            return existing

    level = existing.get("level", 0) if existing else 0

    if rating == "aced":
        level = min(level + 1, len(iv) - 1)
    elif rating == "hard":
        level = 0
    # 'good' or None keep the current level (None on a first solve -> 0)

    days = iv[min(level, len(iv) - 1)]
    entry = {
        "level": level,
        "interval_days": days,
        "due": (today + timedelta(days=days)).isoformat(),
        "last_reviewed": today.isoformat(),
        "last_rating": rating or "",
        "reps": (existing.get("reps", 0) + 1) if existing else 1,
        "number": meta.get("number"),
        "title": meta.get("title", slug),
        "difficulty": meta.get("difficulty", ""),
        "topic": meta.get("topic", ""),
        "url": meta.get("url") or f"https://leetcode.com/problems/{slug}/",
    }
    reviews[slug] = entry
    _save(data)
    return entry


def all_reviews() -> dict[str, dict[str, Any]]:
    return _load().get("reviews", {})


def has_review(slug: str) -> bool:
    return slug in _load().get("reviews", {})


def is_review_due(slug: str, today: date | None = None) -> bool:
    """True only if this problem has a review whose due date has arrived. Used
    to decide whether a re-solve is a genuine spaced-repetition retest (rate
    confidence, advance the level) or just practice (leave the schedule alone)."""
    r = _load().get("reviews", {}).get(slug)
    if not r:
        return False
    today = today or date.today()
    try:
        due = datetime.strptime(r["due"], "%Y-%m-%d").date()
    except (KeyError, ValueError):
        return True  # malformed schedule -> treat as due so it gets fixed
    return due <= today


def due_reviews(today: date | None = None) -> list[dict[str, Any]]:
    """Reviews whose due date has arrived (most overdue first)."""
    today = today or date.today()
    out = []
    for slug, r in _load().get("reviews", {}).items():
        try:
            due = datetime.strptime(r["due"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        if due <= today:
            out.append({**r, "slug": slug, "days_overdue": (today - due).days})
    out.sort(key=lambda x: (-x["days_overdue"], x.get("number") or 0))
    return out


def upcoming_reviews(today: date | None = None) -> list[dict[str, Any]]:
    """Reviews not yet due, soonest first."""
    today = today or date.today()
    out = []
    for slug, r in _load().get("reviews", {}).items():
        try:
            due = datetime.strptime(r["due"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        if due > today:
            out.append({**r, "slug": slug, "days_until": (due - today).days})
    out.sort(key=lambda x: x["days_until"])
    return out


# --------------------------------------------------------------------------- #
# Topic tests (back-to-back gauntlet per topic)
# --------------------------------------------------------------------------- #
PRESET_RANK = {"blind75": 1, "neetcode150": 2, "neetcode250": 3, "all": 4}


def _now() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def passed_tests() -> dict[str, Any]:
    return _load().get("tests", {})


def test_in_progress() -> dict[str, Any]:
    return _load().get("test_progress", {})


def start_test(topic: str, preset: str) -> dict[str, Any]:
    """Begin (or restart at a new preset) a topic test session."""
    data = _load()
    tp = data.setdefault("test_progress", {})
    cur = tp.get(topic)
    if not cur or cur.get("preset") != preset:
        tp[topic] = {"preset": preset, "started_at": _now(), "outcomes": {}}
        _save(data)
    return tp[topic]


def test_outcomes(topic: str, preset: str) -> dict[str, str]:
    cur = _load().get("test_progress", {}).get(topic)
    if cur and cur.get("preset") == preset:
        return dict(cur.get("outcomes", {}))
    return {}


def record_test_outcome(topic: str, preset: str, slug: str, outcome: str,
                        topic_slugs: list[str]) -> dict[str, Any]:
    """Record one problem's outcome (clean/unsure/help) in a topic test. When
    every problem in the topic has an outcome, the topic is marked passed."""
    data = _load()
    tp = data.setdefault("test_progress", {})
    cur = tp.get(topic)
    if not cur or cur.get("preset") != preset:
        cur = {"preset": preset, "started_at": _now(), "outcomes": {}}
        tp[topic] = cur
    cur["outcomes"][slug] = outcome
    outcomes = cur["outcomes"]
    done = [s for s in topic_slugs if s in outcomes]
    if topic_slugs and len(done) >= len(topic_slugs):
        record = _finalize_test(data, topic, preset, outcomes, topic_slugs)
        tp.pop(topic, None)
        _save(data)
        return {"status": "passed", "record": record,
                "done": len(done), "total": len(topic_slugs)}
    _save(data)
    return {"status": "in_progress", "done": len(done),
            "total": len(topic_slugs),
            "remaining": [s for s in topic_slugs if s not in outcomes]}


def _finalize_test(data, topic, preset, outcomes, topic_slugs) -> dict[str, Any]:
    tests = data.setdefault("tests", {})
    clean = sum(1 for s in topic_slugs if outcomes.get(s) == "clean")
    unsure = sum(1 for s in topic_slugs if outcomes.get(s) == "unsure")
    helped = sum(1 for s in topic_slugs if outcomes.get(s) == "help")
    existing = tests.get(topic)
    # A pass at a higher question set outranks a lower one; never downgrade.
    if existing and PRESET_RANK.get(existing.get("preset"), 0) > PRESET_RANK.get(preset, 0):
        return existing
    rec = {
        "preset": preset,
        "completed_at": _now(),
        "total": len(topic_slugs),
        "clean": clean, "unsure": unsure, "help": helped,
        "clean_pass": unsure == 0 and helped == 0,
        "problems": [{"slug": s, "outcome": outcomes.get(s, "")} for s in topic_slugs],
    }
    tests[topic] = rec
    return rec


def test_status(topic: str, preset: str, topic_slugs: list[str]) -> dict[str, Any]:
    """Status of a topic test at a preset: passed / in-progress / not started."""
    data = _load()
    passed = data.get("tests", {}).get(topic)
    if passed and PRESET_RANK.get(passed.get("preset"), 0) >= PRESET_RANK.get(preset, 0):
        return {"state": "passed", "preset": passed.get("preset"),
                "record": passed}
    outcomes = test_outcomes(topic, preset)
    done = [s for s in topic_slugs if s in outcomes]
    return {"state": "in_progress" if done else "not_started",
            "done": len(done), "total": len(topic_slugs), "outcomes": outcomes,
            "passed_lower": passed}


def stats() -> dict[str, Any]:
    data = _load()
    solved = data["solved"]
    # Count each problem once (most recent solve), so re-solving on another day
    # doesn't inflate the totals; streaks below still use the full dated history.
    latest = _latest_per_slug()
    by_diff: dict[str, int] = {}
    optimal = graded = 0
    for e in latest.values():
        by_diff[e.get("difficulty", "unknown")] = by_diff.get(
            e.get("difficulty", "unknown"), 0
        ) + 1
        opt = e.get("optimality")
        if opt in ("optimal", "suboptimal"):
            graded += 1
            if opt == "optimal":
                optimal += 1
    return {
        "total": len(latest),
        "by_difficulty": by_diff,
        "streak": current_streak(),
        "longest_streak": longest_streak(),
        "optimal": optimal,
        "graded": graded,
        "last": solved[-1] if solved else None,
    }
