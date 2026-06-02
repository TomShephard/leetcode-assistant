"""Problem data providers.

Default provider is LeetCode's own public endpoints, because they give us
real descriptions, official starter code, AND the example test cases needed
to actually run `leetcode test`:

    https://leetcode.com/api/problems/all/   -> the problem index
    https://leetcode.com/graphql             -> per-problem content

A secondary "github" provider can read a JSON dataset hosted on GitHub
(configurable URL) for users who prefer that, though such datasets rarely
ship runnable test cases.
"""

from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from html import unescape
from typing import Any

from .config import TOPICS_CACHE, ensure_home


LEETCODE_API_ALL = "https://leetcode.com/api/problems/all/"
LEETCODE_GRAPHQL = "https://leetcode.com/graphql"
LEVEL_TO_NAME = {1: "easy", 2: "medium", 3: "hard"}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (leetcode-assistant)",
    "Referer": "https://leetcode.com",
    "Content-Type": "application/json",
}


class DataError(RuntimeError):
    """Raised when problem data cannot be fetched."""


@dataclass
class Problem:
    number: int
    slug: str
    title: str
    difficulty: str  # easy / medium / hard
    paid_only: bool = False
    description: str = ""
    url: str = ""
    starter_code: dict[str, str] = field(default_factory=dict)  # lc_slug -> code
    example_inputs: list[str] = field(default_factory=list)  # raw stdin lines
    example_outputs: list[str] = field(default_factory=list)  # parsed "Output:" lines

    @property
    def padded_number(self) -> str:
        return f"{self.number:04d}"


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def _get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise DataError(f"Could not reach {url}: {exc}") from exc


