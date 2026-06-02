"""Configuration + on-disk paths for leetcode-assistant.

Everything that should outlive a single working directory lives under
``~/.leetcode-assistant``:

    config.json    user settings (repo URL, language, difficulty filter)
    progress.json  solve log used for streak tracking
    repo/          local clone of the user's private solutions repo
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

HOME_DIR = Path.home() / ".leetcode-assistant"
# Previous location (the tool used to be called "leetcode-cli"); migrated once.
_OLD_HOME_DIR = Path.home() / ".leetcode-cli"
CONFIG_PATH = HOME_DIR / "config.json"
PROGRESS_PATH = HOME_DIR / "progress.json"
REPO_DIR = HOME_DIR / "repo"
TOPICS_CACHE = HOME_DIR / "topics_cache.json"
NEETCODE_CACHE = HOME_DIR / "neetcode_cache.json"


def _migrate_old_home() -> None:
    """Carry settings/progress over from the old ~/.leetcode-cli folder once."""
    if not _OLD_HOME_DIR.exists():
        return
    try:
        HOME_DIR.mkdir(parents=True, exist_ok=True)
        for name in ("config.json", "progress.json"):
            old, new = _OLD_HOME_DIR / name, HOME_DIR / name
            if old.exists() and not new.exists():
                shutil.copyfile(old, new)
    except OSError:
        pass

# Per-working-directory scratch space for fetched problem metadata so that
# `leetcode test` / `leetcode submit` can run without re-fetching.
WORKDIR_META = ".leetcode"

SUPPORTED_LANGUAGES = {
    "python": {"ext": "py", "lc_slug": "python3"},
    "javascript": {"ext": "js", "lc_slug": "javascript"},
}

VALID_DIFFICULTIES = ("easy", "medium", "hard")

DEFAULTS: dict[str, Any] = {
    "repo_url": "",
    "language": "python",
    "default_difficulty": "any",
    "include_paid": False,
    "source": "leetcode",  # or "github"
    "github_dataset_url": "",
    "editor": "",  # explicit editor command; blank = auto-detect PyCharm
    "workdir": "",  # last-used solutions folder (GUI remembers this)
    "delete_after_submit": False,  # remove the local file once it's committed
    "preset": "neetcode150",  # roadmap preset: blind75 / neetcode150 / all
    "review_intervals": [7, 30, 90, 365],  # spaced-repetition ladder, in days
}


def ensure_home() -> None:
    _migrate_old_home()
    HOME_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any] | None:
    """Return the saved config, or ``None`` if the tool has not been set up."""
    _migrate_old_home()
    if not CONFIG_PATH.exists():
        return None
    try:
        # utf-8-sig tolerates a UTF-8 BOM from hand-edited files.
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return None
    merged = dict(DEFAULTS)
    merged.update(data)
    return merged


def save_config(config: dict[str, Any]) -> None:
    ensure_home()
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{label}{suffix}: ").strip()
    except EOFError:
        answer = ""
    return answer or default


def first_run_setup() -> dict[str, Any]:
    """Interactively create the config file. Returns the saved config."""
    print("\nWelcome to leetcode-assistant! Let's set things up (saved to")
    print(f"{CONFIG_PATH}).\n")

    config = dict(DEFAULTS)

    config["repo_url"] = _prompt(
        "Private GitHub repo URL for your solutions (e.g. "
        "https://github.com/you/leetcode or git@github.com:you/leetcode.git)"
    )

    lang = ""
    while lang not in SUPPORTED_LANGUAGES:
        lang = _prompt("Preferred language (python/javascript)", "python").lower()
        if lang in ("py", "python3"):
            lang = "python"
        if lang in ("js", "node"):
            lang = "javascript"
        if lang not in SUPPORTED_LANGUAGES:
            print("  Please enter 'python' or 'javascript'.")
    config["language"] = lang

    diff = ""
    allowed = VALID_DIFFICULTIES + ("any",)
    while diff not in allowed:
        diff = _prompt(
            "Default difficulty filter (easy/medium/hard/any)", "any"
        ).lower()
        if diff not in allowed:
            print("  Please enter easy, medium, hard, or any.")
    config["default_difficulty"] = diff

    save_config(config)
    print("\nConfig saved. You're ready to go:\n")
    print("  leetcode fetch     # grab a problem and scaffold a file")
    print("  leetcode test      # run the example test cases")
    print("  leetcode submit    # commit + push a passing solution\n")
    return config


def get_config_or_setup() -> dict[str, Any]:
    config = load_config()
    if config is None:
        config = first_run_setup()
    return config
