"""The NeetCode roadmap: a structured 'course' of curated problems.

Data comes from the public NeetCode dataset (neetcode-gh/leetcode), which tags
each problem with its pattern (topic), difficulty, and which curated list it
belongs to (Blind 75 / NeetCode 150). We expose it as ordered topics with
prerequisite links, plus presets that widen the selection:

    blind75      -> the 75-problem Blind list
    neetcode150  -> the 150-problem NeetCode list (default)
    all          -> every roadmap problem (~420)
"""

from __future__ import annotations

import json
import random
import re
import urllib.error
import urllib.request
from typing import Any

NEETCODE_DATA_URL = (
    "https://raw.githubusercontent.com/neetcode-gh/leetcode/main/.problemSiteData.json"
)

# Presets, in increasing breadth.
PRESETS: list[tuple[str, str]] = [
    ("blind75", "Blind 75"),
    ("neetcode150", "NeetCode 150"),
    ("neetcode250", "NeetCode 250"),
    ("all", "NeetCode (All)"),
]
PRESET_NAMES = {key: name for key, name in PRESETS}
DEFAULT_PRESET = "neetcode150"

# Topics in roadmap (topological) order. Names must match the dataset's
# `pattern` field exactly.
ROADMAP_ORDER: list[str] = [
    "Arrays & Hashing",
    "Two Pointers",
    "Stack",
    "Binary Search",
    "Sliding Window",
    "Linked List",
    "Trees",
    "Tries",
    "Heap / Priority Queue",
    "Backtracking",
    "Graphs",
    "Advanced Graphs",
    "1-D Dynamic Programming",
    "2-D Dynamic Programming",
    "Greedy",
    "Intervals",
    "Math & Geometry",
    "Bit Manipulation",
]

# Prerequisites for each topic (from the NeetCode roadmap edges).
PREREQS: dict[str, list[str]] = {
    "Arrays & Hashing": [],
    "Two Pointers": ["Arrays & Hashing"],
    "Stack": ["Arrays & Hashing"],
    "Binary Search": ["Two Pointers"],
    "Sliding Window": ["Two Pointers"],
    "Linked List": ["Two Pointers"],
    "Trees": ["Binary Search", "Linked List"],
    "Tries": ["Trees"],
    "Heap / Priority Queue": ["Trees"],
    "Backtracking": ["Trees"],
    "Graphs": ["Backtracking"],
    "1-D Dynamic Programming": ["Backtracking"],
    "Advanced Graphs": ["Heap / Priority Queue", "Graphs"],
    "Intervals": ["Heap / Priority Queue"],
    "Greedy": ["Heap / Priority Queue"],
    "2-D Dynamic Programming": ["Graphs", "1-D Dynamic Programming"],
    "Math & Geometry": ["Graphs", "Bit Manipulation"],
    "Bit Manipulation": ["1-D Dynamic Programming"],
}


class RoadmapError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# data loading (cached)
# --------------------------------------------------------------------------- #
def _fetch_raw() -> list[dict[str, Any]]:
    req = urllib.request.Request(
        NEETCODE_DATA_URL, headers={"User-Agent": "leetcode-cli"})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RoadmapError(f"Could not fetch NeetCode data: {exc}") from exc


def _slug_from_link(link: str) -> str:
    parts = [p for p in str(link).split("/") if p]
    return parts[-1] if parts else ""


def _number_from_code(code: str) -> int:
    m = re.match(r"\s*0*(\d+)", str(code or ""))
    return int(m.group(1)) if m else 0


# The dataset ships with the package (extracted from neetcode.io; refresh with
# tools/refresh_neetcode_data.py). It carries blind75 / neetcode150 /
# neetcode250 flags, which the community GitHub JSON lacks.
BUNDLED_DATA = __import__("pathlib").Path(__file__).with_name("neetcode_roadmap.json")


