"""Generate a presentable README.md for the solutions repo from the solve log.

Rebuilt on every submission so it always reflects the full history: a header
with summary badges, per-difficulty counts, and a reverse-chronological table
of every solved problem with its topic and whether it was solved optimally.
"""

from __future__ import annotations

from typing import Any

_DIFF_ORDER = {"easy": 0, "medium": 1, "hard": 2}
_APPROACH = {"optimal": "Optimal", "suboptimal": "Suboptimal"}


def _fmt_time(seconds: Any) -> str:
    if not seconds:
        return "-"
    try:
        s = int(seconds)
    except (TypeError, ValueError):
        return "-"
    return f"{s // 60}m {s % 60}s" if s >= 60 else f"{s}s"


def _badge(label: str, value: str, color: str) -> str:
    def enc(s: str) -> str:
        return (s.replace("-", "--").replace("_", "__")
                .replace("/", "%2F").replace(" ", "%20"))
    return f"![{label}](https://img.shields.io/badge/{enc(label)}-{enc(value)}-{color})"


def _review_section(reviews: dict[str, Any]) -> list[str]:
    """Render the spaced-repetition schedule (due now + upcoming)."""
    from datetime import date, datetime
    if not reviews:
        return []
    _names = ["Learning", "Familiar", "Confident", "Mastered"]
    today = date.today()
    rows = []
    for slug, r in reviews.items():
        try:
            due = datetime.strptime(r["due"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        rows.append((due, slug, r))
    rows.sort(key=lambda t: t[0])
    due_now = [t for t in rows if t[0] <= today]

    out = ["## Review schedule", ""]
    out.append(f"Spaced-repetition refresh queue -- **{len(due_now)} due now**, "
               f"{len(rows)} tracked. Blind-retest the due ones and rate your "
               f"confidence to push them further out.")
    out.append("")
    out.append("| Status | # | Problem | Level | Last | Next review |")
    out.append("|--------|---|---------|-------|------|-------------|")
    for due, slug, r in rows:
        lvl = r.get("level", 0)
        name = _names[lvl] if lvl < len(_names) else f"L{lvl}"
        url = r.get("url") or f"https://leetcode.com/problems/{slug}/"
        title = r.get("title", slug)
        if due <= today:
            status = "**DUE**" if due == today else f"**DUE +{(today - due).days}d**"
            when = r["due"]
        else:
            status = "scheduled"
            when = f"{r['due']} (in {(due - today).days}d)"
        last = r.get("last_rating") or "-"
        out.append(f"| {status} | {r.get('number','')} | [{title}]({url}) | "
                   f"{name} | {last} | {when} |")
    out.append("")
    return out


_PRESET_NAMES = {"blind75": "Blind 75", "neetcode150": "NeetCode 150",
                 "neetcode250": "NeetCode 250", "all": "NeetCode (All)"}


def _testing_section(tests: dict[str, Any]) -> list[str]:
    """Passed topic tests only (back-to-back gauntlets)."""
    if not tests:
        return []
    out = ["## Topic tests", ""]
    out.append("Back-to-back topic gauntlets -- a pass means every problem in "
               "the topic (at the listed question set) was solved in one run. "
               "Only passed topics are shown; passes do not expire.")
    out.append("")
    out.append("| Topic | Question set | Result | Problems | Completed |")
    out.append("|-------|--------------|--------|----------|-----------|")
    for topic in sorted(tests):
        t = tests[topic]
        setname = _PRESET_NAMES.get(t.get("preset", ""), t.get("preset", "?"))
        if t.get("clean_pass"):
            result = "Pass (clean sweep)"
        else:
            bits = []
            if t.get("clean"):
                bits.append(f"{t['clean']} clean")
            if t.get("unsure"):
                bits.append(f"{t['unsure']} unsure")
            if t.get("help"):
                bits.append(f"{t['help']} used help")
            result = "Pass (" + ", ".join(bits) + ")"
        out.append(f"| {topic} | {setname} | {result} | {t.get('total','')} | "
                   f"{t.get('completed_at','')} |")
    out.append("")
    # Per-topic question log (collapsible to keep it tidy).
    for topic in sorted(tests):
        t = tests[topic]
        out.append(f"<details><summary>{topic} -- questions tested "
                   f"({t.get('total','')})</summary>")
        out.append("")
        for p in t.get("problems", []):
            o = p.get("outcome", "")
            tag = {"clean": "", "unsure": " (unsure)", "help": " (used help)"}.get(o, "")
            out.append(f"- {p.get('slug','')}{tag}")
        out.append("</details>")
        out.append("")
    return out


def generate(entries: list[dict[str, Any]], streak: int = 0,
             reviews: dict[str, Any] | None = None,
             tests: dict[str, Any] | None = None) -> str:
    total = len(entries)
    by_diff = {"easy": 0, "medium": 0, "hard": 0}
    optimal = suboptimal = 0
    for e in entries:
        by_diff[e.get("difficulty", "")] = by_diff.get(e.get("difficulty", ""), 0) + 1
        opt = e.get("optimality")
        if opt == "optimal":
            optimal += 1
        elif opt == "suboptimal":
            suboptimal += 1

    graded = optimal + suboptimal
    lines: list[str] = []
    lines.append("# LeetCode Solutions")
    lines.append("")
    badges = [
        _badge("Solved", str(total), "1f6feb"),
        _badge("Streak", f"{streak} days", "f59e0b"),
        _badge("Easy", str(by_diff["easy"]), "1a7f37"),
        _badge("Medium", str(by_diff["medium"]), "9a6700"),
        _badge("Hard", str(by_diff["hard"]), "cf222e"),
    ]
    if graded:
        badges.append(_badge("Optimal", f"{optimal}/{graded}", "2f6feb"))
    lines.append(" ".join(badges))
    lines.append("")
    lines.append("Auto-generated log of my LeetCode solutions. "
                 "Updated automatically on every submission.")
    lines.append("")

    if graded:
        pct = round(100 * optimal / graded)
        lines.append(f"**Solved optimally:** {optimal}/{graded} ({pct}%)  -  "
                     f"flagged as brute-force/suboptimal: {suboptimal}")
        lines.append("")

    # 1) Log (most recent first)
    ordered = sorted(
        entries,
        key=lambda e: (e.get("date", ""), e.get("number", 0)),
        reverse=True,
    )
    lines.append("## Log")
    lines.append("")
    lines.append("| Date | # | Problem | Difficulty | Topic | Approach | Time |")
    lines.append("|------|---|---------|------------|-------|----------|------|")
    for e in ordered:
        url = e.get("url") or f"https://leetcode.com/problems/{e.get('slug','')}/"
        title = e.get("title", e.get("slug", "?"))
        diff = (e.get("difficulty", "") or "").capitalize() or "-"
        topic = e.get("topic") or "-"
        approach = _APPROACH.get(e.get("optimality", ""), "-")
        lines.append(f"| {e.get('date','')} | {e.get('number','')} | "
                     f"[{title}]({url}) | {diff} | {topic} | {approach} | "
                     f"{_fmt_time(e.get('seconds'))} |")
    lines.append("")

    # 2) Review schedule (below the log)
    lines.extend(_review_section(reviews or {}))

    # 3) Topic tests (below the review schedule)
    lines.extend(_testing_section(tests or {}))

    lines.append("---")
    lines.append("*Generated by [leetcode-assistant](https://github.com/TomShephard/"
                 "leetcode-assistant).*")
    lines.append("")
    return "\n".join(lines)
