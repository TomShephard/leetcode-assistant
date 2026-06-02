# Changelog

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
