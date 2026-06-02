"""`leetcode doctor` -- preflight checks so first-run problems are obvious."""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any

from . import config as cfg

OK, WARN, FAIL = "ok", "warn", "fail"
_MARK = {OK: "[ ok ]", WARN: "[warn]", FAIL: "[fail]"}

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0


def _check_python() -> tuple[str, str]:
    v = sys.version_info
    if v >= (3, 9):
        return OK, f"Python {v.major}.{v.minor}.{v.micro}"
    return FAIL, f"Python {v.major}.{v.minor} (need 3.9+)"


def _check_cmd(name: str, required: bool, note: str) -> tuple[str, str]:
    found = shutil.which(name)
    if found:
        return OK, f"{name} found ({found})"
    return (FAIL if required else WARN), f"{name} not found -- {note}"


def _check_config() -> list[tuple[str, str, str]]:
    out = []
    config = cfg.load_config()
    if config is None:
        out.append((WARN, "config", "not set up yet -- run `leetcode config` or fetch once"))
        return out
    out.append((OK, "config", f"found at {cfg.CONFIG_PATH}"))
    repo_url = config.get("repo_url", "")
    if repo_url:
        out.append((OK, "repo url", repo_url))
    else:
        out.append((WARN, "repo url", "not set -- submit won't be able to push"))
    return out


def _check_repo_reachable() -> tuple[str, str]:
    config = cfg.load_config() or {}
    repo_url = config.get("repo_url", "")
    if not repo_url:
        return WARN, "skipped (no repo url configured)"
    if not shutil.which("git"):
        return FAIL, "git not installed"
    try:
        proc = subprocess.run(
            ["git", "ls-remote", "--heads", repo_url],
            capture_output=True, text=True, timeout=25, creationflags=_NO_WINDOW)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return FAIL, f"could not reach repo: {exc}"
    if proc.returncode == 0:
        return OK, "reachable and authenticated"
    err = (proc.stderr or proc.stdout).strip().splitlines()
    last = err[-1] if err else "unknown error"
    if any(s in (proc.stderr or "").lower() for s in
           ("authentication", "denied", "could not read", "403", "401")):
        return FAIL, "auth failed -- sign in (e.g. `gh auth login` or any git push prompt)"
    return FAIL, f"not reachable: {last}"


def _check_network() -> tuple[str, str]:
    import urllib.request
    try:
        req = urllib.request.Request("https://leetcode.com/api/problems/all/",
                                     headers={"User-Agent": "leetcode-assistant"})
        with urllib.request.urlopen(req, timeout=15):
            return OK, "leetcode.com reachable"
    except Exception as exc:  # noqa: BLE001
        return FAIL, f"cannot reach leetcode.com: {exc}"


def run() -> int:
    rows: list[tuple[str, str, str]] = []
    s, m = _check_python(); rows.append((s, "python", m))
    s, m = _check_cmd("git", True, "needed to commit/push solutions"); rows.append((s, "git", m))
    s, m = _check_cmd("gh", False, "optional; smoother GitHub auth"); rows.append((s, "gh", m))
    s, m = _check_cmd("node", False, "optional; only to run JavaScript solutions"); rows.append((s, "node", m))
    rows.extend(_check_config())
    s, m = _check_network(); rows.append((s, "network", m))
    s, m = _check_repo_reachable(); rows.append((s, "repo auth", m))

    print("leetcode-assistant doctor\n")
    worst = OK
    for status, label, msg in rows:
        print(f"  {_MARK[status]}  {label:<10} {msg}")
        if status == FAIL:
            worst = FAIL
        elif status == WARN and worst != FAIL:
            worst = WARN
    print()
    if worst == FAIL:
        print("Some checks failed -- fix the [fail] items above.")
        return 1
    if worst == WARN:
        print("Mostly good; the [warn] items are optional or not set up yet.")
        return 0
    print("All good. You're ready to go.")
    return 0
