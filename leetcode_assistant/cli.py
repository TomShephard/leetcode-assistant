"""Command-line interface: leetcode {fetch,test,submit,config,stats}."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from . import __version__, config as cfg
from . import data, progress, repo, roadmap, runner, scaffold
from .config import SUPPORTED_LANGUAGES, VALID_DIFFICULTIES


# --------------------------------------------------------------------------- #
# small output helpers
# --------------------------------------------------------------------------- #
def _rule(char: str = "-", width: int = 60) -> str:
    return char * width


def print_streak_banner() -> None:
    s = progress.stats()
    streak = s["streak"]
    total = s["total"]
    flame = "day" if streak == 1 else "days"
    print(_rule("="))
    if streak > 0:
        print(f" Current streak: {streak} {flame}  |  Total solved: {total}")
    else:
        print(f" Current streak: 0 days  |  Total solved: {total}")
        if total > 0:
            print(" Solve one today to start a new streak.")
    print(_rule("="))


def _resolve_lang(value: str | None, config: dict[str, Any]) -> str:
    lang = (value or config.get("language") or "python").lower()
    aliases = {"py": "python", "python3": "python", "js": "javascript", "node": "javascript"}
    lang = aliases.get(lang, lang)
    if lang not in SUPPORTED_LANGUAGES:
        raise SystemExit(f"Unsupported language '{lang}'. Choose python or javascript.")
    return lang


def _resolve_difficulty(value: str | None, config: dict[str, Any]) -> str:
    diff = (value or config.get("default_difficulty") or "any").lower()
    if diff not in VALID_DIFFICULTIES + ("any",):
        raise SystemExit(f"Invalid difficulty '{diff}'. Use easy/medium/hard/any.")
    return diff


def _resolve_preset(value: str | None, config: dict[str, Any]) -> str:
    return roadmap.normalize_preset(value or config.get("preset"))


# --------------------------------------------------------------------------- #
# target resolution for test/submit
# --------------------------------------------------------------------------- #
def _resolve_target(cwd: Path, file_arg: str | None) -> tuple[Path, dict[str, Any]]:
    if file_arg:
        path = Path(file_arg)
        if not path.is_absolute():
            path = cwd / path
        if not path.exists():
            raise SystemExit(f"File not found: {path}")
        meta = scaffold.find_meta_for_file(cwd, path)
        if meta is None:
            raise SystemExit(
                f"No saved test metadata for {path.name}. Fetch the problem with "
                "`leetcode fetch` so the example cases are recorded, or pass the "
                "matching file from this directory."
            )
        return path, meta

    meta = scaffold.load_last_meta(cwd)
    if meta is None:
        raise SystemExit(
            "Nothing to work on here. Run `leetcode fetch` first, or pass a file."
        )
    path = cwd / meta["filename"]
    if not path.exists():
        raise SystemExit(f"Expected solution file {path} is missing.")
    return path, meta


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_fetch(args: argparse.Namespace, config: dict[str, Any]) -> int:
    lang = _resolve_lang(args.lang, config)
    difficulty = _resolve_difficulty(args.difficulty, config)
    cwd = Path.cwd()

    target = args.problem
    topic = getattr(args, "topic", None)

    try:
        if topic:
            tname = roadmap.resolve_topic(topic)
            if not tname:
                print(f"\nUnknown topic '{topic}'. See `leetcode roadmap` for the list.")
                return 1
            if target:
                print(f"Fetching problem '{target}' ...")
                problem = data.fetch_problem(config, target, difficulty)
            else:
                preset = _resolve_preset(getattr(args, "preset", None), config)
                label = difficulty if difficulty != "any" else "any difficulty"
                print(f"Fetching a {label} '{tname}' problem "
                      f"({roadmap.PRESET_NAMES[preset]}) you haven't solved ...")
                chosen = roadmap.pick(tname, preset, difficulty,
                                      exclude=progress.solved_slugs())
                problem = data.leetcode_get(chosen["slug"])
        else:
            if target:
                print(f"Fetching problem '{target}' ...")
            else:
                label = difficulty if difficulty != "any" else "any difficulty"
                print(f"Fetching a random {label} problem ...")
            problem = data.fetch_problem(config, target, difficulty)
    except (data.DataError, roadmap.RoadmapError) as exc:
        print(f"\nError: {exc}")
        return 1

    try:
        path, meta = scaffold.scaffold(problem, lang, cwd)
    except FileExistsError as exc:
        print(f"\nA file already exists at {exc}. Not overwriting it.")
        print("Delete it or pass a different problem if you want a fresh scaffold.")
        return 1

    print()
    print(f"  {problem.number}. {problem.title}  [{problem.difficulty.capitalize()}]")
    print(f"  {problem.url}")
    print(f"  -> {path.relative_to(cwd) if path.is_relative_to(cwd) else path}")
    n_cases = len(meta.get("test_cases") or [])
    if n_cases:
        print(f"  {n_cases} example test case(s) recorded for `leetcode test`.")
    else:
        print("  (no auto-extractable test cases; you can still test manually)")

    desc = problem.description or ""
    if desc:
        preview = desc.strip().splitlines()
        print("\n  Description preview:")
        for line in preview[:6]:
            print(f"    {line}")
        if len(preview) > 6:
            print("    ...")
    print("\nNext: edit the file, then run `leetcode test`.")
    return 0


def _print_test_report(report: runner.RunReport) -> None:
    if not report.ran:
        print(f"\nSkipped: {report.skipped_reason}")
        return
    print()
    for r in report.results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] case {r.index + 1}")
        if not r.passed or r.note:
            print(f"         input:    {' | '.join(r.inputs)}")
            print(f"         expected: {r.expected}")
            if r.error:
                print(f"         error:    {r.error}")
            else:
                print(f"         got:      {r.actual}")
        if r.note:
            print(f"         note:     {r.note}")
    print()
    print(f"  {report.passed_count}/{report.total} cases passed.")


def cmd_test(args: argparse.Namespace, config: dict[str, Any]) -> int:
    cwd = Path.cwd()
    path, meta = _resolve_target(cwd, args.file)
    print(f"Testing {path.name}  ({meta['number']}. {meta['title']})")
    report = runner.run_tests(path, meta)
    _print_test_report(report)
    if not report.ran:
        return 0  # not a failure, just nothing to run
    return 0 if report.passed else 1


def cmd_submit(args: argparse.Namespace, config: dict[str, Any]) -> int:
    cwd = Path.cwd()
    path, meta = _resolve_target(cwd, args.file)
    repo_url = config.get("repo_url", "")
    if not repo_url:
        print("No repo URL configured. Run `leetcode config` to set one.")
        return 1

    print(f"Submitting {path.name}  ({meta['number']}. {meta['title']})")

    report = runner.run_tests(path, meta)
    _print_test_report(report)

    has_tests = bool(meta.get("test_cases"))
    if has_tests:
        # This problem HAS example tests -> they must pass. If they failed or
        # couldn't run (e.g. the solution doesn't compile yet), block.
        if not (report.ran and report.passed):
            if report.ran:
                print("\nTests did not pass, so nothing was committed. "
                      "Fix the failing cases and run submit again.")
            else:
                print("\nThe tests could not run (does the file compile and is the "
                      "method complete?), so nothing was committed.")
            return 1
    else:
        # No runnable cases (e.g. tree/linked-list/in-place problems). These
        # can't be auto-verified, so ask the user to confirm before committing.
        print("\nThis problem has no automatic test cases to verify the solution.")
        try:
            answer = input("Submit anyway? [y/N]: ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            print("Aborted.")
            return 1

    lang = meta.get("language", "python")
    ext = SUPPORTED_LANGUAGES.get(lang, {}).get("ext", "txt")

    from . import roadmap
    topic = roadmap.topic_for_slug(meta["slug"]) or ""

    # Record BEFORE committing so the repo README includes this solve.
    progress.record_solve(
        meta["number"], meta["slug"], meta["title"], meta["difficulty"],
        topic=topic, url=meta.get("url"))
    # Spaced-repetition: schedule (or, with --rating, advance) the refresh.
    rating = getattr(args, "rating", None)
    rmeta = {**meta, "topic": topic}
    review = progress.schedule_review(meta["slug"], rmeta, rating=rating)
    print(f"Next refresh: {review['due']} ({progress.level_name(review['level'])}).")

    print("\nCommitting to your solutions repo ...")
    try:
        result = repo.commit_and_push(
            repo_url,
            path,
            number=meta["number"],
            title=meta["title"],
            difficulty=meta["difficulty"],
            slug=meta["slug"],
            language_ext=ext,
        )
    except repo.RepoError as exc:
        print(f"\nGit error: {exc}")
        return 1

    if not result.get("committed"):
        print(f"  Nothing to commit ({result.get('reason', 'no changes')}) at "
              f"{result['path']}.")
    else:
        print(f"  Committed: {result['message']}")
        print(f"  Path:      {result['path']}")
        if result.get("pushed"):
            print("  Pushed to remote.")
        else:
            print(f"  Push failed: {result.get('push_error', 'unknown error')}")
            print("  The commit is saved locally in ~/.leetcode-assistant/repo; "
                  "fix auth and `git push` there, or re-run submit.")

    # Optionally tidy up the local file now that it's safely committed.
    should_cleanup = config.get("delete_after_submit", False)
    if args.cleanup:
        should_cleanup = True
    if args.keep:
        should_cleanup = False
    if should_cleanup and result.get("committed"):
        removed = scaffold.cleanup_solution(cwd, meta)
        if removed:
            print(f"  Cleaned up locally: {', '.join(removed)}")

    print()
    print_streak_banner()
    return 0


def cmd_roadmap(args: argparse.Namespace, config: dict[str, Any]) -> int:
    preset = _resolve_preset(getattr(args, "preset", None), config)
    try:
        topics = roadmap.topics_for_preset(preset)
    except roadmap.RoadmapError as exc:
        print(f"Error: {exc}")
        return 1
    solved = progress.solved_slugs()
    grand_done = grand_total = 0
    print(f"NeetCode roadmap  -  preset: {roadmap.PRESET_NAMES[preset]}\n")
    for i, (topic, probs) in enumerate(topics, 1):
        total = len(probs)
        done = sum(1 for p in probs if p["slug"] in solved)
        grand_done += done
        grand_total += total
        bar_w = 16
        filled = int(bar_w * done / total) if total else 0
        bar = "#" * filled + "-" * (bar_w - filled)
        print(f"  {i:>2}. {topic:<26} [{bar}] {done}/{total}")
    print(f"\n  Total: {grand_done}/{grand_total} solved")
    print("\nChange preset with --preset blind75|neetcode150|all")
    print('Drill one with:  leetcode fetch --topic "two pointers"')
    return 0


def cmd_list(args: argparse.Namespace, config: dict[str, Any]) -> int:
    topic = roadmap.resolve_topic(args.topic)
    if not topic:
        print(f"Unknown topic '{args.topic}'. See `leetcode roadmap` for the list.")
        return 1
    preset = _resolve_preset(getattr(args, "preset", None), config)
    try:
        probs = roadmap.topic_problems(topic, preset)
    except roadmap.RoadmapError as exc:
        print(f"Error: {exc}")
        return 1
    if args.difficulty and args.difficulty != "any":
        probs = [p for p in probs if p["difficulty"] == args.difficulty]
    solved = progress.solved_slugs()
    if args.unsolved:
        probs = [p for p in probs if p["slug"] not in solved]
    done = sum(1 for p in probs if p["slug"] in solved)
    pre = ", ".join(roadmap.PREREQS.get(topic, [])) or "none (start here)"
    print(f"{topic}  ({roadmap.PRESET_NAMES[preset]})  -  prereqs: {pre}")
    print(f"{len(probs)} problems ({done} solved)\n")
    for p in probs:
        mark = "[x]" if p["slug"] in solved else "[ ]"
        print(f"  {mark} {p['number']:>4}  {p['difficulty']:<6}  {p['title']}")
    return 0


def cmd_clean(args: argparse.Namespace, config: dict[str, Any]) -> int:
    target = Path(args.dir) if args.dir else Path.cwd()
    if not target.is_dir():
        print(f"Not a folder: {target}")
        return 1
    removed = scaffold.clean_workdir(target)
    if removed:
        print(f"Removed {len(removed)} file(s): {', '.join(removed)}")
    else:
        print("Nothing to clean (no scaffolded files found).")
    return 0


def cmd_config(args: argparse.Namespace, config: dict[str, Any]) -> int:
    if args.show:
        import json
        print(json.dumps(config, indent=2))
        print(f"\n(stored at {cfg.CONFIG_PATH})")
        return 0
    cfg.first_run_setup()
    return 0


def cmd_stats(args: argparse.Namespace, config: dict[str, Any]) -> int:
    s = progress.stats()
    print(f"Total solved: {s['total']}")
    print(f"Current streak: {s['streak']} day(s)   (longest: {s['longest_streak']})")
    if s["by_difficulty"]:
        print("By difficulty:")
        for diff in ("easy", "medium", "hard"):
            if diff in s["by_difficulty"]:
                print(f"  {diff:7}: {s['by_difficulty'][diff]}")
    if s["last"]:
        last = s["last"]
        print(f"Last solved: {last['number']}. {last['title']} on {last['date']}")
    return 0


def cmd_doctor(args: argparse.Namespace, config: dict[str, Any]) -> int:
    from . import doctor
    return doctor.run()


def cmd_review(args: argparse.Namespace, config: dict[str, Any]) -> int:
    due = progress.due_reviews()
    upcoming = progress.upcoming_reviews()
    if not due and not upcoming:
        print("No problems are tracked for review yet -- solve something first.")
        return 0
    if due:
        print(f"Due for a blind refresh now -- {len(due)} problem(s):\n")
        for r in due:
            od = "today" if r["days_overdue"] == 0 else f"+{r['days_overdue']}d overdue"
            print(f"  {r['number']:>4}  {r['difficulty']:<6}  {r['title']:<40}  "
                  f"[{progress.level_name(r['level'])}]  ({od})")
        print("\nIn the GUI: the Refresh tab queues these. CLI: re-solve blind with")
        print("  leetcode fetch <slug>   then   leetcode submit --rating aced|good|hard")
    else:
        nxt = upcoming[0]
        print(f"Nothing due right now. Next up: {nxt['title']} in {nxt['days_until']} day(s).")
    return 0


# --------------------------------------------------------------------------- #
# argument parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="leetcode",
        description="A daily LeetCode workflow: fetch, test, and submit problems.",
    )
    p.add_argument("--version", action="version", version=f"leetcode-assistant {__version__}")
    sub = p.add_subparsers(dest="command")

    pf = sub.add_parser("fetch", help="fetch a problem and scaffold a solution file")
    pf.add_argument("problem", nargs="?", help="problem number or title-slug (random if omitted)")
    pf.add_argument("-d", "--difficulty", choices=VALID_DIFFICULTIES + ("any",),
                    help="filter difficulty for a random fetch")
    pf.add_argument("-l", "--lang", help="language: python or javascript")
    pf.add_argument("-t", "--topic",
                    help="roadmap topic, e.g. \"two pointers\" or \"1-d dp\"")
    pf.add_argument("-p", "--preset", help="blind75 | neetcode150 | all")
    pf.set_defaults(func=cmd_fetch)

    pt = sub.add_parser("test", help="run example test cases against your solution")
    pt.add_argument("file", nargs="?", help="solution file (defaults to last fetched)")
    pt.set_defaults(func=cmd_test)

    ps = sub.add_parser("submit", help="test, then commit + push a passing solution")
    ps.add_argument("file", nargs="?", help="solution file (defaults to last fetched)")
    ps.add_argument("--cleanup", action="store_true",
                    help="delete the local file after a successful commit")
    ps.add_argument("--keep", action="store_true",
                    help="keep the local file even if delete_after_submit is on")
    ps.add_argument("--rating", choices=("aced", "good", "hard"),
                    help="spaced-repetition rating for this attempt "
                         "(aced=level up, good=stay, hard=reset)")
    ps.set_defaults(func=cmd_submit)

    pcl = sub.add_parser("clean", help="remove scaffolded files from a folder")
    pcl.add_argument("dir", nargs="?", help="folder to clean (default: current)")
    pcl.set_defaults(func=cmd_clean)

    pc = sub.add_parser("config", help="set up or view configuration")
    pc.add_argument("--show", action="store_true", help="print current config and exit")
    pc.set_defaults(func=cmd_config)

    pst = sub.add_parser("stats", help="show solve stats and streak")
    pst.set_defaults(func=cmd_stats)

    pdoc = sub.add_parser("doctor", help="check your setup (python, git, auth, network)")
    pdoc.set_defaults(func=cmd_doctor)

    prev = sub.add_parser("review", help="list problems due for spaced-repetition review")
    prev.add_argument("-d", "--days", type=int, default=None,
                      help="minimum age in days (default 7)")
    prev.set_defaults(func=cmd_review)

    pto = sub.add_parser("roadmap", help="show the NeetCode roadmap and your progress")
    pto.add_argument("-p", "--preset", help="blind75 | neetcode150 | all")
    pto.set_defaults(func=cmd_roadmap)

    pls = sub.add_parser("list", help="list the problems in a roadmap topic")
    pls.add_argument("topic", help="topic, e.g. \"two pointers\" or \"1-d dp\"")
    pls.add_argument("-d", "--difficulty", choices=VALID_DIFFICULTIES + ("any",),
                     help="filter by difficulty")
    pls.add_argument("-p", "--preset", help="blind75 | neetcode150 | all")
    pls.add_argument("--unsolved", action="store_true", help="only show unsolved problems")
    pls.set_defaults(func=cmd_list)

    pg = sub.add_parser("gui", help="launch the point-and-click GUI")
    pg.set_defaults(func=cmd_gui)

    return p


def cmd_gui(args: argparse.Namespace, config: dict[str, Any]) -> int:
    try:
        from .gui import launch
    except ImportError as exc:
        print(f"Could not start the GUI (is Tkinter installed?): {exc}")
        return 1
    return launch()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        parser.print_help()
        return 0

    # `config` (setup) and `gui` manage configuration themselves, so they must
    # not trigger the interactive text setup.
    if ((args.command == "config" and not args.show)
            or args.command in ("gui", "doctor", "review")):
        return args.func(args, cfg.load_config() or dict(cfg.DEFAULTS))

    config = cfg.get_config_or_setup()

    # Streak banner on every real run.
    if args.command in ("fetch", "test", "submit"):
        print_streak_banner()
        print()

    return args.func(args, config)


if __name__ == "__main__":
    sys.exit(main())
