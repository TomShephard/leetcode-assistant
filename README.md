# leetcode-cli

A small command-line tool for a daily LeetCode habit. It fetches a problem,
scaffolds a solution file with the description as a header comment, runs your
solution against the problem's own example test cases, and -- when it passes --
commits and pushes it to your private GitHub solutions repo. It also tracks a
local solve streak.

```
leetcode fetch      grab a (random or specific) problem and scaffold a file
leetcode test       run the example test cases against your solution
leetcode submit     test, then commit + push a passing solution
leetcode config     set up or view configuration
leetcode stats      show your solve stats and streak
leetcode roadmap    show the NeetCode roadmap and your progress
leetcode list TOPIC list the problems in a roadmap topic
leetcode clean      remove scaffolded files from a folder
leetcode gui        launch the point-and-click GUI
```

## NeetCode roadmap (structured course)

Work through interview prep as a course instead of random problems. The roadmap
uses NeetCode's curated lists and topic order (Arrays & Hashing -> Two Pointers
/ Stack -> ... -> DP), with prerequisites between topics. Four presets widen
the selection:

- **Blind 75** - the classic 75-problem starter list
- **NeetCode 150** - the default (28 easy / 101 medium / 21 hard)
- **NeetCode 250** - the extended 250-problem list
- **NeetCode (All)** - every roadmap problem (~940)

Your solved count per topic is tracked automatically by cross-referencing your
solve log, and updates as you submit.

```
leetcode roadmap                          # progress per topic at your preset
leetcode roadmap --preset blind75
leetcode list "two pointers"              # problems in a topic, [x] = solved
leetcode list "1-d dp" --preset neetcode250 --unsolved
leetcode fetch --topic "two pointers"     # scaffold a random unsolved one
leetcode fetch --topic trees -p neetcode150 -d medium
```

Presets accept `blind75`, `neetcode150`, `neetcode250`, or `all`.

In the **GUI**, the "NeetCode Roadmap" tab shows the topics in roadmap order
with live done/total counts and a list selector. Click a topic to see its
problems (colour-coded by difficulty, solved ones highlighted, prerequisites
shown), filter by difficulty or unsolved-only, and double-click (or "Fetch
selected") to scaffold it. Switching list re-scopes everything; counts update
as you submit.

### Browse all of LeetCode by topic

Not everything is on the NeetCode roadmap. Pick **"All LeetCode (by topic)"**
from the same list selector to browse LeetCode's full topic taxonomy (arrays,
strings, trees, graphs, DP, and ~20 more) with every problem in each category,
not just the curated ones. From the CLI, the topic commands also accept any
LeetCode topic.

The roadmap dataset ships with the tool (`leetcode_cli/neetcode_roadmap.json`),
so it works offline and instantly. It was extracted from neetcode.io (which
carries the blind75 / neetcode150 / neetcode250 flags); refresh it any time with
`py tools/refresh_neetcode_data.py`.

## Standalone EXE (no Python needed)

Build a double-clickable Windows executable of the GUI:

```
build-exe.cmd
```

This installs PyInstaller (if needed) and produces `dist\LeetCodeCLI.exe`. You
can move that EXE anywhere (desktop, Start menu) and run it without Python
installed. Note: `git` (and optionally `gh`) still need to be installed for the
submit step, and Node for running JavaScript solutions.

## Keeping your folders tidy

Solution files can pile up. Two ways to manage that:

- **Auto-delete after submit:** tick "Delete local file after a successful
  submit" in the GUI (or set `"delete_after_submit": true` in the config, or run
  `leetcode submit --cleanup`). Once a solution is committed to your repo, the
  local file and its scratch metadata are removed. The streak log is separate,
  so your streak is unaffected.
- **Clean a folder on demand:** the GUI's "Clean folder" button (or
  `leetcode clean [folder]`) removes every file this tool scaffolded in that
  folder. Already-committed solutions remain safe in your repo.

The GUI remembers the last working folder you used (saved as `"workdir"` in the
config), so fetched files keep landing in the same place.

## GUI (no commands)

Prefer buttons over a terminal? Run:

```
py -m leetcode_cli gui
```

or just double-click `leetcode-gui.cmd` in this folder. The window lets you:

