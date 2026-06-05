"""Turn a fetched Problem into a solution file (+ test metadata sidecar)."""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path
from typing import Any

from .config import SUPPORTED_LANGUAGES, WORKDIR_META
from .data import Problem


def _wrap_block(text: str, width: int = 78) -> list[str]:
    out: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line.strip():
            out.append("")
            continue
        wrapped = textwrap.wrap(
            raw_line, width=width, break_long_words=False, break_on_hyphens=False
        )
        out.extend(wrapped or [""])
    return out


def _python_signature(starter: str) -> tuple[str, list[str]]:
    """Extract (function_name, param_names) from a LeetCode python3 snippet."""
    m = re.search(r"def\s+(\w+)\s*\(\s*self\s*,?\s*(.*?)\)\s*(->|:)", starter, re.S)
    if not m:
        return ("", [])
    name = m.group(1)
    params_blob = m.group(2)
    params = []
    for part in params_blob.split(","):
        part = part.strip()
        if not part:
            continue
        pname = part.split(":")[0].split("=")[0].strip()
        if pname and pname != "self":
            params.append(pname)
    return (name, params)


def _js_signature(starter: str) -> tuple[str, list[str]]:
    """Extract (function_name, param_names) from a LeetCode javascript snippet."""
    m = re.search(r"(?:var|const|let|function)\s+(\w+)\s*=?\s*function\s*\((.*?)\)", starter, re.S)
    if not m:
        m = re.search(r"function\s+(\w+)\s*\((.*?)\)", starter, re.S)
    if not m:
        return ("", [])
    name = m.group(1)
    params = [p.strip() for p in m.group(2).split(",") if p.strip()]
    return (name, params)


def build_test_cases(problem: Problem, params: list[str]) -> list[dict[str, Any]]:
    """Group raw example stdin lines into per-call argument sets, matched
    with the parsed 'Output:' values. Returns [] when we can't line them up."""
    if not params or not problem.example_inputs or not problem.example_outputs:
        return []
    n = len(params)
    lines = problem.example_inputs
    if len(lines) % n != 0:
        return []
    groups = [lines[i : i + n] for i in range(0, len(lines), n)]
    cases = []
    for group, output in zip(groups, problem.example_outputs):
        cases.append({"input": group, "expected": output})
    return cases


def _comment_block(problem: Problem, lang: str) -> str:
    header_lines = [
        f"{problem.number}. {problem.title} [{problem.difficulty.capitalize()}]",
        problem.url,
        "",
    ]
    header_lines += _wrap_block(problem.description or "(no description available)")

    if lang == "python":
        body = "\n".join(header_lines)
        return f'"""\n{body}\n"""\n'
    # javascript -> block comment
    commented = "\n".join(" * " + ln if ln else " *" for ln in header_lines)
    return f"/*\n{commented}\n */\n"


# LeetCode's online judge auto-imports typing names (List, Optional, ...) plus
# the common standard-library helpers (collections, heapq, ...). Mirroring that
# here means solutions that rely on e.g. `defaultdict` or `Counter` without an
# explicit import run locally just like they do on LeetCode.
_PY_PREAMBLE = (
    "from typing import List, Optional, Dict, Set, Tuple\n"
    "from collections import defaultdict, Counter, deque, OrderedDict\n"
    "import heapq\n"
    "import bisect\n"
    "import math\n"
    "import itertools\n"
    "import functools\n\n"
)


def _solution_body(problem: Problem, lang: str) -> str:
    lc_slug = SUPPORTED_LANGUAGES[lang]["lc_slug"]
    starter = problem.starter_code.get(lc_slug, "")
    if starter:
        if lang == "python":
            return _PY_PREAMBLE + starter.rstrip() + "\n"
        return starter.rstrip() + "\n"
    # Fallback stubs if no official snippet is present (e.g. github source).
    if lang == "python":
        return (
            "class Solution:\n"
            "    def solve(self, *args):\n"
            "        # TODO: implement\n"
            "        pass\n"
        )
    return (
        "/**\n * @return {*}\n */\n"
        "var solve = function() {\n"
        "    // TODO: implement\n"
        "};\n"
    )


def solution_filename(problem: Problem, lang: str) -> str:
    ext = SUPPORTED_LANGUAGES[lang]["ext"]
    return f"{problem.padded_number}-{problem.slug}.{ext}"


