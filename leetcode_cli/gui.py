"""A simple Tkinter GUI for leetcode-cli.

Wraps the same library functions the command-line uses (data / scaffold /
runner / repo / progress) behind buttons, so you can fetch, test, and submit
without typing commands. Network, test, and git work runs on background
threads to keep the window responsive.

Launch with:  py -m leetcode_cli gui
"""

from __future__ import annotations

import glob
import os
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

from . import config as cfg
from . import data, progress, repo, runner, scaffold
from .config import SUPPORTED_LANGUAGES, VALID_DIFFICULTIES

LANG_CHOICES = ["python", "javascript"]
DIFF_CHOICES = list(VALID_DIFFICULTIES) + ["any"]

# Colour palette
BG = "#eef1f6"
CARD = "#ffffff"
BORDER = "#d7dce5"
HEADER = "#10243e"
ACCENT = "#2f6feb"
ACCENT_ACTIVE = "#1f5fd0"
TEXT = "#1f2329"
MUTED = "#6b7280"
CONSOLE_BG = "#0f172a"
CONSOLE_FG = "#e2e8f0"


def find_pycharm() -> str | None:
    """Locate a PyCharm launcher, or return None if not found."""
    for name in ("pycharm64.exe", "pycharm.exe", "pycharm", "charm", "pycharm.cmd"):
        found = shutil.which(name)
        if found:
            return found
    patterns = [
        r"C:\Program Files\JetBrains\PyCharm*\bin\pycharm64.exe",
        r"C:\Program Files (x86)\JetBrains\PyCharm*\bin\pycharm64.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\PyCharm*\bin\pycharm64.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\JetBrains\Toolbox\apps\PyCharm*\**\bin\pycharm64.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\JetBrains\Toolbox\scripts\pycharm*.cmd"),
        os.path.expandvars(r"%APPDATA%\JetBrains\Toolbox\scripts\pycharm*.cmd"),
    ]
    for pat in patterns:
        matches = glob.glob(pat, recursive=True)
        if matches:
            return sorted(matches)[-1]
    return None