- pick the working folder where solution files are saved,
- set/save your repo URL, language, and difficulty,
- Fetch a problem (random or by number/slug),
- Open the scaffolded file in your editor, edit it, then
- Run tests (pass/fail shown in colour) and Submit (commit + push),
- see your streak update live.

Each section in the Workflow tab is collapsible -- click its header to fold it
away and keep the window tidy. The Output box expands to fill the freed space.

## Run it from PyCharm

This project ships PyCharm run configurations (in `.idea/runConfigurations`).
After opening the project, pick one from the dropdown next to the green Run
button and click Run:

- **LeetCode GUI** - opens the GUI (recommended).
- **LeetCode Fetch (random)** / **Test** / **Submit** - run those commands with
  the working directory set to `practice/`.

First time only: if PyCharm shows "No interpreter", open the config (Run ->
Edit Configurations) and pick your Python 3 interpreter, then Run. The configs
already add the project root to the path, so imports just work.

## Requirements

- Python 3.9+ (no third-party packages; standard library only)
- `git` (used for committing/pushing). The `gh` CLI is used automatically if
  present, otherwise it falls back to raw `git`.
- Node.js is only needed if you want to *run* JavaScript solutions locally.

## Install / run

You don't have to install anything -- the repo ships with launcher shims.

**Windows (PowerShell or cmd):** add this folder to your `PATH`, then:

```
leetcode fetch
```

(`leetcode.cmd` points Python at this folder for you.)

**Unix / git-bash:** make the shim executable and put it on your `PATH`:

```
chmod +x ./leetcode
./leetcode fetch
```

**Or install it as a real command** with pip (creates a `leetcode` entry point):

```
py -m pip install --user -e .
leetcode fetch
```

## First run

The first time you run any command, you'll be asked for:

1. Your private GitHub repo URL (HTTPS or SSH) for storing solutions
2. Preferred language (`python` or `javascript`)
3. Default difficulty filter (`easy` / `medium` / `hard` / `any`)

These are saved to `~/.leetcode-cli/config.json`. Re-run setup any time with
`leetcode config`, or view current settings with `leetcode config --show`.

## Typical day

```
# 1. Get a problem (random easy, or a specific one)
leetcode fetch -d easy
leetcode fetch two-sum          # by slug
leetcode fetch 1                # by number

# -> writes ./0001-two-sum.py with the description + starter code,
#    and records the example test cases under ./.leetcode/

# 2. Solve it in the scaffolded file, then check your work
leetcode test

# 3. When it passes, ship it
leetcode submit
```

`submit` runs the tests first. If they pass, it commits the file into your repo
using a consistent layout and message:

```
solutions/{difficulty}/{number}-{slug}.{ext}
commit: Solve {number}: {Title} ({Difficulty})
```

**Submit only commits when the tests pass.** If any example test fails, submit
refuses and commits nothing -- there is no override; fix the solution and try
again. If a problem has no auto-extractable example cases (e.g. tree or
linked-list inputs that the tool can't run), submit can't verify it, so it asks
you to confirm before committing.

`test` and `submit` operate on the last problem you fetched in the current
directory by default; pass a filename to target a specific one
(`leetcode test 0001-two-sum.py`).

## How it works

- **Problem data** comes from LeetCode's public endpoints by default
  (`/api/problems/all/` for the index and the GraphQL API for content). This is
  what gives you real descriptions, official starter code, and the example test
  cases needed to actually run `leetcode test`.
- **GitHub dataset (optional):** set `"source": "github"` and a
  `"github_dataset_url"` in the config to pull from a JSON dataset hosted on
  GitHub instead. Note that most such datasets don't ship runnable test cases,
  so `test` will have nothing to run for those.
- **Streak** is computed from `~/.leetcode-cli/progress.json`, which logs every
  solved problem with its date, number, name, and difficulty. The streak counts
  consecutive days (ending today or yesterday) with at least one solve.

## Notes & limitations

- The local test runner handles the common "call a method with JSON-style
  arguments and compare the return value" shape, with order-insensitive list
  comparison and a small float tolerance. Problems that mutate inputs in place,
  use custom classes (`ListNode`, `TreeNode`), or accept multiple valid answers
  won't verify automatically -- submit treats these as "no test cases" and asks
  you to confirm before committing.
- Premium/locked problems can't be fetched (no public content).
- Config, progress, and the local clone of your repo all live under
  `~/.leetcode-cli/`.
