"""Refresh the bundled NeetCode roadmap dataset.

neetcode.io is an Angular app whose problem data (including the blind75 /
neetcode150 / neetcode250 flags) is embedded in its main.<hash>.js bundle.
The community `neetcode-gh` JSON only carries blind75/neetcode150, so to get
the 250 list we extract straight from the site bundle and write a static JSON
into the package. Re-run this whenever you want to refresh the lists:

    py tools/refresh_neetcode_data.py
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

PRACTICE_URL = "https://neetcode.io/practice"
OUT_PATH = Path(__file__).resolve().parent.parent / "leetcode_assistant" / "neetcode_roadmap.json"

ROADMAP_PATTERNS = {
    "Arrays & Hashing", "Two Pointers", "Stack", "Binary Search", "Sliding Window",
    "Linked List", "Trees", "Tries", "Heap / Priority Queue", "Backtracking",
    "Graphs", "Advanced Graphs", "1-D Dynamic Programming", "2-D Dynamic Programming",
    "Greedy", "Intervals", "Math & Geometry", "Bit Manipulation",
}


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return resp.read().decode("utf-8", "replace")


def _field(obj: str, key: str) -> str:
    m = re.search(key + r':"((?:[^"\\]|\\.)*)"', obj)
    return m.group(1) if m else ""


def _flag(obj: str, key: str) -> bool:
    # minified booleans: !0 == true, !1 == false
    return re.search(key + r":!0\b", obj) is not None


def main() -> int:
    html = _get(PRACTICE_URL)
    m = re.search(r"(main\.[A-Za-z0-9]+\.js)", html)
    if not m:
        raise SystemExit("Could not find main.js in the practice page.")
    js = _get("https://neetcode.io/" + m.group(1))

    objs = re.findall(r'\{problem:"(?:[^"\\]|\\.)*"[^{}]*\}', js)
    records = []
    seen = set()
    for obj in objs:
        pattern = _field(obj, "pattern")
        if pattern not in ROADMAP_PATTERNS:
            continue
        link = _field(obj, "link")
        slug = link.rstrip("/").split("/")[-1] if link else ""
        if not slug or slug in seen:
            continue
        seen.add(slug)
        code = _field(obj, "code")
        num_m = re.match(r"\s*0*(\d+)", code)
        records.append({
            "number": int(num_m.group(1)) if num_m else 0,
            "slug": slug,
            "title": _field(obj, "problem"),
            "difficulty": _field(obj, "difficulty").lower(),
            "pattern": pattern,
            "blind75": _flag(obj, "blind75"),
            "neetcode150": _flag(obj, "neetcode150"),
            "neetcode250": _flag(obj, "neetcode250"),
        })

    records.sort(key=lambda r: (r["pattern"], r["number"]))
    OUT_PATH.write_text(json.dumps(records, indent=2), encoding="utf-8")

    print(f"wrote {len(records)} problems -> {OUT_PATH}")
    for key in ("blind75", "neetcode150", "neetcode250"):
        print(f"  {key}: {sum(1 for r in records if r[key])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
