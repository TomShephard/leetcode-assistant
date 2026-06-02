# Changelog

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