def _normalize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize the community GitHub JSON shape (network fallback only)."""
    out = []
    for r in rows:
        pattern = r.get("pattern", "")
        if pattern not in ROADMAP_ORDER:  # skip e.g. the "JavaScript" group
            continue
        slug = _slug_from_link(r.get("link", ""))
        if not slug:
            continue
        out.append({
            "number": _number_from_code(r.get("code", "")),
            "slug": slug,
            "title": r.get("problem", slug),
            "difficulty": str(r.get("difficulty", "")).lower(),
            "pattern": pattern,
            "blind75": bool(r.get("blind75", False)),
            "neetcode150": bool(r.get("neetcode150", False)),
            "neetcode250": bool(r.get("neetcode250", False)),
        })
    return out


_cache: list[dict[str, Any]] | None = None


def all_problems(force: bool = False) -> list[dict[str, Any]]:
    """Every roadmap problem. Loads the bundled dataset (no network); falls
    back to fetching the community GitHub JSON only if the bundle is missing."""
    global _cache
    if _cache is not None and not force:
        return _cache

    if BUNDLED_DATA.exists():
        try:
            problems = json.loads(BUNDLED_DATA.read_text(encoding="utf-8-sig"))
            problems = [p for p in problems if p.get("pattern") in ROADMAP_ORDER]
            _cache = problems
            return _cache
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback: community dataset (blind75/neetcode150 only, no 250).
    problems = _normalize(_fetch_raw())
    _cache = problems
    return problems


# --------------------------------------------------------------------------- #
# preset / topic queries
# --------------------------------------------------------------------------- #
def normalize_preset(preset: str | None) -> str:
    p = (preset or DEFAULT_PRESET).strip().lower()
    aliases = {
        "blind": "blind75", "blind75": "blind75", "75": "blind75",
        "150": "neetcode150", "neetcode150": "neetcode150", "neetcode": "neetcode150",
        "250": "neetcode250", "neetcode250": "neetcode250",
        "all": "all", "allnc": "all",
    }
    return aliases.get(p, DEFAULT_PRESET)


def _in_preset(problem: dict[str, Any], preset: str) -> bool:
    if preset == "blind75":
        return problem.get("blind75", False)
    if preset == "neetcode150":
        return problem.get("neetcode150", False)
    if preset == "neetcode250":
        return problem.get("neetcode250", False)
    return True  # all


def problems_for_preset(preset: str) -> list[dict[str, Any]]:
    preset = normalize_preset(preset)
    return [p for p in all_problems() if _in_preset(p, preset)]


def topics_for_preset(preset: str) -> list[tuple[str, list[dict[str, Any]]]]:
    """Ordered [(topic, [problems])] for the preset, in roadmap order."""
    preset = normalize_preset(preset)
    by_topic: dict[str, list[dict[str, Any]]] = {t: [] for t in ROADMAP_ORDER}
    for p in problems_for_preset(preset):
        by_topic[p["pattern"]].append(p)
    for probs in by_topic.values():
        probs.sort(key=lambda r: (("easy", "medium", "hard").index(r["difficulty"])
                                  if r["difficulty"] in ("easy", "medium", "hard") else 9,
                                  r["number"]))
    return [(t, by_topic[t]) for t in ROADMAP_ORDER]


def topic_problems(topic: str, preset: str) -> list[dict[str, Any]]:
    for t, probs in topics_for_preset(preset):
        if t == topic:
            return probs
    return []


def pick(topic: str, preset: str, difficulty: str = "any",
         exclude: set[str] | None = None) -> dict[str, Any]:
    """Choose a problem from a topic at a preset, preferring unsolved ones."""
    pool = topic_problems(topic, preset)
    if difficulty in ("easy", "medium", "hard"):
        pool = [p for p in pool if p["difficulty"] == difficulty]
    if not pool:
        raise RoadmapError(f"No '{topic}' problems match that filter at this preset.")
    exclude = exclude or set()
    unsolved = [p for p in pool if p["slug"] not in exclude]
    return random.choice(unsolved or pool)


_slug_topic: dict[str, str] | None = None


def topic_for_slug(slug: str) -> str | None:
    """The roadmap topic a problem belongs to, or None if not on the roadmap."""
    global _slug_topic
    if _slug_topic is None:
        try:
            _slug_topic = {p["slug"]: p["pattern"] for p in all_problems()}
        except RoadmapError:
            _slug_topic = {}
    return _slug_topic.get(slug)


def resolve_topic(value: str) -> str | None:
    """Match a topic name loosely (case/punctuation-insensitive)."""
    norm = re.sub(r"[^a-z0-9]", "", value.lower())
    for t in ROADMAP_ORDER:
        if re.sub(r"[^a-z0-9]", "", t.lower()) == norm:
            return t
    # allow short forms like "1d dp", "2d dp", "heap"
    short = {
        "1ddp": "1-D Dynamic Programming", "2ddp": "2-D Dynamic Programming",
        "dp": "1-D Dynamic Programming", "heap": "Heap / Priority Queue",
        "arrays": "Arrays & Hashing", "hashing": "Arrays & Hashing",
        "math": "Math & Geometry", "graphs": "Graphs",
    }
    return short.get(norm)