def open_in_editor(path: Path, editor: str = "") -> str:
    """Open `path`. Prefer an explicit editor command, then PyCharm, then the
    OS default. Returns a short description of what was used."""
    candidates: list[tuple[str, list[str]]] = []
    if editor.strip():
        candidates.append((editor, [editor, str(path)]))
    pycharm = find_pycharm()
    if pycharm:
        candidates.append(("PyCharm", [pycharm, str(path)]))
    for label, cmd in candidates:
        try:
            subprocess.Popen(cmd)
            return label
        except OSError:
            continue
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
        return "default app"
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.run([opener, str(path)])
    return "default app"


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("leetcode-cli")
        root.geometry("880x720")
        root.minsize(760, 600)
        root.configure(bg=BG)

        self.config = cfg.load_config() or dict(cfg.DEFAULTS)
        self._busy = False
        self._ui_queue: "queue.Queue[Callable[[], None]]" = queue.Queue()

        self.workdir = tk.StringVar(value=self._default_workdir())
        self.problem_var = tk.StringVar()
        self.fetch_diff = tk.StringVar(value=self.config.get("default_difficulty", "any"))
        self.lang_var = tk.StringVar(value=self.config.get("language", "python"))
        self.repo_var = tk.StringVar(value=self.config.get("repo_url", ""))
        self.cfg_diff = tk.StringVar(value=self.config.get("default_difficulty", "any"))
        self.editor_var = tk.StringVar(value=self.config.get("editor", ""))
        self.delete_after = tk.BooleanVar(value=bool(self.config.get("delete_after_submit", False)))
        self.target_var = tk.StringVar(value="(none yet)")
        self.streak_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready.")

        self._setup_style()
        self._build_ui()
        self.refresh_streak()
        self.refresh_target()
        self._pump_queue()

    # ------------------------------------------------------------------ #
    # defaults
    # ------------------------------------------------------------------ #
    def _default_workdir(self) -> str:
        saved = self.config.get("workdir", "")
        if saved and Path(saved).is_dir():
            return saved
        practice = Path.cwd() / "practice"
        if practice.is_dir():
            return str(practice)
        return str(Path.cwd())

    # ------------------------------------------------------------------ #
    # styling
    # ------------------------------------------------------------------ #
    def _setup_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        base_font = ("Segoe UI", 10)
        style.configure(".", font=base_font, background=BG, foreground=TEXT)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Card.TLabel", background=CARD, foreground=TEXT)
        style.configure("Muted.TLabel", background=CARD, foreground=MUTED)
        style.configure("Target.TLabel", background=CARD, foreground=ACCENT,
                        font=("Segoe UI", 10, "bold"))

        style.configure("Header.TFrame", background=HEADER)
        style.configure("HeaderTitle.TLabel", background=HEADER, foreground="#ffffff",
                        font=("Segoe UI Semibold", 16))
        style.configure("HeaderSub.TLabel", background=HEADER, foreground="#9fb3c8",
                        font=("Segoe UI", 9))
        style.configure("Streak.TLabel", background=HEADER, foreground="#7ee2b8",
                        font=("Segoe UI Semibold", 11))

        style.configure("Card.TLabelframe", background=CARD, bordercolor=BORDER,
                        relief="solid", borderwidth=1)
        style.configure("Card.TLabelframe.Label", background=CARD, foreground=ACCENT,
                        font=("Segoe UI Semibold", 10))

        style.configure("TButton", padding=(10, 6))
        style.configure("Accent.TButton", padding=(14, 7), foreground="#ffffff",
                        background=ACCENT, borderwidth=0,
                        font=("Segoe UI Semibold", 10))
        style.map("Accent.TButton",
                  background=[("active", ACCENT_ACTIVE), ("disabled", "#9db8e8")],
                  foreground=[("disabled", "#eef1f6")])
        style.configure("TCheckbutton", background=CARD)
        style.configure("Status.TLabel", background="#dfe4ec", foreground=MUTED,
                        padding=(8, 4))

    def _card(self, parent: tk.Misc, title: str) -> ttk.Frame:
        lf = ttk.Labelframe(parent, text=title, style="Card.TLabelframe")
        lf.pack(fill="x", padx=14, pady=7)
        inner = ttk.Frame(lf, style="Card.TFrame")
        inner.pack(fill="x", padx=10, pady=8)
        return inner

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        # Header bar
        header = ttk.Frame(self.root, style="Header.TFrame")
        header.pack(fill="x")
        htext = ttk.Frame(header, style="Header.TFrame")
        htext.pack(side="left", padx=18, pady=12)
        ttk.Label(htext, text="LeetCode Daily", style="HeaderTitle.TLabel").pack(anchor="w")
        ttk.Label(htext, text="fetch  -  solve  -  test  -  submit",
                  style="HeaderSub.TLabel").pack(anchor="w")
        ttk.Label(header, textvariable=self.streak_var,
                  style="Streak.TLabel").pack(side="right", padx=18)

        # Working folder
        wf = self._card(self.root, "Working folder (solutions are saved here)")
        ttk.Entry(wf, textvariable=self.workdir).pack(side="left", fill="x", expand=True)
        ttk.Button(wf, text="Change...", command=self.choose_workdir).pack(side="left", padx=(8, 0))

        # Config
        cf = self._card(self.root, "Configuration")
        cf.columnconfigure(1, weight=1)
        ttk.Label(cf, text="Private repo URL:", style="Card.TLabel").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(cf, textvariable=self.repo_var).grid(row=0, column=1, columnspan=3, sticky="we", padx=6, pady=3)
        ttk.Label(cf, text="Language:", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Combobox(cf, textvariable=self.lang_var, values=LANG_CHOICES, width=14,
                     state="readonly").grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(cf, text="Default difficulty:", style="Card.TLabel").grid(row=1, column=2, sticky="e")
        ttk.Combobox(cf, textvariable=self.cfg_diff, values=DIFF_CHOICES, width=10,
                     state="readonly").grid(row=1, column=3, sticky="w", padx=6)
        ttk.Label(cf, text="Editor (blank = auto-detect PyCharm):", style="Card.TLabel").grid(
            row=2, column=0, sticky="w", pady=3)
        ttk.Entry(cf, textvariable=self.editor_var).grid(row=2, column=1, columnspan=2, sticky="we", padx=6, pady=3)
        ttk.Button(cf, text="Browse...", command=self._browse_editor).grid(row=2, column=3, sticky="w", padx=6)
        ttk.Checkbutton(cf, text="Delete local file after a successful submit",
                        variable=self.delete_after, command=self._toggle_delete,
                        style="TCheckbutton").grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Button(cf, text="Save config", command=self.save_config).grid(
            row=3, column=3, sticky="e", pady=(6, 0))

        # Fetch
        ff = self._card(self.root, "Fetch a problem")
        ttk.Label(ff, text="Number or slug (blank = random):", style="Card.TLabel").pack(side="left")
        ttk.Entry(ff, textvariable=self.problem_var, width=22).pack(side="left", padx=6)
        ttk.Label(ff, text="Difficulty:", style="Card.TLabel").pack(side="left")
        ttk.Combobox(ff, textvariable=self.fetch_diff, values=DIFF_CHOICES, width=8,
                     state="readonly").pack(side="left", padx=6)
        self.fetch_btn = ttk.Button(ff, text="Fetch", style="Accent.TButton", command=self.do_fetch)
        self.fetch_btn.pack(side="left", padx=6)

        # Current target + actions
        af = self._card(self.root, "Current solution")
        trow = ttk.Frame(af, style="Card.TFrame")
        trow.pack(fill="x")
        ttk.Label(trow, text="File:", style="Card.TLabel").pack(side="left")
        ttk.Label(trow, textvariable=self.target_var, style="Target.TLabel").pack(side="left", padx=6)
        ttk.Button(trow, text="Choose file...", command=self.choose_file).pack(side="right", padx=4)
        ttk.Button(trow, text="Open in editor", command=self.open_file).pack(side="right", padx=4)
        brow = ttk.Frame(af, style="Card.TFrame")
        brow.pack(fill="x", pady=(8, 0))
        self.test_btn = ttk.Button(brow, text="Run tests", style="Accent.TButton", command=self.do_test)
        self.test_btn.pack(side="left", padx=4)
        self.submit_btn = ttk.Button(brow, text="Submit (commit + push)", style="Accent.TButton",
                                     command=self.do_submit)
        self.submit_btn.pack(side="left", padx=4)
        ttk.Button(brow, text="Clean folder", command=self.do_clean).pack(side="right", padx=4)

        # Output log
        of = ttk.Labelframe(self.root, text="Output", style="Card.TLabelframe")
        of.pack(fill="both", expand=True, padx=14, pady=7)
        mono = tkfont.Font(family="Consolas", size=10)
        self.log_widget = tk.Text(of, wrap="word", height=12, state="disabled",
                                  background=CONSOLE_BG, foreground=CONSOLE_FG,
                                  insertbackground=CONSOLE_FG, relief="flat",
                                  font=mono, padx=10, pady=8)
        self.log_widget.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(of, command=self.log_widget.yview)
        sb.pack(side="right", fill="y")
        self.log_widget.configure(yscrollcommand=sb.set)
        self.log_widget.tag_configure("pass", foreground="#34d399")
        self.log_widget.tag_configure("fail", foreground="#f87171")
        self.log_widget.tag_configure("info", foreground="#60a5fa")
        self.log_widget.tag_configure("muted", foreground="#94a3b8")

        ttk.Label(self.root, textvariable=self.status_var, style="Status.TLabel",
                  anchor="w").pack(fill="x", side="bottom")

    # ------------------------------------------------------------------ #
    # threading helpers
    # ------------------------------------------------------------------ #
    def _pump_queue(self) -> None:
        try:
            while True:
                self._ui_queue.get_nowait()()
        except queue.Empty:
            pass
        self.root.after(60, self._pump_queue)

    def _post(self, fn: Callable[[], None]) -> None:
        self._ui_queue.put(fn)

    def run_bg(self, work: Callable[[], Any],
               on_done: Callable[[Any, Exception | None], None]) -> None:
        if self._busy:
            self.log("Busy with another action; please wait.\n", "muted")
            return
        self._set_busy(True)

        def runner_thread() -> None:
            result: Any = None
            err: Exception | None = None
            try:
                result = work()
            except Exception as exc:  # noqa: BLE001
                err = exc
            self._post(lambda: self._finish(result, err, on_done))

        threading.Thread(target=runner_thread, daemon=True).start()

    def _finish(self, result: Any, err: Exception | None,
                on_done: Callable[[Any, Exception | None], None]) -> None:
        self._set_busy(False)
        on_done(result, err)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        for btn in (self.fetch_btn, self.test_btn, self.submit_btn):
            btn.configure(state=state)
        self.status_var.set("Working..." if busy else "Ready.")

    # ------------------------------------------------------------------ #
    # logging
    # ------------------------------------------------------------------ #
    def log(self, text: str, tag: str | None = None) -> None:
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", text, tag or ())
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    def log_section(self, title: str) -> None:
        self.log(f"\n=== {title} ===\n", "info")

    # ------------------------------------------------------------------ #
    # config / streak / target
    # ------------------------------------------------------------------ #
    def _toggle_delete(self) -> None:
        self.config["delete_after_submit"] = bool(self.delete_after.get())
        cfg.save_config(self.config)

    def save_config(self) -> None:
        self.config["repo_url"] = self.repo_var.get().strip()
        self.config["language"] = self.lang_var.get().strip().lower()
        self.config["default_difficulty"] = self.cfg_diff.get().strip().lower()
        self.config["editor"] = self.editor_var.get().strip()
        self.config["delete_after_submit"] = bool(self.delete_after.get())
        self.config["workdir"] = self.workdir.get().strip()
        cfg.save_config(self.config)
        self.log(f"Config saved to {cfg.CONFIG_PATH}\n", "info")
        self.status_var.set("Config saved.")

    def refresh_streak(self) -> None:
        s = progress.stats()
        unit = "day" if s["streak"] == 1 else "days"
        self.streak_var.set(f"Streak: {s['streak']} {unit}   |   Solved: {s['total']}")

    def _workdir_path(self) -> Path:
        return Path(self.workdir.get())

    def refresh_target(self) -> None:
        meta = scaffold.load_last_meta(self._workdir_path())
        if meta:
            self.target_var.set(f"{meta['filename']}  ({meta['number']}. {meta['title']})")
        else:
            self.target_var.set("(none yet -- fetch a problem)")

    def resolve_target(self) -> tuple[Path | None, dict[str, Any] | None]:
        workdir = self._workdir_path()
        meta = scaffold.load_last_meta(workdir)
        if not meta:
            return None, None
        path = workdir / meta["filename"]
        if not path.exists():
            return None, meta
        return path, meta

    def _persist_workdir(self) -> None:
        self.config["workdir"] = self.workdir.get().strip()
        cfg.save_config(self.config)

    # ------------------------------------------------------------------ #
    # actions
    # ------------------------------------------------------------------ #
    def _browse_editor(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Choose editor executable",
            filetypes=[("Programs", "*.exe *.cmd *.bat"), ("All files", "*.*")],
        )
        if chosen:
            self.editor_var.set(chosen)

    def choose_workdir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.workdir.get())
        if chosen:
            self.workdir.set(chosen)
            self._persist_workdir()
            self.refresh_target()
            self.log(f"Working folder: {chosen}\n", "muted")

    def choose_file(self) -> None:
        chosen = filedialog.askopenfilename(
            initialdir=self.workdir.get(),
            filetypes=[("Solution files", "*.py *.js"), ("All files", "*.*")],
        )
        if not chosen:
            return
        path = Path(chosen)
        self.workdir.set(str(path.parent))
        self._persist_workdir()
        meta = scaffold.find_meta_for_file(path.parent, path)
        if meta is None:
            messagebox.showwarning(
                "No metadata",
                "No saved test metadata for this file. Fetch the problem with "
                "this tool so its example cases are recorded.",
            )
            return
        try:
            (path.parent / cfg.WORKDIR_META / "last.json").write_text(
                f'{{"slug": "{meta["slug"]}"}}', encoding="utf-8")
        except OSError:
            pass
        self.refresh_target()
        self.log(f"Selected {path.name}\n", "muted")

    def open_file(self) -> None:
        path, _ = self.resolve_target()
        if not path:
            messagebox.showinfo("No file", "Fetch or choose a solution file first.")
            return
        try:
            used = open_in_editor(path, self.editor_var.get())
            self.log(f"Opened {path.name} in {used}.\n", "muted")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not open", str(exc))

    def do_fetch(self) -> None:
        identifier = self.problem_var.get().strip() or None
        difficulty = self.fetch_diff.get().strip().lower()
        lang = self.lang_var.get().strip().lower()
        if lang not in SUPPORTED_LANGUAGES:
            messagebox.showerror("Language", "Choose python or javascript.")
            return
        workdir = self._workdir_path()
        if not workdir.is_dir():
            messagebox.showerror("Working folder", f"Not a folder: {workdir}")
            return
        self._persist_workdir()

        self.log_section("Fetch")
        if identifier:
            self.log(f"Fetching '{identifier}'...\n")
        else:
            label = difficulty if difficulty != "any" else "any difficulty"
            self.log(f"Fetching a random {label} problem...\n")

        def work() -> Any:
            problem = data.fetch_problem(self.config, identifier, difficulty)
            path, meta = scaffold.scaffold(problem, lang, workdir)
            return problem, path, meta

        def done(result: Any, err: Exception | None) -> None:
            if err:
                if isinstance(err, FileExistsError):
                    self.log(f"A file already exists: {err}. Not overwriting.\n", "fail")
                else:
                    self.log(f"Error: {err}\n", "fail")
                return
            problem, path, meta = result
            self.log(f"{problem.number}. {problem.title} [{problem.difficulty.capitalize()}]\n")
            self.log(f"{problem.url}\n", "muted")
            self.log(f"Saved: {path}\n", "info")
            n = len(meta.get("test_cases") or [])
            self.log(f"{n} example test case(s) recorded.\n", "muted" if n else "fail")
            self.refresh_target()
            self.status_var.set(f"Fetched {problem.number}. {problem.title}")

        self.run_bg(work, done)

    def do_test(self) -> None:
        path, meta = self.resolve_target()
        if not path or not meta:
            messagebox.showinfo("Nothing to test", "Fetch or choose a solution file first.")
            return
        self.log_section(f"Test {path.name}")
        self.run_bg(lambda: runner.run_tests(path, meta),
                    lambda r, e: self._show_test_report(r, e))

    def _show_test_report(self, report: Any, err: Exception | None) -> bool:
        if err:
            self.log(f"Error running tests: {err}\n", "fail")
            return False
        if not report.ran:
            self.log(f"Skipped: {report.skipped_reason}\n", "muted")
            return False
        for r in report.results:
            if r.passed:
                self.log(f"  [PASS] case {r.index + 1}\n", "pass")
            else:
                self.log(f"  [FAIL] case {r.index + 1}\n", "fail")
                self.log(f"         input:    {' | '.join(r.inputs)}\n", "muted")
                self.log(f"         expected: {r.expected}\n", "muted")
                if r.error:
                    self.log(f"         error:    {r.error}\n", "muted")
                else:
                    self.log(f"         got:      {r.actual}\n", "muted")
            if r.note:
                self.log(f"         note:     {r.note}\n", "muted")
        tag = "pass" if report.passed else "fail"
        self.log(f"  {report.passed_count}/{report.total} cases passed.\n", tag)
        self.status_var.set("All tests passed." if report.passed else "Some tests failed.")
        return report.passed

    def do_submit(self) -> None:
        path, meta = self.resolve_target()
        if not path or not meta:
            messagebox.showinfo("Nothing to submit", "Fetch or choose a solution file first.")
            return
        repo_url = self.repo_var.get().strip()
        if not repo_url:
            messagebox.showerror("No repo", "Set your private repo URL and Save config.")
            return
        if repo_url != self.config.get("repo_url"):
            self.config["repo_url"] = repo_url
            cfg.save_config(self.config)

        self.log_section(f"Submit {path.name}")

        def after_tests(report: Any, err: Exception | None) -> None:
            if err:
                self.log(f"Error running tests: {err}\n", "fail")
                return
            passed = self._show_test_report(report, None)
            if report.ran and not passed:
                # Strict gate: failing tests can never be committed.
                self.log("Tests did not pass - nothing was committed. "
                         "Fix the failing cases and submit again.\n", "fail")
                messagebox.showerror(
                    "Tests failed",
                    "This solution did not pass its tests, so it was not "
                    "committed.\n\nFix the failing cases and try again.")
                self.status_var.set("Submit blocked: tests failed.")
                return
            if not report.ran:
                # No auto-runnable cases: can't verify, so confirm first.
                if not messagebox.askyesno(
                    "No test cases",
                    "There are no automatic test cases to verify this solution. "
                    "Submit anyway?"):
                    self.log("Submit cancelled.\n", "muted")
                    return
            self._do_commit(path, meta, repo_url)

        self.run_bg(lambda: runner.run_tests(path, meta), after_tests)

    def _do_commit(self, path: Path, meta: dict[str, Any], repo_url: str) -> None:
        ext = SUPPORTED_LANGUAGES.get(meta.get("language", "python"), {}).get("ext", "txt")
        self.log("Committing to your solutions repo...\n")

        def work() -> Any:
            return repo.commit_and_push(
                repo_url, path,
                number=meta["number"], title=meta["title"],
                difficulty=meta["difficulty"], slug=meta["slug"], language_ext=ext)

        def done(result: Any, err: Exception | None) -> None:
            if err:
                self.log(f"Git error: {err}\n", "fail")
                return
            committed = result.get("committed")
            if not committed:
                self.log(f"Nothing to commit ({result.get('reason', 'no changes')}) "
                         f"at {result['path']}.\n", "muted")
            else:
                self.log(f"Committed: {result['message']}\n", "pass")
                self.log(f"Path: {result['path']}\n", "muted")
                if result.get("pushed"):
                    self.log("Pushed to remote.\n", "pass")
                else:
                    self.log(f"Push failed: {result.get('push_error', 'unknown')}\n", "fail")
            progress.record_solve(meta["number"], meta["slug"], meta["title"], meta["difficulty"])
            self.refresh_streak()
            # Optional local cleanup once it's safely committed.
            if committed and self.delete_after.get():
                removed = scaffold.cleanup_solution(self._workdir_path(), meta)
                if removed:
                    self.log(f"Cleaned up locally: {', '.join(removed)}\n", "muted")
                self.refresh_target()
            self.status_var.set("Submit complete.")

        self.run_bg(work, done)

    def do_clean(self) -> None:
        workdir = self._workdir_path()
        if not workdir.is_dir():
            messagebox.showerror("Working folder", f"Not a folder: {workdir}")
            return
        if not messagebox.askyesno(
            "Clean folder",
            f"Remove all scaffolded solution files and metadata from\n{workdir}?\n\n"
            "Already-committed solutions remain safe in your repo."):
            return
        removed = scaffold.clean_workdir(workdir)
        if removed:
            self.log(f"Removed {len(removed)} file(s): {', '.join(removed)}\n", "muted")
        else:
            self.log("Nothing to clean.\n", "muted")
        self.refresh_target()


def launch() -> int:
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0