def _post_graphql(query: str, variables: dict[str, Any]) -> Any:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(LEETCODE_GRAPHQL, data=payload, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise DataError(f"GraphQL request failed: {exc}") from exc


# --------------------------------------------------------------------------- #
# HTML -> text + example output parsing
# --------------------------------------------------------------------------- #
def html_to_text(html: str) -> str:
    """Best-effort conversion of LeetCode's HTML description to plain text."""
    if not html:
        return ""
    text = html
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</li\s*>", "\n", text)
    text = re.sub(r"(?i)<li\s*>", "  - ", text)
    text = re.sub(r"(?i)</?(pre|ul|ol|div)[^>]*>", "\n", text)
    text = re.sub(r"<sup>(.*?)</sup>", r"^\1", text)
    text = re.sub(r"<sub>(.*?)</sub>", r"_\1", text)
    text = re.sub(r"<[^>]+>", "", text)  # strip remaining tags
    text = unescape(text)
    text = text.replace("\u00a0", " ").replace("\u200b", "")  # nbsp / zero-width
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_example_outputs(text: str) -> list[str]:
    """Pull the value after each 'Output:' label from the plain-text body."""
    outputs: list[str] = []
    for line in text.splitlines():
        m = re.match(r"\s*Output:\s*(.*\S)\s*$", line)
        if m:
            outputs.append(m.group(1).strip())
    return outputs


# --------------------------------------------------------------------------- #
# LeetCode provider
# --------------------------------------------------------------------------- #
_index_cache: list[dict[str, Any]] | None = None


def _leetcode_index() -> list[dict[str, Any]]:
    global _index_cache
    if _index_cache is not None:
        return _index_cache
    data = _get_json(LEETCODE_API_ALL)
    rows = []
    for item in data.get("stat_status_pairs", []):
        stat = item.get("stat", {})
        rows.append(
            {
                "number": stat.get("frontend_question_id"),
                "slug": stat.get("question__title_slug"),
                "title": stat.get("question__title"),
                "difficulty": LEVEL_TO_NAME.get(
                    item.get("difficulty", {}).get("level", 0), "unknown"
                ),
                "paid_only": bool(item.get("paid_only", False)),
            }
        )
    _index_cache = [r for r in rows if r["slug"] and r["number"]]
    return _index_cache


def _leetcode_content(problem: Problem) -> Problem:
    query = """
    query q($slug: String!) {
      question(titleSlug: $slug) {
        questionFrontendId
        title
        difficulty
        content
        exampleTestcases
        codeSnippets { langSlug code }
      }
    }
    """
    resp = _post_graphql(query, {"slug": problem.slug})
    q = (resp or {}).get("data", {}).get("question")
    if not q:
        raise DataError(
            f"No content available for '{problem.slug}' "
            "(it may be a premium/locked problem)."
        )
    problem.title = q.get("title") or problem.title
    problem.difficulty = (q.get("difficulty") or problem.difficulty).lower()
    text = html_to_text(q.get("content") or "")
    problem.description = text
    problem.example_outputs = parse_example_outputs(text)
    raw_inputs = (q.get("exampleTestcases") or "").splitlines()
    problem.example_inputs = [ln for ln in raw_inputs if ln.strip() != ""]
    problem.starter_code = {
        sn["langSlug"]: sn["code"] for sn in (q.get("codeSnippets") or [])
    }
    return problem


def _row_to_problem(row: dict[str, Any]) -> Problem:
    return Problem(
        number=int(row["number"]),
        slug=row["slug"],
        title=row["title"],
        difficulty=row["difficulty"],
        paid_only=row["paid_only"],
        url=f"https://leetcode.com/problems/{row['slug']}/",
    )


def leetcode_pick(
    difficulty: str = "any", include_paid: bool = False
) -> Problem:
    index = _leetcode_index()
    pool = index
    if not include_paid:
        pool = [r for r in pool if not r["paid_only"]]
    if difficulty in ("easy", "medium", "hard"):
        pool = [r for r in pool if r["difficulty"] == difficulty]
    if not pool:
        raise DataError(f"No problems match difficulty='{difficulty}'.")
    return _leetcode_content(_row_to_problem(random.choice(pool)))


def leetcode_get(identifier: str) -> Problem:
    """Look up by frontend number or by title-slug."""
    index = _leetcode_index()
    ident = identifier.strip().lower()
    row = None
    if ident.isdigit():
        target = int(ident)
        row = next((r for r in index if int(r["number"]) == target), None)
    else:
        row = next((r for r in index if r["slug"] == ident), None)
    if row is None:
        raise DataError(f"Could not find problem '{identifier}'.")
    return _leetcode_content(_row_to_problem(row))


# --------------------------------------------------------------------------- #
# GitHub dataset provider (best-effort; usually no runnable test cases)
# --------------------------------------------------------------------------- #
def _github_dataset(url: str) -> list[dict[str, Any]]:
    data = _get_json(url)
    if isinstance(data, dict):
        for key in ("problems", "questions", "data"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise DataError("GitHub dataset is not a JSON array of problems.")
    return data


def _github_to_problem(item: dict[str, Any]) -> Problem:
    def pick(*keys: str, default: Any = "") -> Any:
        for k in keys:
            if k in item and item[k] not in (None, ""):
                return item[k]
        return default

    number = pick("number", "id", "frontend_id", "questionFrontendId", default=0)
    slug = pick("slug", "titleSlug", "stat_slug")
    title = pick("title", "name", "question__title")
    if not slug and title:
        slug = re.sub(r"[^a-z0-9]+", "-", str(title).lower()).strip("-")
    difficulty = str(pick("difficulty", "level", default="unknown")).lower()
    description = pick("description", "content", "body")
    return Problem(
        number=int(number or 0),
        slug=str(slug),
        title=str(title),
        difficulty=difficulty if difficulty in LEVEL_TO_NAME.values() else difficulty,
        description=html_to_text(str(description)) if "<" in str(description) else str(description),
        url=str(pick("url", default=f"https://leetcode.com/problems/{slug}/")),
    )


def github_pick(url: str, difficulty: str = "any") -> Problem:
    items = _github_dataset(url)
    if difficulty in ("easy", "medium", "hard"):
        items = [
            i for i in items
            if str(i.get("difficulty", i.get("level", ""))).lower() == difficulty
        ]
    if not items:
        raise DataError(f"No problems match difficulty='{difficulty}' in dataset.")
    return _github_to_problem(random.choice(items))


def github_get(url: str, identifier: str) -> Problem:
    items = _github_dataset(url)
    ident = identifier.strip().lower()
    for i in items:
        num = str(i.get("number", i.get("id", ""))).lower()
        slug = str(i.get("slug", i.get("titleSlug", ""))).lower()
        if ident == num or ident == slug:
            return _github_to_problem(i)
    raise DataError(f"Could not find '{identifier}' in dataset.")


# --------------------------------------------------------------------------- #
# Unified entry points
# --------------------------------------------------------------------------- #
def fetch_problem(config: dict[str, Any], identifier: str | None, difficulty: str) -> Problem:
    source = config.get("source", "leetcode")
    if source == "github":
        url = config.get("github_dataset_url", "")
        if not url:
            raise DataError(
                "source is 'github' but no github_dataset_url is configured."
            )
        return github_get(url, identifier) if identifier else github_pick(url, difficulty)
    # default
    if identifier:
        return leetcode_get(identifier)
    return leetcode_pick(difficulty, bool(config.get("include_paid", False)))


# --------------------------------------------------------------------------- #
# Browse ALL of LeetCode by topic tag (the non-NeetCode view)
# --------------------------------------------------------------------------- #
# LeetCode's own topic taxonomy: every problem carrying that tag is available.
LEETCODE_TOPICS: list[tuple[str, str]] = [
    ("Array", "array"),
    ("Hashing", "hash-table"),
    ("String", "string"),
    ("Two Pointers", "two-pointers"),
    ("Sliding Window", "sliding-window"),
    ("Stack", "stack"),
    ("Monotonic Stack", "monotonic-stack"),
    ("Queue", "queue"),
    ("Binary Search", "binary-search"),
    ("Linked List", "linked-list"),
    ("Trees", "tree"),
    ("Binary Search Tree", "binary-search-tree"),
    ("Tries", "trie"),
    ("Heap / Priority Queue", "heap-priority-queue"),
    ("Backtracking", "backtracking"),
    ("Recursion", "recursion"),
    ("Graphs", "graph"),
    ("Union Find", "union-find"),
    ("Dynamic Programming", "dynamic-programming"),
    ("Greedy", "greedy"),
    ("Bit Manipulation", "bit-manipulation"),
    ("Math", "math"),
    ("Geometry", "geometry"),
    ("Matrix", "matrix"),
    ("Sorting", "sorting"),
]
LEETCODE_TOPIC_BY_DISPLAY = {name: slug for name, slug in LEETCODE_TOPICS}

_PROBLEMSET_QUERY = """
query problemsetQuestionList($limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
  problemsetQuestionList: questionList(categorySlug: "", limit: $limit, skip: $skip, filters: $filters) {
    total: totalNum
    questions: data {
      questionFrontendId
      title
      titleSlug
      difficulty
      isPaidOnly
    }
  }
}
"""

_TOPIC_CACHE_TTL = 7 * 24 * 3600


def _load_topic_cache() -> dict[str, Any]:
    if not TOPICS_CACHE.exists():
        return {}
    try:
        return json.loads(TOPICS_CACHE.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_topic_cache(cache: dict[str, Any]) -> None:
    ensure_home()
    try:
        TOPICS_CACHE.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass


def leetcode_topic_questions(slug: str, force: bool = False) -> list[dict[str, Any]]:
    """All LeetCode questions carrying a topic tag (cached on disk for a week).
    Each item: {number, slug, title, difficulty, paid}."""
    cache = _load_topic_cache()
    entry = cache.get(slug)
    if entry and not force and (time.time() - entry.get("ts", 0)) < _TOPIC_CACHE_TTL:
        return entry["questions"]

    questions: list[dict[str, Any]] = []
    skip, page, total = 0, 100, None
    while True:
        resp = _post_graphql(
            _PROBLEMSET_QUERY,
            {"skip": skip, "limit": page, "filters": {"tags": [slug]}})
        block = (resp or {}).get("data", {}).get("problemsetQuestionList")
        if not block:
            break
        total = block.get("total", 0)
        rows = block.get("questions") or []
        for q in rows:
            try:
                number = int(q["questionFrontendId"])
            except (KeyError, ValueError, TypeError):
                continue
            questions.append({
                "number": number,
                "slug": q["titleSlug"],
                "title": q["title"],
                "difficulty": (q.get("difficulty") or "").lower(),
                "paid": bool(q.get("isPaidOnly", False)),
            })
        skip += page
        if total is None or skip >= total or not rows:
            break

    questions.sort(key=lambda r: r["number"])
    cache[slug] = {"ts": time.time(), "questions": questions}
    _save_topic_cache(cache)
    return questions
