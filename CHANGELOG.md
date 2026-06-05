# Changelog

## v1.10.5
- Fixed duplicate rows in the solutions-repo **Log** (and double-counting in the
  badges/Stats) when the same problem was solved on more than one day. The Log
  now shows **one row per problem** -- the most recent solve -- and "Solved" /
  per-difficulty / optimal counts are per unique problem. The full per-day solve
  history is still kept for the streak heatmap.

## v1.10.4
- Fixed the NeetCode **250** preset coming up empty in the Testing tab on some
  packaged builds. The bundled dataset is the only source carrying the 250
  flags; the loader now finds it via the PyInstaller bundle dir (`sys._MEIPASS`)
  first, so the EXE can never silently fall back to the network dataset (which
  has no 250 data). Added a test locking 150 as a per-topic subset of 250.

## v1.10.3
- Solve editor: the import preamble is now a **collapsible block**, folded by
  default so the boilerplate imports stay out of the way. A small triangle in
  the line-number gutter toggles it -- click to expand or re-collapse. The full
  imports are always saved and submitted regardless of fold state.

## v1.10.2
- **Order-insensitive test matching.** Many LeetCode problems accept the answer
  in any order (Group Anagrams, Subsets, Permutations, ...). The local runner
  used to only ignore order at the top level, so a correct Group Anagrams answer
  with reordered groups -- or reordered items within a group -- was wrongly
  rejected. Comparison is now recursive/canonical, matching LeetCode's judge,
  while genuinely different answers still fail.
- **Scaffold pre-imports the common stdlib helpers** (`defaultdict`, `Counter`,
  `deque`, `OrderedDict`, `heapq`, `bisect`, `math`, `itertools`, `functools`),
  mirroring LeetCode's environment -- so a solution using `defaultdict` without
  an explicit import runs locally instead of raising `NameError`.

## v1.10.1
- Solve tab: the sash above the **Tests / output** console is now wider, raised,
  and has a visible drag handle, so it's obvious you can drag the console taller
  or shorter. The editor can also shrink further, letting the console grow much
  larger. (The resizable console first shipped in v1.8.1 -- this just makes it
  discoverable.)

## v1.10.0
- **Self-reported approach.** Submitting now asks a quick "how did you solve
  this?" -- Optimal / Brute-force / Skip (Enter accepts Optimal). This replaces
  the removed auto-probe: it's always accurate, and it lets you deliberately
  lock in a brute-force attempt before redoing it efficiently. The **Approach**
  column, optimal badge/summary, and Stats ratio are back, now driven by your
  own marks. CLI: `leetcode submit --approach optimal|brute|skip`.
- The approach prompt is skipped during a topic-test gauntlet to keep it
  flowing.

## v1.9.0
- **Removed the complexity / "optimal vs brute-force" check.** Empirically
  timing a solution is unreliable (it only works for some Python problems and
  can be fooled -- e.g. a brute-force duplicate finder that returns early on
  random input looked O(1)), and a wrong verdict baked into your permanent
  solutions README is worse than none. The Approach column, the "solved
  optimally" badge/summary, and the Stats optimal ratio are gone; submitting is
  now faster (no probe step).
- **Smarter refresh scheduling.** Re-solving a problem before its review is due
  (e.g. a brute-force warm-up immediately followed by the optimal version) no
  longer advances the spaced-repetition clock -- that counted as a retest and
  could jump a brand-new problem straight to a 30-day interval. The confidence
  prompt and level-up now only happen on a genuine *due* retest; earlier
  re-solves just count as practice and leave the schedule untouched.

## v1.8.2
- Editor: **Ctrl+Backspace** deletes the previous word and **Ctrl+Delete** the
  next one, one token at a time (word / whitespace / symbol run), like a real
  IDE; at a line edge it joins the adjacent line.
- Complexity check: the probe now feeds **distinct** values to the solution.
  Random small-range inputs were full of duplicates, so a brute-force
  duplicate finder (e.g. an O(n^2) Contains Duplicate) would hit a match on the
  first pair and look O(1) -> wrongly "optimal". Distinct inputs remove that
  accidental early-exit, so it measures the genuine worst case.

## v1.8.1
- Solve tab: the **Tests / output** console now lives in a resizable pane.
  Drag the sash between the editor and the console to grow the output (handy
  for long failure traces) or shrink it to give your code more room.

## v1.8.0
- **Testing tab (topic gauntlets):** test a whole topic back-to-back. A pass
  means solving every problem in the topic at the selected question set
  (Blind 75 / NeetCode 150 / 250 / All). Mark each problem clean, unsure, or
  used-help as you go -- the same prompt doubles as the refresh rating so you
  aren't asked twice.
- Larger question sets are harder, so a pass records the set used and a pass at
  a higher set outranks a lower one (and never gets downgraded). Passes don't
  expire; the completion date/time and the full per-problem log are kept.
- The solutions-repo README is restructured: **Log -> Review schedule ->
  Topic tests**. Only passed topics are listed (so unattempted ones don't flood
  it), each with its question set, result, problem count, completion time, and a
  collapsible per-topic question log.

## v1.7.0
- **Refresh tab (spaced repetition):** every solved problem is scheduled for a
  blind retest on an expanding ladder (Learning 7d -> Familiar 30d -> Confident
  90d -> Mastered 365d). Due problems queue up; "Start blind retest" fetches a
  fresh copy, and after passing you rate the attempt (Aced -> level up,
  Got it -> stay, Needed help -> back to Learning).
- The solutions-repo README now includes a **Review schedule** section.
- `leetcode review` shows what's due; `leetcode submit --rating` records a
  rating from the CLI. Intervals are configurable (`review_intervals`).

## v1.6.0
- Editor feels like a real IDE: tab-aware backspace (delete a whole indent
  level at once), auto-closing brackets/quotes with type-over, and a
  scroll-margin so there's always room below the cursor.
- The Solve editor now shows just your code -- the problem text lives only in
  the left pane -- giving more space to write (the description is re-attached
  to the saved file automatically).

## v1.5.0
- `leetcode doctor`: preflight checks (Python, git, GitHub auth, network, config).
- `leetcode review`: spaced-repetition queue of problems due for another pass.
- **Stats** tab: GitHub-style activity heatmap, current/longest streak,
  per-difficulty counts, optimal ratio.
- Complexity check now also estimates **space** complexity; broader input coverage.
- Per-problem solve timer (shown in the solutions-repo README).
- Editor: find (`Ctrl+F`), font zoom (`Ctrl +/-`); global shortcuts
  (`Ctrl+S` save, `Ctrl+Enter` test, `Ctrl+Shift+Enter` submit); fetching a
  problem opens it in the Solve tab; the GUI remembers its window size.
- Unit-test suite and GitHub Actions for tests + automatic release builds.

## v1.4.0
- Renamed to **Leetcode Assistant** (package, app, CLI, data dir, EXE).
- In-app code editor (Solve tab) merged into the main app.
- Fixed the Windows title-bar icon (Win32 `WM_SETICON` + embedded icon).

## v1.3.0
- Complexity check on submit: flags brute-force vs optimal solutions.
- Self-updating `README.md` in the solutions repo on every submission.
- No more console-window flashing in the packaged app.

## v1.2.x
- NeetCode roadmap with Blind 75 / 150 / 250 / All presets and prerequisites.
- Browse all of LeetCode by topic.
- Strict test gate: submit only commits when example tests pass.

## v1.0.x
- Fetch / test / submit workflow, scaffolding, streak tracking, the GUI,
  and the standalone Windows EXE.
