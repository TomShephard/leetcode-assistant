"""Experimental: estimate a solution's time complexity empirically.

Static Big-O analysis is undecidable in general, so instead we *measure* it:
run the solution on inputs of growing size, time each run, and fit the slope of
log(time) vs log(n). A slope near 1 is linear, near 2 is quadratic, etc. We
then compare the measured class against a known-optimal class for the problem
to decide whether the solution is "optimal" or merely "half solved" (a brute-
force approach that ignores the intended technique -- e.g. nested loops for Two
Sum instead of hashing).

Limitations (it's a prototype): only works when the problem's first argument is
a list of numbers to scale, and only for Python solutions. Everything else
returns an "unknown" verdict rather than a wrong one.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import runner

# Complexity classes ranked from best to worst.
CLASS_RANK = {
    "O(1)": 0, "O(log n)": 1, "O(n)": 2, "O(n log n)": 3,
    "O(n^2)": 4, "O(n^3)": 5,
}
RANK_CLASS = {v: k for k, v in CLASS_RANK.items()}

# Known optimal complexity for common problems (by title-slug). Extend freely.
OPTIMAL_BY_SLUG: dict[str, str] = {
    "two-sum": "O(n)",
    "contains-duplicate": "O(n)",
    "valid-anagram": "O(n)",
    "group-anagrams": "O(n)",
    "top-k-frequent-elements": "O(n)",
    "product-of-array-except-self": "O(n)",
    "valid-palindrome": "O(n)",
    "best-time-to-buy-and-sell-stock": "O(n)",
    "maximum-subarray": "O(n)",
    "3sum": "O(n^2)",
    "container-with-most-water": "O(n)",
    "two-sum-ii-input-array-is-sorted": "O(n)",
    "longest-substring-without-repeating-characters": "O(n)",
    "search-insert-position": "O(log n)",
    "binary-search": "O(log n)",
}


@dataclass
class ComplexityResult:
    measured: str          # e.g. "O(n)" or "unknown"
    exponent: float | None
    optimal: str | None    # known-optimal class, or None if unknown
    verdict: str           # "optimal" | "suboptimal" | "unknown"
    detail: str = ""

    @property
    def is_optimal(self) -> bool:
        return self.verdict == "optimal"


def _slope_to_class(slope: float) -> str:
    if slope < 0.35:
        return "O(1)"
    if slope < 0.85:
        return "O(log n)"          # sub-linear
    if slope < 1.35:
        return "O(n)"
    if slope < 1.7:
        return "O(n log n)"
    if slope < 2.4:
        return "O(n^2)"
    return "O(n^3)"


_HARNESS = r'''
import importlib.util, json, sys, time, copy, random

sol_path, meta_path, sizes_json = sys.argv[1], sys.argv[2], sys.argv[3]
meta = json.load(open(meta_path, encoding="utf-8"))
sizes = json.loads(sizes_json)

spec = importlib.util.spec_from_file_location("sol", sol_path)
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
    inst = mod.Solution()
    fn = getattr(inst, meta["function"])
except Exception as e:
    print(json.dumps({"error": "load: %r" % e})); sys.exit(0)

# Build a template arg list from the first example case.
case = meta["test_cases"][0]
try:
    base_args = [json.loads(x) for x in case["input"]]
except Exception as e:
    print(json.dumps({"error": "parse args: %r" % e})); sys.exit(0)

# Find the first list-of-numbers argument; that's the one we scale.
scale_idx = None
for i, a in enumerate(base_args):
    if isinstance(a, list) and a and all(isinstance(v, (int, float)) for v in a):
        scale_idx = i; break
if scale_idx is None:
    print(json.dumps({"error": "no scalable list arg"})); sys.exit(0)

random.seed(1)

def make_args(n):
    args = []
    for i, a in enumerate(base_args):
        if i == scale_idx:
            args.append([random.randint(0, 10 * n) for _ in range(n)])
        elif isinstance(a, (int, float)) and not isinstance(a, bool):
            # Force worst case: a target that can't be hit (no early exit).
            args.append(-1)
        else:
            args.append(a)
    return args

results = {}
for n in sizes:
    args = make_args(n)
    a = copy.deepcopy(args)
    t0 = time.perf_counter()
    try:
        fn(*a)
    except Exception as e:
        print(json.dumps({"error": "runtime: %r" % e})); sys.exit(0)
    results[str(n)] = time.perf_counter() - t0

print(json.dumps({"results": results, "scaled_arg": scale_idx}))
'''


def estimate(solution_path: Path, meta: dict[str, Any]) -> ComplexityResult:
    slug = meta.get("slug", "")
    optimal = OPTIMAL_BY_SLUG.get(slug)

    if meta.get("language") != "python":
        return ComplexityResult("unknown", None, optimal, "unknown",
                                "complexity probe supports Python only")
    if not meta.get("test_cases") or not meta.get("function"):
        return ComplexityResult("unknown", None, optimal, "unknown",
                                "no example input to scale")

    base = runner._python_cmd()
    if not base:
        return ComplexityResult("unknown", None, optimal, "unknown",
                                "no Python interpreter")

    sizes = [1000, 2000, 4000, 8000]
    with tempfile.TemporaryDirectory() as td:
        mp = Path(td) / "meta.json"
        mp.write_text(json.dumps(meta), encoding="utf-8")
        hp = Path(td) / "harness.py"
        hp.write_text(_HARNESS, encoding="utf-8")
        cmd = base + [str(hp), str(solution_path), str(mp), json.dumps(sizes)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                                  creationflags=runner.NO_WINDOW)
        except subprocess.TimeoutExpired:
            # Couldn't finish even moderate sizes -> almost certainly quadratic+
            return ComplexityResult("O(n^2)", 2.0, optimal,
                                    _verdict("O(n^2)", optimal),
                                    "timed out on growing inputs (slow)")

    out = (proc.stdout or "").strip().splitlines()
    if not out:
        return ComplexityResult("unknown", None, optimal, "unknown",
                                (proc.stderr or "no output").strip()[:200])
    try:
        payload = json.loads(out[-1])
    except json.JSONDecodeError:
        return ComplexityResult("unknown", None, optimal, "unknown", "bad probe output")
    if "error" in payload:
        return ComplexityResult("unknown", None, optimal, "unknown", payload["error"])

    times = payload["results"]
    pts = [(n, times[str(n)]) for n in sizes if times.get(str(n), 0) > 0]
    if len(pts) < 3:
        return ComplexityResult("unknown", None, optimal, "unknown",
                                "runs too fast to measure reliably")

    slope = _loglog_slope(pts)
    measured = _slope_to_class(slope)
    return ComplexityResult(measured, round(slope, 2), optimal,
                            _verdict(measured, optimal),
                            f"fitted exponent ~{slope:.2f}")


def _loglog_slope(points: list[tuple[int, float]]) -> float:
    xs = [math.log(n) for n, _ in points]
    ys = [math.log(t) for _, t in points]
    k = len(xs)
    mx, my = sum(xs) / k, sum(ys) / k
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den if den else 0.0


def _verdict(measured: str, optimal: str | None) -> str:
    if optimal is None or measured == "unknown":
        return "unknown"
    if CLASS_RANK.get(measured, 99) <= CLASS_RANK.get(optimal, -1):
        return "optimal"
    return "suboptimal"
