"""Commit + push a passing solution to the user's private GitHub repo.

Uses the `gh` CLI when available (nicer auth handling), otherwise falls back
to raw `git`. A local clone is kept at ~/.leetcode-cli/repo so we never touch
the user's working directory's git state.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from .config import REPO_DIR


class RepoError(RuntimeError):
    pass


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, cwd=str(cwd) if cwd else None,
        capture_output=True, text=True,
    )


def _check(args: list[str], cwd: Path | None = None) -> str:
    proc = _run(args, cwd)
    if proc.returncode != 0:
        raise RepoError(
            f"`{' '.join(args)}` failed:\n{(proc.stderr or proc.stdout).strip()}"
        )
    return proc.stdout.strip()


def _normalize_clone_target(repo_url: str) -> str:
    return repo_url.strip()


def ensure_clone(repo_url: str) -> Path:
    """Make sure REPO_DIR contains an up-to-date clone of repo_url."""
    if not repo_url:
        raise RepoError("No repo URL configured. Run `leetcode config` to set one.")

    if not _has("git"):
        raise RepoError("git is not installed or not on PATH.")

    git_dir = REPO_DIR / ".git"
    if git_dir.exists():
        # Pull latest, but don't fail the whole submit on a transient pull error.
        proc = _run(["git", "pull", "--ff-only"], cwd=REPO_DIR)
        if proc.returncode != 0:
            print("  (warning: git pull failed; committing on top of local clone)")
        return REPO_DIR

    REPO_DIR.parent.mkdir(parents=True, exist_ok=True)
    if REPO_DIR.exists():
        # Directory exists but isn't a repo; refuse to clobber.
        if any(REPO_DIR.iterdir()):
            raise RepoError(f"{REPO_DIR} exists and is not a git clone.")

    target = _normalize_clone_target(repo_url)
    print(f"  Cloning {target} into {REPO_DIR} ...")
    if _has("gh"):
        proc = _run(["gh", "repo", "clone", target, str(REPO_DIR)])
        if proc.returncode == 0:
            return REPO_DIR
        print("  (gh clone failed; trying plain git)")
    _check(["git", "clone", target, str(REPO_DIR)])
    return REPO_DIR


def commit_and_push(
    repo_url: str,
    solution_path: Path,
    *,
    number: int,
    title: str,
    difficulty: str,
    slug: str,
    language_ext: str,
) -> dict[str, Any]:
    repo = ensure_clone(repo_url)

    rel_dir = Path("solutions") / difficulty
    dest_dir = repo / rel_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_name = f"{number:04d}-{slug}.{language_ext}"
    dest_path = dest_dir / dest_name
    rel_path = (rel_dir / dest_name).as_posix()

    shutil.copyfile(solution_path, dest_path)

    _run(["git", "add", rel_path], cwd=repo)

    # Nothing staged? Then the file is unchanged from what's committed.
    status = _run(["git", "status", "--porcelain", rel_path], cwd=repo)
    if not status.stdout.strip():
        return {"committed": False, "path": rel_path, "reason": "no changes"}

    message = f"Solve {number}: {title} ({difficulty.capitalize()})"
    _check(["git", "commit", "-m", message], cwd=repo)

    push = _run(["git", "push"], cwd=repo)
    pushed = push.returncode == 0
    return {
        "committed": True,
        "pushed": pushed,
        "path": rel_path,
        "message": message,
        "push_error": "" if pushed else (push.stderr or push.stdout).strip(),
    }
