"""Run a solution file against its parsed example test cases.

We isolate execution in a subprocess (the user's interpreter for that
language) so a crashing or slow solution can't take the CLI down with it.
The per-language harness loads the solution, calls the target function for
each case, and emits a JSON report on stdout.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CaseResult:
    index: int
    passed: bool
    inputs: list[str]
    expected: str
    actual: str
    note: str = ""
    error: str = ""


@dataclass
class RunReport:
    ran: bool
    results: list[CaseResult]
    skipped_reason: str = ""

    @property
    def passed(self) -> bool:
        return self.ran and bool(self.results) and all(r.passed for r in self.results)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)


PY_HARNESS = r'''
import importlib.util, json, sys, copy

sol_path, meta_path = sys.argv[1], sys.argv[2]
meta = json.load(open(meta_path, encoding="utf-8"))

spec = importlib.util.spec_from_file_location("user_solution", sol_path)
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
except Exception as e:
    print(json.dumps({"fatal": "Could not import solution: %r" % e}))
    sys.exit(0)

if not hasattr(mod, "Solution"):
    print(json.dumps({"fatal": "No `Solution` class found in solution file."}))
    sys.exit(0)

func_name = meta["function"]
inst = mod.Solution()
fn = getattr(inst, func_name, None)
if fn is None:
    print(json.dumps({"fatal": "Method `%s` not found on Solution." % func_name}))
    sys.exit(0)

def canon(v):
    # Canonicalise for order-insensitive comparison: recursively sort every
    # list (so nested lists like Group Anagrams match regardless of the order
    # of the groups OR the order within each group). Dicts compare key-wise.
    if isinstance(v, list):
        items = [canon(x) for x in v]
        try:
            return sorted(items, key=lambda x: json.dumps(x, sort_keys=True))
        except TypeError:
            return items
    if isinstance(v, dict):
        return {k: canon(val) for k, val in v.items()}
    return v

def equalish(a, b):
    if a == b:
        return (True, "")
    if isinstance(a, float) or isinstance(b, float):
        try:
            if abs(float(a) - float(b)) < 1e-5:
                return (True, "matched within tolerance")
        except (TypeError, ValueError):
            pass
    # Many LeetCode problems accept the answer in any order (Group Anagrams,
    # Subsets, Permutations, ...). Fall back to an order-insensitive match.
    try:
        if canon(a) == canon(b):
            return (True, "matched ignoring order")
    except Exception:
        pass
    return (False, "")

results = []
for i, case in enumerate(meta["test_cases"]):
    raw_inputs = case["input"]
    expected_raw = case["expected"]
    entry = {"index": i, "inputs": raw_inputs, "expected": expected_raw}
    try:
        args = [json.loads(x) for x in raw_inputs]
    except Exception as e:
        entry.update(passed=False, actual="", error="Could not parse inputs: %r" % e)
        results.append(entry); continue
    try:
        expected = json.loads(expected_raw)
    except Exception:
        expected = expected_raw
    try:
        out = fn(*copy.deepcopy(args))
    except Exception as e:
        entry.update(passed=False, actual="", error="Runtime error: %r" % e)
        results.append(entry); continue
    ok, note = equalish(out, expected)
    try:
        actual_str = json.dumps(out)
    except TypeError:
        actual_str = str(out)
    entry.update(passed=ok, actual=actual_str, note=note, error="")
    results.append(entry)

print(json.dumps({"results": results}))
'''


JS_HARNESS = r'''
const fs = require("fs");
const path = require("path");
const [, , solPath, metaPath] = process.argv;
const meta = JSON.parse(fs.readFileSync(metaPath, "utf-8"));

let src = fs.readFileSync(solPath, "utf-8");
src += "\nmodule.exports = (typeof " + meta.function + " !== 'undefined') ? " +
       meta.function + " : undefined;\n";
const tmp = solPath + ".__run.js";
fs.writeFileSync(tmp, src);

let fn;
try {
  fn = require(tmp);
} catch (e) {
  console.log(JSON.stringify({ fatal: "Could not load solution: " + e.message }));
  process.exit(0);
} finally {
  try { fs.unlinkSync(tmp); } catch (e) {}
}
if (typeof fn !== "function") {
  console.log(JSON.stringify({ fatal: "Function `" + meta.function + "` not found." }));
  process.exit(0);
}

function canon(v) {
  // Recursively sort every array so nested lists (e.g. Group Anagrams) match
  // regardless of order at any level. Object keys are sorted too.
  if (Array.isArray(v)) {
    const items = v.map(canon);
    items.sort((x, y) => {
      const sx = JSON.stringify(x), sy = JSON.stringify(y);
      return sx < sy ? -1 : sx > sy ? 1 : 0;
    });
    return items;
  }
  if (v && typeof v === "object") {
    const o = {};
    for (const k of Object.keys(v).sort()) o[k] = canon(v[k]);
    return o;
  }
  return v;
}

function equalish(a, b) {
  if (JSON.stringify(a) === JSON.stringify(b)) return [true, ""];
  if (typeof a === "number" && typeof b === "number" && Math.abs(a - b) < 1e-5)
    return [true, "matched within tolerance"];
  // Many LeetCode problems accept any ordering -- compare canonically.
  try {
    if (JSON.stringify(canon(a)) === JSON.stringify(canon(b)))
      return [true, "matched ignoring order"];
  } catch (e) {}
  return [false, ""];
}

const results = [];
meta.test_cases.forEach((c, i) => {
  const entry = { index: i, inputs: c.input, expected: c.expected };
  let args, expected;
  try { args = c.input.map((x) => JSON.parse(x)); }
  catch (e) { entry.passed = false; entry.actual = ""; entry.error = "Could not parse inputs: " + e.message; results.push(entry); return; }
  try { expected = JSON.parse(c.expected); } catch (e) { expected = c.expected; }
  let out;
  try { out = fn(...JSON.parse(JSON.stringify(args))); }
  catch (e) { entry.passed = false; entry.actual = ""; entry.error = "Runtime error: " + e.message; results.push(entry); return; }
  const [ok, note] = equalish(out, expected);
  entry.passed = ok; entry.note = note; entry.error = "";
  try { entry.actual = JSON.stringify(out); } catch (e) { entry.actual = String(out); }
  results.push(entry);
});
console.log(JSON.stringify({ results }));
'''


# On Windows, suppress the console window that would otherwise flash for every
# child process when we run as a windowed (no-console) packaged app.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0


def _find_system_python() -> list[str] | None:
    for name in ("py", "python", "python3"):
        found = shutil.which(name)
        if found:
            return [found]
    return None


def _python_cmd() -> list[str] | None:
    """Return a command that runs a real Python interpreter.

    When packaged as a PyInstaller EXE, ``sys.executable`` points at the bundled
    app (e.g. LeetCodeCLI.exe), so using it would relaunch the GUI instead of
    running the test harness. In that case we must locate a system Python.
    """
    if getattr(sys, "frozen", False):
        return _find_system_python()
    if sys.executable:
        return [sys.executable]
    return _find_system_python()


def _node_cmd() -> list[str] | None:
    for name in ("node", "nodejs"):
        if shutil.which(name):
            return [name]
    return None


def run_tests(solution_path: Path, meta: dict[str, Any]) -> RunReport:
    cases = meta.get("test_cases") or []
    if not cases:
        return RunReport(
            ran=False,
            results=[],
            skipped_reason=(
                "No runnable example test cases were available for this problem. "
                "You can still solve it and submit -- submit will skip the test gate "
                "with a warning."
            ),
        )
    if not meta.get("function"):
        return RunReport(
            ran=False,
            results=[],
            skipped_reason="Could not determine the entry function for this problem.",
        )

    lang = meta.get("language", "python")
    with tempfile.TemporaryDirectory() as td:
        meta_path = Path(td) / "meta.json"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

        if lang == "python":
            base = _python_cmd()
            if not base:
                return RunReport(
                    False, [],
                    "No Python interpreter found on PATH. Install Python "
                    "(python.org) so the app can run your solution.")
            harness = Path(td) / "harness.py"
            harness.write_text(PY_HARNESS, encoding="utf-8")
            cmd = base + [str(harness), str(solution_path), str(meta_path)]
        elif lang == "javascript":
            base = _node_cmd()
            if not base:
                return RunReport(
                    False, [],
                    "Node.js was not found on PATH, so JavaScript solutions can't be "
                    "run locally. Install Node (https://nodejs.org) to enable JS testing.",
                )
            harness = Path(td) / "harness.js"
            harness.write_text(JS_HARNESS, encoding="utf-8")
            cmd = base + [str(harness), str(solution_path), str(meta_path)]
        else:
            return RunReport(False, [], f"Unsupported language: {lang}")

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                creationflags=NO_WINDOW,
            )
        except subprocess.TimeoutExpired:
            return RunReport(False, [], "Solution timed out (>30s).")

        out = proc.stdout.strip()
        if not out:
            err = proc.stderr.strip() or "no output"
            return RunReport(False, [], f"Test harness produced no result: {err}")
        try:
            payload = json.loads(out.splitlines()[-1])
        except json.JSONDecodeError:
            return RunReport(False, [], f"Could not parse harness output:\n{out}")

        if "fatal" in payload:
            return RunReport(False, [], payload["fatal"])

        results = [
            CaseResult(
                index=r["index"],
                passed=bool(r["passed"]),
                inputs=r.get("inputs", []),
                expected=r.get("expected", ""),
                actual=r.get("actual", ""),
                note=r.get("note", ""),
                error=r.get("error", ""),
            )
            for r in payload.get("results", [])
        ]
        return RunReport(ran=True, results=results)