def scaffold(problem: Problem, lang: str, dest_dir: Path) -> tuple[Path, dict[str, Any]]:
    """Write the solution file and sidecar metadata. Returns (path, meta)."""
    if lang not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {lang}")

    lc_slug = SUPPORTED_LANGUAGES[lang]["lc_slug"]
    starter = problem.starter_code.get(lc_slug, "")
    if lang == "python":
        func, params = _python_signature(starter)
    else:
        func, params = _js_signature(starter)
    cases = build_test_cases(problem, params)

    filename = solution_filename(problem, lang)
    path = dest_dir / filename

    content = _comment_block(problem, lang) + "\n" + _solution_body(problem, lang)

    if path.exists():
        # Don't clobber work in progress.
        raise FileExistsError(str(path))
    path.write_text(content, encoding="utf-8")

    meta = {
        "number": problem.number,
        "slug": problem.slug,
        "title": problem.title,
        "difficulty": problem.difficulty,
        "language": lang,
        "function": func,
        "params": params,
        "filename": filename,
        "url": problem.url,
        "description": problem.description,
        "test_cases": cases,
    }
    _write_meta(dest_dir, problem.slug, meta)
    _write_last(dest_dir, problem.slug)
    return path, meta


# --------------------------------------------------------------------------- #
# Sidecar metadata (per working directory, under .leetcode/)
# --------------------------------------------------------------------------- #
def _meta_dir(dest_dir: Path) -> Path:
    d = dest_dir / WORKDIR_META
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_meta(dest_dir: Path, slug: str, meta: dict[str, Any]) -> None:
    (_meta_dir(dest_dir) / f"{slug}.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )


def _write_last(dest_dir: Path, slug: str) -> None:
    (_meta_dir(dest_dir) / "last.json").write_text(
        json.dumps({"slug": slug}, indent=2), encoding="utf-8"
    )


def load_meta(dest_dir: Path, slug: str) -> dict[str, Any] | None:
    p = _meta_dir(dest_dir) / f"{slug}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load_last_meta(dest_dir: Path) -> dict[str, Any] | None:
    last = _meta_dir(dest_dir) / "last.json"
    if not last.exists():
        return None
    slug = json.loads(last.read_text(encoding="utf-8")).get("slug")
    return load_meta(dest_dir, slug) if slug else None


def find_meta_for_file(dest_dir: Path, file_path: Path) -> dict[str, Any] | None:
    """Match a solution file back to its metadata by filename."""
    name = file_path.name
    meta_dir = dest_dir / WORKDIR_META
    if not meta_dir.exists():
        return None
    for mp in meta_dir.glob("*.json"):
        if mp.name == "last.json":
            continue
        try:
            data = json.loads(mp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("filename") == name:
            return data
    return None


def cleanup_solution(dest_dir: Path, meta: dict[str, Any]) -> list[str]:
    """Remove a solution file and its sidecar metadata from the working dir.

    Returns the list of paths removed. Safe to call after a successful commit:
    the solution lives in your repo and the streak log is stored separately.
    """
    removed: list[str] = []
    slug = meta.get("slug", "")
    filename = meta.get("filename", "")

    sol = dest_dir / filename if filename else None
    if sol and sol.exists():
        sol.unlink()
        removed.append(sol.name)

    meta_dir = dest_dir / WORKDIR_META
    side = meta_dir / f"{slug}.json" if slug else None
    if side and side.exists():
        side.unlink()
        removed.append(f"{WORKDIR_META}/{side.name}")

    # Clear the "last" pointer if it referenced this problem.
    last = meta_dir / "last.json"
    if last.exists():
        try:
            if json.loads(last.read_text(encoding="utf-8")).get("slug") == slug:
                last.unlink()
        except (json.JSONDecodeError, OSError):
            pass

    # Drop the .leetcode dir entirely if nothing is left in it.
    if meta_dir.exists() and not any(meta_dir.iterdir()):
        meta_dir.rmdir()
    return removed


def clean_workdir(dest_dir: Path) -> list[str]:
    """Remove every scaffolded solution file (and the .leetcode metadata) that
    this tool created in `dest_dir`. Returns the list of removed file names."""
    removed: list[str] = []
    meta_dir = dest_dir / WORKDIR_META
    if not meta_dir.exists():
        return removed
    for mp in list(meta_dir.glob("*.json")):
        if mp.name == "last.json":
            continue
        try:
            data = json.loads(mp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        fname = data.get("filename")
        if fname:
            sol = dest_dir / fname
            if sol.exists():
                sol.unlink()
                removed.append(fname)
        mp.unlink()
    last = meta_dir / "last.json"
    if last.exists():
        last.unlink()
    if not any(meta_dir.iterdir()):
        meta_dir.rmdir()
    return removed
