"""A simple Tkinter GUI for leetcode-assistant.

Wraps the same library functions the command-line uses (data / scaffold /
runner / repo / progress) behind buttons, so you can fetch, test, and submit
without typing commands. Network, test, and git work runs on background
threads to keep the window responsive.

Launch with:  py -m leetcode_assistant gui
"""

from __future__ import annotations

import glob
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

from . import config as cfg
from . import data, progress, repo, roadmap, runner, scaffold
from .config import SUPPORTED_LANGUAGES, VALID_DIFFICULTIES
from .editor import CodeEditor

LANG_CHOICES = ["python", "javascript"]
DIFF_CHOICES = list(VALID_DIFFICULTIES) + ["any"]
LEETCODE_VIEW = "All LeetCode (by topic)"

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
        root.title("Leetcode Assistant")
        root.geometry("1240x900")
        root.minsize(960, 700)
        root.configure(bg=BG)
        self._set_window_icon()

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
        self.solve_title_var = tk.StringVar(value="No problem loaded.")
        self.streak_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready.")

        # Practice / roadmap tab state
        self.topic_problems: dict[str, list[dict[str, Any]]] = {}
        self.leetcode_cache: dict[str, list[dict[str, Any]]] = {}
        self.current_topic: str | None = None
        self.practice_loaded = False
        self.practice_diff = tk.StringVar(value="any")
        self.practice_unsolved = tk.BooleanVar(value=False)
        _preset = roadmap.normalize_preset(self.config.get("preset"))
        self.preset_var = tk.StringVar(value=roadmap.PRESET_NAMES[_preset])

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

        # Notebook tabs
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(16, 8),
                        font=("Segoe UI Semibold", 10))
        style.map("TNotebook.Tab",
                  background=[("selected", CARD), ("!selected", "#dde3ec")],
                  foreground=[("selected", ACCENT), ("!selected", MUTED)])

        # Treeviews (sections + problems)
        style.configure("Treeview", rowheight=24, font=("Segoe UI", 10),
                        background=CARD, fieldbackground=CARD)
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10))

    def _set_window_icon(self) -> None:
        # Icon data is embedded in the source (base64) so we never depend on a
        # bundled file being found inside the frozen exe.
        try:
            from . import _icondata
        except ImportError:
            return
        # PhotoImage handles the taskbar / non-Windows platforms.
        try:
            self._icon_img = tk.PhotoImage(data=_icondata.PNG_B64)  # keep ref
            self.root.iconphoto(True, self._icon_img)
        except (tk.TclError, AttributeError):
            pass
        if not sys.platform.startswith("win"):
            return
        # Write the .ico to disk and force it onto the window's title bar via
        # Win32 WM_SETICON -- Tk's iconbitmap/iconphoto don't reliably set the
        # Windows title-bar icon in a packaged app.
        try:
            import base64
            import tempfile
            self._ico_path = Path(tempfile.gettempdir()) / "leetcode_assistant.ico"
            self._ico_path.write_bytes(base64.b64decode(_icondata.ICO_B64))
            try:
                self.root.iconbitmap(default=str(self._ico_path))
            except tk.TclError:
                pass
            # Defer until the window exists, then push via Win32.
            self.root.after(60, self._win32_set_titlebar_icon)
        except (OSError, AttributeError):
            pass

    def _win32_set_titlebar_icon(self) -> None:
        try:
            import ctypes
            self.root.update_idletasks()
            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            IMAGE_ICON, LR_LOADFROMFILE = 1, 0x00000010
            WM_SETICON, ICON_SMALL, ICON_BIG = 0x0080, 0, 1
            path = str(self._ico_path)
            small = user32.LoadImageW(None, path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
            big = user32.LoadImageW(None, path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
            if hwnd and small:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, small)
            if hwnd and big:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, big)
        except Exception:  # noqa: BLE001 - icon is cosmetic, never crash on it
            pass

    def _card(self, parent: tk.Misc, title: str) -> ttk.Frame:
        lf = ttk.Labelframe(parent, text=title, style="Card.TLabelframe")
        lf.pack(fill="x", padx=14, pady=7)
        inner = ttk.Frame(lf, style="Card.TFrame")
        inner.pack(fill="x", padx=10, pady=8)
        return inner

    def _collapsible_card(self, parent: tk.Misc, title: str,
                          expand: bool = False, collapsed: bool = False) -> ttk.Frame:
        """A card whose body can be collapsed/expanded by clicking its header."""
        container = tk.Frame(parent, bg=CARD, highlightbackground=BORDER,
                             highlightthickness=1, bd=0)
        container.pack(fill="both" if expand else "x", expand=expand, padx=14, pady=6)

        head = tk.Frame(container, bg=CARD, cursor="hand2")
        head.pack(fill="x")
        state = {"open": not collapsed}
        arrow = tk.Label(head, text="▾" if state["open"] else "▸",
                         bg=CARD, fg=ACCENT, font=("Segoe UI", 10, "bold"))
        arrow.pack(side="left", padx=(8, 4), pady=5)
        lbl = tk.Label(head, text=title, bg=CARD, fg=ACCENT,
                       font=("Segoe UI Semibold", 10))
        lbl.pack(side="left", pady=5)

        body = ttk.Frame(container, style="Card.TFrame")
        if state["open"]:
            body.pack(fill="both", expand=expand, padx=10, pady=(0, 8))

        def toggle(_event: Any = None) -> None:
            state["open"] = not state["open"]
            arrow.configure(text="▾" if state["open"] else "▸")
            if state["open"]:
                body.pack(fill="both", expand=expand, padx=10, pady=(0, 8))
            else:
                body.pack_forget()

        for w in (head, arrow, lbl):
            w.bind("<Button-1>", toggle)
        return body

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        # Header bar
        header = ttk.Frame(self.root, style="Header.TFrame")
        header.pack(fill="x")
        htext = ttk.Frame(header, style="Header.TFrame")
        htext.pack(side="left", padx=18, pady=12)
        ttk.Label(htext, text="Leetcode Assistant", style="HeaderTitle.TLabel").pack(anchor="w")
        ttk.Label(htext, text="fetch  -  solve  -  test  -  submit",
                  style="HeaderSub.TLabel").pack(anchor="w")
        ttk.Label(header, textvariable=self.streak_var,
                  style="Streak.TLabel").pack(side="right", padx=18)

        # Status bar (packed first so it stays at the bottom under the notebook)
        ttk.Label(self.root, textvariable=self.status_var, style="Status.TLabel",
                  anchor="w").pack(fill="x", side="bottom")

        # Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        workflow_tab = ttk.Frame(self.notebook)
        solve_tab = ttk.Frame(self.notebook)
        practice_tab = ttk.Frame(self.notebook)
        refresh_tab = ttk.Frame(self.notebook)
        stats_tab = ttk.Frame(self.notebook)
        self.notebook.add(workflow_tab, text="  Workflow  ")
        self.notebook.add(solve_tab, text="  Solve  ")
        self.notebook.add(practice_tab, text="  NeetCode Roadmap  ")
        self.notebook.add(refresh_tab, text="  Refresh  ")
        self.notebook.add(stats_tab, text="  Stats  ")
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self._build_workflow_tab(workflow_tab)
        self._build_solve_tab(solve_tab)
        self._build_practice_tab(practice_tab)
        self._build_refresh_tab(refresh_tab)
        self._build_stats_tab(stats_tab)

        self._bind_shortcuts()
        self._restore_window_state()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_workflow_tab(self, parent: tk.Misc) -> None:
        # Working folder
        wf = self._collapsible_card(parent, "Working folder (solutions are saved here)")
        ttk.Entry(wf, textvariable=self.workdir).pack(side="left", fill="x", expand=True)
        ttk.Button(wf, text="Change...", command=self.choose_workdir).pack(side="left", padx=(8, 0))

        # Config
        cf = self._collapsible_card(parent, "Configuration", collapsed=True)
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
        ff = self._collapsible_card(parent, "Fetch a problem")
        ttk.Label(ff, text="Number or slug (blank = random):", style="Card.TLabel").pack(side="left")
        ttk.Entry(ff, textvariable=self.problem_var, width=22).pack(side="left", padx=6)
        ttk.Label(ff, text="Difficulty:", style="Card.TLabel").pack(side="left")
        ttk.Combobox(ff, textvariable=self.fetch_diff, values=DIFF_CHOICES, width=8,
                     state="readonly").pack(side="left", padx=6)
        self.fetch_btn = ttk.Button(ff, text="Fetch", style="Accent.TButton", command=self.do_fetch)
        self.fetch_btn.pack(side="left", padx=6)

        # Current target + actions
        af = self._collapsible_card(parent, "Current solution")
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
        of = self._collapsible_card(parent, "Output", expand=True)
        mono = tkfont.Font(family="Consolas", size=10)
        self.log_widget = tk.Text(of, wrap="word", height=16, state="disabled",
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

    # ------------------------------------------------------------------ #
    # Solve tab -- in-app code editor (experimental)
    # ------------------------------------------------------------------ #
    def _build_solve_tab(self, parent: tk.Misc) -> None:
        self.solve_path: Path | None = None
        self.solve_meta: dict[str, Any] | None = None

        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=10, pady=(8, 4))
        ttk.Label(bar, textvariable=self.solve_title_var,
                  style="Target.TLabel").pack(side="left")
        ttk.Button(bar, text="Reload", command=self._load_solve).pack(side="right", padx=3)
        ttk.Button(bar, text="Open in PyCharm", command=self.open_file).pack(side="right", padx=3)
        self.solve_submit_btn = ttk.Button(bar, text="Submit", style="Accent.TButton",
                                           command=self._solve_submit)
        self.solve_submit_btn.pack(side="right", padx=3)
        self.solve_test_btn = ttk.Button(bar, text="Run tests", style="Accent.TButton",
                                         command=self._solve_run_tests)
        self.solve_test_btn.pack(side="right", padx=3)
        self.solve_save_btn = ttk.Button(bar, text="Save", command=self._solve_save)
        self.solve_save_btn.pack(side="right", padx=3)

        # main split: description | editor
        split = tk.PanedWindow(parent, orient="horizontal", sashwidth=6,
                               bg=BORDER, bd=0)
        split.pack(fill="both", expand=True, padx=10, pady=6)

        desc_wrap = ttk.Labelframe(split, text="Problem", style="Card.TLabelframe")
        self.desc_text = tk.Text(desc_wrap, wrap="word", state="disabled",
                                 bg=CARD, fg=TEXT, relief="flat", padx=10, pady=8,
                                 font=("Segoe UI", 10), width=42)
        self.desc_text.pack(side="left", fill="both", expand=True)
        dsb = ttk.Scrollbar(desc_wrap, command=self.desc_text.yview)
        dsb.pack(side="right", fill="y")
        self.desc_text.configure(yscrollcommand=dsb.set)
        split.add(desc_wrap, minsize=260, width=440)

        edit_wrap = ttk.Labelframe(split, text="Your solution", style="Card.TLabelframe")
        self.code_editor = CodeEditor(edit_wrap, language="python")
        self.code_editor.pack(fill="both", expand=True, padx=2, pady=2)
        split.add(edit_wrap, minsize=420)

        # bottom: test/output console
        out = ttk.Labelframe(parent, text="Tests / output", style="Card.TLabelframe")
        out.pack(fill="x", padx=10, pady=(0, 8))
        mono = tkfont.Font(family="Consolas", size=10)
        self.solve_output = tk.Text(out, wrap="word", height=6, state="disabled",
                                    background=CONSOLE_BG, foreground=CONSOLE_FG,
                                    relief="flat", font=mono, padx=10, pady=6)
        self.solve_output.pack(side="left", fill="both", expand=True)
        osb = ttk.Scrollbar(out, command=self.solve_output.yview)
        osb.pack(side="right", fill="y")
        self.solve_output.configure(yscrollcommand=osb.set)
        for tag, col in (("pass", "#34d399"), ("fail", "#f87171"),
                         ("info", "#60a5fa"), ("muted", "#94a3b8")):
            self.solve_output.tag_configure(tag, foreground=col)

    def _solve_log(self, text: str, tag: str | None = None) -> None:
        self.solve_output.configure(state="normal")
        self.solve_output.insert("end", text, tag or ())
        self.solve_output.see("end")
        self.solve_output.configure(state="disabled")

    def _set_desc(self, text: str) -> None:
        self.desc_text.configure(state="normal")
        self.desc_text.delete("1.0", "end")
        self.desc_text.insert("1.0", text)
        self.desc_text.configure(state="disabled")

    def _load_solve(self) -> None:
        path, meta = self.resolve_target()
        if not path or not meta:
            self.solve_title_var.set("No problem loaded -- fetch one in the Workflow tab.")
            self._set_desc("Fetch a problem first, then come here to solve it.")
            self.code_editor.set_code("")
            self.solve_path = self.solve_meta = None
            return
        # Start (or keep) a solve timer for this problem.
        if getattr(self, "_solve_timed_slug", None) != meta.get("slug"):
            self._solve_started = time.monotonic()
            self._solve_timed_slug = meta.get("slug")
        self.solve_path, self.solve_meta = path, meta
        self.solve_title_var.set(
            f"{meta['number']}. {meta['title']}  [{meta['difficulty'].capitalize()}]")
        desc = meta.get("description") or self._description_from_file(path, meta)
        self._set_desc(desc or "(no description stored)")
        lang = meta.get("language", "python")
        try:
            text = path.read_text(encoding="utf-8")
            # The description is already shown on the left, so keep it out of the
            # editor -- show just the code. We re-attach the header on save.
            self._solve_header, body = self._split_header(text, lang)
            self.code_editor.set_code(body, language=lang)
        except OSError as exc:
            self._solve_log(f"Could not read file: {exc}\n", "fail")
        self.code_editor.focus_editor()

    @staticmethod
    def _split_header(text: str, lang: str) -> tuple[str, str]:
        """Split the leading description comment block from the code body."""
        if lang == "javascript":
            m = re.match(r"\s*/\*.*?\*/\s*", text, re.S)
        else:
            m = re.match(r"\s*(?P<q>\"\"\"|''').*?(?P=q)\s*", text, re.S)
        if m:
            return text[:m.end()], text[m.end():]
        return "", text

    def _open_solve(self) -> None:
        """Switch to the Solve tab and load the current problem into the editor."""
        for i in range(len(self.notebook.tabs())):
            if "Solve" in self.notebook.tab(i, "text"):
                self.notebook.select(i)
                break
        self._load_solve()

    @staticmethod
    def _description_from_file(path: Path, meta: dict[str, Any]) -> str:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return ""
        if meta.get("language") == "javascript":
            m = re.search(r"/\*(.*?)\*/", text, re.S)
            body = m.group(1) if m else ""
            return "\n".join(line.lstrip(" *") for line in body.splitlines()).strip()
        m = re.search(r'"""(.*?)"""', text, re.S)
        return (m.group(1).strip() if m else "")

    def _solve_save(self) -> bool:
        if not self.solve_path:
            return False
        try:
            # Re-attach the description header that we hid from the editor.
            content = getattr(self, "_solve_header", "") + self.code_editor.get_code()
            self.solve_path.write_text(content, encoding="utf-8")
            self.status_var.set(f"Saved {self.solve_path.name}")
            return True
        except OSError as exc:
            self._solve_log(f"Save failed: {exc}\n", "fail")
            return False

    def _solve_run_tests(self) -> None:
        if not self.solve_path or not self.solve_meta:
            messagebox.showinfo("Nothing to test", "Fetch a problem first.")
            return
        if not self._solve_save():
            return
        self.solve_output.configure(state="normal")
        self.solve_output.delete("1.0", "end")
        self.solve_output.configure(state="disabled")
        self._solve_log("Running tests...\n", "info")
        path, meta = self.solve_path, self.solve_meta
        self.run_bg(lambda: runner.run_tests(path, meta),
                    lambda r, e: self._solve_show_report(r, e))

    def _solve_show_report(self, report: Any, err: Exception | None) -> bool:
        if err:
            self._solve_log(f"Error: {err}\n", "fail")
            return False
        if not report.ran:
            self._solve_log(f"Skipped: {report.skipped_reason}\n", "muted")
            return False
        for r in report.results:
            if r.passed:
                self._solve_log(f"  [PASS] case {r.index + 1}\n", "pass")
            else:
                self._solve_log(f"  [FAIL] case {r.index + 1}\n", "fail")
                self._solve_log(f"         input:    {' | '.join(r.inputs)}\n", "muted")
                self._solve_log(f"         expected: {r.expected}\n", "muted")
                self._solve_log(f"         got:      {r.error or r.actual}\n", "muted")
        tag = "pass" if report.passed else "fail"
        self._solve_log(f"  {report.passed_count}/{report.total} cases passed.\n", tag)
        return report.passed

    def _solve_submit(self) -> None:
        if not self.solve_path or not self.solve_meta:
            messagebox.showinfo("Nothing to submit", "Fetch a problem first.")
            return
        if not self._solve_save():
            return
        repo_url = self.repo_var.get().strip()
        if not repo_url:
            messagebox.showerror("No repo", "Set your private repo URL in the Workflow tab.")
            return
        path, meta = self.solve_path, self.solve_meta
        self.solve_output.configure(state="normal")
        self.solve_output.delete("1.0", "end")
        self.solve_output.configure(state="disabled")
        self._solve_log("Submitting...\n", "info")

        def after_tests(report: Any, err: Exception | None) -> None:
            if err:
                self._solve_log(f"Error: {err}\n", "fail")
                return
            passed = self._solve_show_report(report, None)
            has_tests = bool(meta.get("test_cases"))
            if has_tests and not (report.ran and passed):
                msg = ("Tests did not pass" if report.ran else
                       "Tests could not run (does the code compile?)")
                self._solve_log(f"{msg} -- nothing committed.\n", "fail")
                messagebox.showerror("Tests must pass", msg + ", so it was not committed.")
                return
            if not has_tests and not messagebox.askyesno(
                    "No test cases", "No automatic tests for this problem. Submit anyway?"):
                self._solve_log("Cancelled.\n", "muted")
                return
            elapsed = None
            if getattr(self, "_solve_started", None) is not None:
                elapsed = int(time.monotonic() - self._solve_started)
            rating = self._rating_for(meta.get("slug", ""))
            self._do_commit(path, meta, repo_url, seconds=elapsed, rating=rating)
            if elapsed:
                m, s = divmod(elapsed, 60)
                self._solve_log(f"Solved in {m}m {s}s.\n", "muted")
            self._solve_log("Committed (see the Workflow Output for details).\n", "pass")

        self.run_bg(lambda: runner.run_tests(path, meta), after_tests)

    # ------------------------------------------------------------------ #
    # NeetCode roadmap tab
    # ------------------------------------------------------------------ #
    def _build_practice_tab(self, parent: tk.Misc) -> None:
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=12, pady=(10, 4))
        # Pack the right-hand controls FIRST so they keep their full size; the
        # description label (packed last) takes whatever space is left over.
        ttk.Button(bar, text="Refresh", command=lambda: self._populate_topics(force=True)
                   ).pack(side="right", padx=(8, 0))
        preset_box = ttk.Combobox(
            bar, textvariable=self.preset_var, width=26, state="readonly",
            values=[name for _, name in roadmap.PRESETS] + [LEETCODE_VIEW])
        preset_box.pack(side="right", padx=6)
        preset_box.bind("<<ComboboxSelected>>", lambda e: self._on_preset_changed())
        ttk.Label(bar, text="List:", style="TLabel").pack(side="right", padx=(0, 2))
        ttk.Label(bar, text="Pick a list, then a topic, and drill its problems.",
                  style="TLabel").pack(side="left")

        body = ttk.Frame(parent)
        body.pack(fill="both", expand=True, padx=12, pady=6)

        # Left: topics (roadmap order for NeetCode; LeetCode taxonomy otherwise)
        left = ttk.Labelframe(body, text="Topics", style="Card.TLabelframe")
        left.pack(side="left", fill="y", padx=(0, 8))
        self.topic_tree = ttk.Treeview(left, columns=("prog",), show="tree headings",
                                       height=18, selectmode="browse")
        self.topic_tree.heading("#0", text="Topic")
        self.topic_tree.heading("prog", text="Done")
        self.topic_tree.column("#0", width=210, anchor="w")
        self.topic_tree.column("prog", width=64, anchor="center")
        self.topic_tree.pack(side="left", fill="y", padx=6, pady=6)
        self.topic_tree.bind("<<TreeviewSelect>>", self._on_topic_selected)
        self.topic_tree.tag_configure("complete", foreground="#1a7f37")

        # Right: problems in selected topic
        right = ttk.Labelframe(body, text="Problems", style="Card.TLabelframe")
        right.pack(side="left", fill="both", expand=True)
        self.topic_header_var = tk.StringVar(value="Select a topic on the left.")
        ttk.Label(right, textvariable=self.topic_header_var, style="Muted.TLabel"
                  ).pack(anchor="w", padx=8, pady=(6, 0))
        ctl = ttk.Frame(right, style="Card.TFrame")
        ctl.pack(fill="x", padx=6, pady=6)
        ttk.Label(ctl, text="Difficulty:", style="Card.TLabel").pack(side="left")
        ttk.Combobox(ctl, textvariable=self.practice_diff, values=DIFF_CHOICES, width=8,
                     state="readonly").pack(side="left", padx=6)
        self.practice_diff.trace_add("write", lambda *_: self._refresh_question_list())
        ttk.Checkbutton(ctl, text="Unsolved only", variable=self.practice_unsolved,
                        command=self._refresh_question_list, style="TCheckbutton").pack(side="left", padx=10)
        self.practice_fetch_btn = ttk.Button(ctl, text="Fetch selected", style="Accent.TButton",
                                             command=self._fetch_selected_question)
        self.practice_fetch_btn.pack(side="right", padx=4)
        ttk.Button(ctl, text="Random unsolved", command=self._fetch_random_in_topic
                   ).pack(side="right", padx=4)

        qwrap = ttk.Frame(right, style="Card.TFrame")
        qwrap.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.question_tree = ttk.Treeview(
            qwrap, columns=("num", "diff", "title", "done"), show="headings",
            selectmode="browse")
        for col, text, w, anchor in (
            ("num", "#", 60, "center"), ("diff", "Difficulty", 90, "center"),
            ("title", "Title", 360, "w"), ("done", "Solved", 70, "center")):
            self.question_tree.heading(col, text=text)
            self.question_tree.column(col, width=w, anchor=anchor)
        self.question_tree.pack(side="left", fill="both", expand=True)
        qsb = ttk.Scrollbar(qwrap, command=self.question_tree.yview)
        qsb.pack(side="right", fill="y")
        self.question_tree.configure(yscrollcommand=qsb.set)
        self.question_tree.tag_configure("easy", foreground="#1a7f37")
        self.question_tree.tag_configure("medium", foreground="#9a6700")
        self.question_tree.tag_configure("hard", foreground="#cf222e")
        self.question_tree.tag_configure("solved", background="#e6f4ea")
        self.question_tree.bind("<Double-1>", lambda e: self._fetch_selected_question())

    # --- mode helpers --------------------------------------------------- #
    def _current_mode(self) -> str:
        return "leetcode" if self.preset_var.get() == LEETCODE_VIEW else "neetcode"

    def _current_preset(self) -> str:
        name = self.preset_var.get()
        for key, disp in roadmap.PRESETS:
            if disp == name:
                return key
        return roadmap.DEFAULT_PRESET

    def _on_tab_changed(self, _event: Any) -> None:
        try:
            current = self.notebook.tab(self.notebook.select(), "text")
        except tk.TclError:
            return
        if "Roadmap" in current and not self.practice_loaded:
            self.practice_loaded = True
            self._populate_topics()
        elif "Solve" in current:
            self._load_solve()
        elif "Refresh" in current:
            self._refresh_refresh_tab()
        elif "Stats" in current:
            self._refresh_stats()

    # ------------------------------------------------------------------ #
    # Refresh tab (spaced repetition)
    # ------------------------------------------------------------------ #
    def _build_refresh_tab(self, parent: tk.Misc) -> None:
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Label(bar, text="Spaced repetition: blind-retest problems as they come due, "
                  "then rate how it went to set the next interval.",
                  style="TLabel").pack(side="left")
        ttk.Button(bar, text="Refresh list", command=self._refresh_refresh_tab
                   ).pack(side="right")

        body = ttk.Frame(parent)
        body.pack(fill="both", expand=True, padx=12, pady=6)

        due = ttk.Labelframe(body, text="Due now", style="Card.TLabelframe")
        due.pack(fill="both", expand=True, side="top", pady=(0, 6))
        ctl = ttk.Frame(due, style="Card.TFrame")
        ctl.pack(fill="x", padx=6, pady=6)
        self.refresh_start_btn = ttk.Button(ctl, text="Start blind retest",
                                            style="Accent.TButton",
                                            command=self._refresh_start)
        self.refresh_start_btn.pack(side="left", padx=4)
        ttk.Label(ctl, text="(fetches a fresh copy and opens the Solve tab)",
                  style="Card.TLabel").pack(side="left", padx=6)
        self.refresh_due_tree = ttk.Treeview(
            due, columns=("num", "diff", "title", "level", "over"), show="headings",
            selectmode="browse", height=8)
        for col, text, w, anchor in (
            ("num", "#", 60, "center"), ("diff", "Difficulty", 90, "center"),
            ("title", "Problem", 330, "w"), ("level", "Level", 100, "center"),
            ("over", "Overdue", 90, "center")):
            self.refresh_due_tree.heading(col, text=text)
            self.refresh_due_tree.column(col, width=w, anchor=anchor)
        self.refresh_due_tree.pack(side="left", fill="both", expand=True, padx=6, pady=(0, 6))
        self.refresh_due_tree.bind("<Double-1>", lambda e: self._refresh_start())

        up = ttk.Labelframe(body, text="Upcoming", style="Card.TLabelframe")
        up.pack(fill="both", expand=True, side="top")
        self.refresh_up_tree = ttk.Treeview(
            up, columns=("num", "title", "level", "due"), show="headings",
            selectmode="none", height=7)
        for col, text, w, anchor in (
            ("num", "#", 60, "center"), ("title", "Problem", 330, "w"),
            ("level", "Level", 110, "center"), ("due", "Next review", 200, "w")):
            self.refresh_up_tree.heading(col, text=text)
            self.refresh_up_tree.column(col, width=w, anchor=anchor)
        self.refresh_up_tree.pack(fill="both", expand=True, padx=6, pady=6)

    def _refresh_refresh_tab(self) -> None:
        if not hasattr(self, "refresh_due_tree"):
            return
        self.refresh_due_tree.delete(*self.refresh_due_tree.get_children())
        for r in progress.due_reviews():
            od = "today" if r["days_overdue"] == 0 else f"+{r['days_overdue']}d"
            self.refresh_due_tree.insert(
                "", "end", iid=r["slug"],
                values=(r.get("number", ""), (r.get("difficulty", "") or "").capitalize(),
                        r.get("title", r["slug"]), progress.level_name(r.get("level", 0)), od))
        self.refresh_up_tree.delete(*self.refresh_up_tree.get_children())
        for r in progress.upcoming_reviews():
            self.refresh_up_tree.insert(
                "", "end",
                values=(r.get("number", ""), r.get("title", r["slug"]),
                        progress.level_name(r.get("level", 0)),
                        f"{r['due']} (in {r['days_until']}d)"))

    def _refresh_start(self) -> None:
        sel = self.refresh_due_tree.selection()
        if not sel:
            messagebox.showinfo("Pick a problem", "Select a due problem to retest.")
            return
        slug = sel[0]
        # Blind retest: remove any old scaffold for this problem so the editor
        # starts empty, then fetch a fresh copy.
        try:
            wd = self._workdir_path()
            num = int(progress.all_reviews().get(slug, {}).get("number") or 0)
            for ext in ("py", "js"):
                f = wd / f"{num:04d}-{slug}.{ext}"
                if f.exists():
                    f.unlink()
            mp = wd / cfg.WORKDIR_META / f"{slug}.json"
            if mp.exists():
                mp.unlink()
        except (OSError, ValueError):
            pass
        self._fetch_problem_by_slug(slug)  # fetches fresh + opens the Solve tab

    # ------------------------------------------------------------------ #
    # Stats tab (heatmap + summary)
    # ------------------------------------------------------------------ #
    def _build_stats_tab(self, parent: tk.Misc) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=14, pady=(12, 4))
        self.stats_summary_var = tk.StringVar(value="No solves yet.")
        ttk.Label(top, textvariable=self.stats_summary_var,
                  font=("Segoe UI", 11)).pack(anchor="w")

        hm = ttk.Labelframe(parent, text="Activity (last 26 weeks)", style="Card.TLabelframe")
        hm.pack(fill="x", padx=14, pady=8)
        self.heatmap = tk.Canvas(hm, height=130, bg=CARD, highlightthickness=0)
        self.heatmap.pack(fill="x", padx=10, pady=10)

        br = ttk.Labelframe(parent, text="By difficulty", style="Card.TLabelframe")
        br.pack(fill="x", padx=14, pady=8)
        self.stats_diff_var = tk.StringVar(value="")
        ttk.Label(br, textvariable=self.stats_diff_var, style="Card.TLabel",
                  font=("Consolas", 10)).pack(anchor="w", padx=10, pady=8)

    def _refresh_stats(self) -> None:
        s = progress.stats()
        opt = f"  |  optimal {s['optimal']}/{s['total']}" if s["total"] else ""
        self.stats_summary_var.set(
            f"Solved: {s['total']}    Current streak: {s['streak']}    "
            f"Longest streak: {s['longest_streak']}{opt}")
        d = s["by_difficulty"]
        self.stats_diff_var.set(
            f"Easy {d.get('easy', 0):>4}    "
            f"Medium {d.get('medium', 0):>4}    Hard {d.get('hard', 0):>4}")
        self._draw_heatmap()

    def _draw_heatmap(self) -> None:
        c = self.heatmap
        c.delete("all")
        counts = progress.solves_by_date()
        cell, gap = 14, 3
        weeks = 26
        today = date.today()
        # start on the Sunday that begins the leftmost visible week
        start = today - timedelta(days=today.weekday() + 1 + (weeks - 1) * 7)
        palette = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
        x0, y0 = 4, 18
        for w in range(weeks):
            for d in range(7):
                day = start + timedelta(days=w * 7 + d)
                if day > today:
                    continue
                n = counts.get(day.isoformat(), 0)
                color = palette[min(n, 4)] if n else palette[0]
                x = x0 + w * (cell + gap)
                y = y0 + d * (cell + gap)
                c.create_rectangle(x, y, x + cell, y + cell, fill=color,
                                   outline=CARD)
        # month ticks
        c.create_text(x0, 6, anchor="nw", text=start.strftime("%b"),
                      fill=MUTED, font=("Segoe UI", 8))
        c.create_text(x0 + 13 * (cell + gap), 6, anchor="nw",
                      text=(start + timedelta(days=13 * 7)).strftime("%b"),
                      fill=MUTED, font=("Segoe UI", 8))

    # ------------------------------------------------------------------ #
    # shortcuts + window-state persistence
    # ------------------------------------------------------------------ #
    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-s>", lambda e: self._shortcut_save())
        self.root.bind("<Control-Return>", lambda e: self._shortcut_test())
        self.root.bind("<Control-Shift-Return>", lambda e: self._shortcut_submit())

    def _on_solve_tab(self) -> bool:
        try:
            return "Solve" in self.notebook.tab(self.notebook.select(), "text")
        except tk.TclError:
            return False

    def _shortcut_save(self) -> str:
        if self._on_solve_tab():
            self._solve_save()
        return "break"

    def _shortcut_test(self) -> str:
        if self._on_solve_tab():
            self._solve_run_tests()
        else:
            self.do_test()
        return "break"

    def _shortcut_submit(self) -> str:
        if self._on_solve_tab():
            self._solve_submit()
        else:
            self.do_submit()
        return "break"

    def _restore_window_state(self) -> None:
        geo = self.config.get("win_geometry", "")
        if geo:
            try:
                self.root.geometry(geo)
            except tk.TclError:
                pass

    def _on_close(self) -> None:
        try:
            self.config["win_geometry"] = self.root.geometry()
            cfg.save_config(self.config)
        except Exception:  # noqa: BLE001
            pass
        self.root.destroy()

    def _on_preset_changed(self) -> None:
        if self._current_mode() == "neetcode":
            self.config["preset"] = self._current_preset()
            cfg.save_config(self.config)
        self.current_topic = None
        self.topic_header_var.set("Select a topic on the left.")
        self.question_tree.delete(*self.question_tree.get_children())
        self._populate_topics()

    # --- topic list population (both modes) ----------------------------- #
    def _populate_topics(self, force: bool = False) -> None:
        if force:
            self.leetcode_cache.clear()
        self.topic_tree.delete(*self.topic_tree.get_children())
        if self._current_mode() == "neetcode":
            self._populate_neetcode(force=force)
        else:
            self._populate_leetcode()

    def _populate_neetcode(self, force: bool = False) -> None:
        try:
            roadmap.all_problems(force=force)  # bundled JSON; instant
        except roadmap.RoadmapError as exc:
            self.topic_header_var.set("Could not load roadmap data.")
            self.log(f"Roadmap load error: {exc}\n", "fail")
            return
        preset = self._current_preset()
        solved = progress.solved_slugs()
        self.topic_problems = {}
        for topic, probs in roadmap.topics_for_preset(preset):
            self.topic_problems[topic] = probs
            done = sum(1 for p in probs if p["slug"] in solved)
            total = len(probs)
            tags = ("complete",) if total and done == total else ()
            self.topic_tree.insert("", "end", iid=topic, text=topic,
                                   values=(f"{done}/{total}",), tags=tags)
        self.status_var.set("Roadmap loaded.")

    def _populate_leetcode(self) -> None:
        solved = progress.solved_slugs()
        self.topic_problems = {}
        missing: list[tuple[str, str]] = []
        for name, slug in data.LEETCODE_TOPICS:
            cached = self.leetcode_cache.get(slug)
            if cached is not None:
                self.topic_problems[name] = cached
                done = sum(1 for q in cached if q["slug"] in solved)
                val = f"{done}/{len(cached)}"
            else:
                val = "..."
                missing.append((name, slug))
            self.topic_tree.insert("", "end", iid=name, text=name, values=(val,))
        if missing:
            # Load every topic's counts up front (background; cached for a week).
            self._load_all_leetcode_counts(missing)
        else:
            self.status_var.set("All LeetCode topics loaded.")

    def _load_all_leetcode_counts(self, topics: list[tuple[str, str]]) -> None:
        """Fetch each LeetCode topic's problem list in the background and fill in
        its count. Runs off the busy-gate so the rest of the app stays usable."""
        if getattr(self, "_loading_counts", False):
            return
        self._loading_counts = True
        self.status_var.set(f"Loading counts for {len(topics)} LeetCode topics...")
        include_paid = bool(self.config.get("include_paid", False))

        def worker() -> None:
            for name, slug in topics:
                try:
                    qs = data.leetcode_topic_questions(slug)
                except Exception:  # noqa: BLE001
                    qs = []
                if not include_paid:
                    qs = [q for q in qs if not q["paid"]]
                self._post(lambda n=name, s=slug, q=qs: self._apply_leetcode_count(n, s, q))
            self._post(self._finish_count_load)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_leetcode_count(self, name: str, slug: str,
                              qs: list[dict[str, Any]]) -> None:
        self.leetcode_cache[slug] = qs
        if self._current_mode() == "leetcode":
            self.topic_problems[name] = qs
        if self.topic_tree.exists(name):
            solved = progress.solved_slugs()
            done = sum(1 for q in qs if q["slug"] in solved)
            self.topic_tree.item(name, values=(f"{done}/{len(qs)}",))
        if self.current_topic == name and self._current_mode() == "leetcode":
            self._refresh_question_list()

    def _finish_count_load(self) -> None:
        self._loading_counts = False
        self.status_var.set("All LeetCode topics loaded.")

    def _on_topic_selected(self, _event: Any) -> None:
        sel = self.topic_tree.selection()
        if not sel:
            return
        topic = self.current_topic = sel[0]
        if self._current_mode() == "neetcode":
            pre = ", ".join(roadmap.PREREQS.get(topic, [])) or "none (start here)"
            self.topic_header_var.set(f"{topic}    -    prerequisites: {pre}")
            self._refresh_question_list()
        else:
            self.topic_header_var.set(f"All LeetCode problems tagged '{topic}'")
            if topic in self.topic_problems:
                self._refresh_question_list()
            else:
                self._load_leetcode_topic(topic, data.LEETCODE_TOPIC_BY_DISPLAY[topic])

    def _load_leetcode_topic(self, topic: str, slug: str) -> None:
        self.question_tree.delete(*self.question_tree.get_children())
        self.status_var.set(f"Loading '{topic}' from LeetCode...")

        def work() -> Any:
            return data.leetcode_topic_questions(slug)

        def done(result: Any, err: Exception | None) -> None:
            if err:
                self.log(f"Could not load '{topic}': {err}\n", "fail")
                self.status_var.set("Topic load failed.")
                return
            qs = (result if self.config.get("include_paid", False)
                  else [q for q in result if not q["paid"]])
            self.leetcode_cache[slug] = qs
            self.topic_problems[topic] = qs
            solved = progress.solved_slugs()
            done_n = sum(1 for q in qs if q["slug"] in solved)
            if self.topic_tree.exists(topic):
                self.topic_tree.item(topic, values=(f"{done_n}/{len(qs)}",))
            if self.current_topic == topic:
                self._refresh_question_list()
            self.status_var.set(f"{topic}: {len(qs)} problems")

        self.run_bg(work, done)

    def _refresh_question_list(self) -> None:
        topic = self.current_topic
        self.question_tree.delete(*self.question_tree.get_children())
        if not topic or topic not in self.topic_problems:
            return
        solved = progress.solved_slugs()
        diff = self.practice_diff.get()
        unsolved_only = self.practice_unsolved.get()
        for q in self.topic_problems[topic]:
            if diff in ("easy", "medium", "hard") and q["difficulty"] != diff:
                continue
            is_solved = q["slug"] in solved
            if unsolved_only and is_solved:
                continue
            tags = (q["difficulty"],) + (("solved",) if is_solved else ())
            self.question_tree.insert(
                "", "end", iid=q["slug"],
                values=(q["number"], q["difficulty"].capitalize(), q["title"],
                        "yes" if is_solved else ""),
                tags=tags)

    def _fetch_selected_question(self) -> None:
        sel = self.question_tree.selection()
        if not sel:
            messagebox.showinfo("Pick a problem", "Select a problem in the list first.")
            return
        self._fetch_problem_by_slug(sel[0])

    def _fetch_random_in_topic(self) -> None:
        topic = self.current_topic
        if not topic or topic not in self.topic_problems:
            messagebox.showinfo("Pick a topic", "Select a topic first (and let it load).")
            return
        solved = progress.solved_slugs()
        pool = self.topic_problems[topic]
        diff = self.practice_diff.get()
        if diff in ("easy", "medium", "hard"):
            pool = [q for q in pool if q["difficulty"] == diff]
        unsolved = [q for q in pool if q["slug"] not in solved]
        pick_from = unsolved or pool
        if not pick_from:
            messagebox.showinfo("Nothing to fetch", "No problems match the current filter.")
            return
        import random as _r
        self._fetch_problem_by_slug(_r.choice(pick_from)["slug"])

    def _refresh_practice_after_solve(self) -> None:
        """Recompute counts + the visible list (no network) so progress
        reflects the just-solved problem."""
        if not self.practice_loaded:
            return
        self._populate_topics()
        self._refresh_question_list()

    def _fetch_problem_by_slug(self, slug: str) -> None:
        lang = self.lang_var.get().strip().lower()
        if lang not in SUPPORTED_LANGUAGES:
            messagebox.showerror("Language", "Choose python or javascript.")
            return
        workdir = self._workdir_path()
        if not workdir.is_dir():
            messagebox.showerror("Working folder", f"Not a folder: {workdir}")
            return
        self.log_section(f"Fetch {slug}")
        self.log(f"Fetching '{slug}'...\n")

        def work() -> Any:
            problem = data.leetcode_get(slug)
            return scaffold.scaffold(problem, lang, workdir) + (problem,)

        def done(result: Any, err: Exception | None) -> None:
            if err:
                if isinstance(err, FileExistsError):
                    self.log(f"A file already exists: {err}. Not overwriting.\n", "fail")
                else:
                    self.log(f"Error: {err}\n", "fail")
                return
            path, meta, problem = result
            self.log(f"{problem.number}. {problem.title} "
                     f"[{problem.difficulty.capitalize()}]\n")
            self.log(f"Saved: {path}\n", "info")
            self.refresh_target()
            self._open_solve()  # jump straight into the editor
            self.status_var.set(f"Fetched {problem.number}. {problem.title}")

        self.run_bg(work, done)

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
        buttons = [self.fetch_btn, self.test_btn, self.submit_btn]
        for name in ("practice_fetch_btn", "solve_test_btn", "solve_submit_btn"):
            if hasattr(self, name):
                buttons.append(getattr(self, name))
        for btn in buttons:
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
            self._open_solve()

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
            has_tests = bool(meta.get("test_cases"))
            if has_tests:
                # This problem HAS example tests -> they must pass. If they
                # failed, or couldn't run (e.g. the solution doesn't compile
                # yet), block. Never offer a bypass here.
                if not (report.ran and passed):
                    if report.ran:
                        reason = ("This solution did not pass its tests, so it was "
                                  "not committed.")
                    else:
                        reason = ("This solution's tests could not run -- check that "
                                  "the file compiles and the method is complete. "
                                  "Nothing was committed.")
                    self.log("Not committed - tests must pass first.\n", "fail")
                    messagebox.showerror("Tests must pass", reason +
                                         "\n\nFix it and submit again.")
                    self.status_var.set("Submit blocked: tests not passed.")
                    return
            else:
                # Problem genuinely has no auto-runnable cases: confirm first.
                if not messagebox.askyesno(
                    "No test cases",
                    "This problem has no automatic test cases to verify the "
                    "solution. Submit anyway?"):
                    self.log("Submit cancelled.\n", "muted")
                    return
            rating = self._rating_for(meta.get("slug", ""))
            self._do_commit(path, meta, repo_url, rating=rating)

        self.run_bg(lambda: runner.run_tests(path, meta), after_tests)

    def _rating_for(self, slug: str) -> str | None:
        """If this problem is already tracked for review, ask how the blind
        retest went (spaced repetition). First solves return None."""
        if not slug or not progress.has_review(slug):
            return None
        return self._ask_confidence()

    def _ask_confidence(self) -> str | None:
        """Modal 3-choice confidence prompt. Returns aced/good/hard or None."""
        win = tk.Toplevel(self.root)
        win.title("How did the refresh go?")
        win.configure(bg=CARD)
        win.transient(self.root)
        win.resizable(False, False)
        result = {"v": None}
        ttk.Label(win, text="Rate this blind attempt -- it sets the next refresh date:",
                  style="Card.TLabel", padding=12).pack()
        row = ttk.Frame(win, style="Card.TFrame")
        row.pack(padx=12, pady=(0, 12))

        def choose(v: str) -> None:
            result["v"] = v
            win.destroy()

        for val, label in (("aced", "Aced it (no help)  ->  longer"),
                           ("good", "Got it (some hesitation)  ->  same"),
                           ("hard", "Needed help  ->  retest soon")):
            ttk.Button(row, text=label, width=34,
                       command=lambda v=val: choose(v)).pack(pady=3)
        win.update_idletasks()
        # center on the main window
        x = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - win.winfo_height()) // 2
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
        win.grab_set()
        self.root.wait_window(win)
        return result["v"]

    def _do_commit(self, path: Path, meta: dict[str, Any], repo_url: str,
                   seconds: int | None = None, rating: str | None = None) -> None:
        ext = SUPPORTED_LANGUAGES.get(meta.get("language", "python"), {}).get("ext", "txt")
        self.log("Tests passed. Checking solution complexity "
                 "(this can take a few seconds), then committing...\n", "info")
        self.status_var.set("Checking complexity, please wait...")

        def work() -> Any:
            from . import complexity, roadmap
            self._post(lambda: self.status_var.set("Checking complexity, please wait..."))
            cx = complexity.estimate(path, meta)
            topic = roadmap.topic_for_slug(meta["slug"]) or ""
            # record BEFORE commit so the repo README includes this solve
            progress.record_solve(
                meta["number"], meta["slug"], meta["title"], meta["difficulty"],
                topic=topic, optimality=cx.verdict, url=meta.get("url"), seconds=seconds)
            review = progress.schedule_review(
                meta["slug"], {**meta, "topic": topic}, rating=rating)
            result = repo.commit_and_push(
                repo_url, path,
                number=meta["number"], title=meta["title"],
                difficulty=meta["difficulty"], slug=meta["slug"], language_ext=ext)
            return result, cx, review

        def done(payload: Any, err: Exception | None) -> None:
            if err:
                self.log(f"Git error: {err}\n", "fail")
                return
            result, cx, review = payload
            if cx.verdict == "optimal":
                self.log(f"Complexity: {cx.summary()} -- optimal.\n", "pass")
            elif cx.verdict == "suboptimal":
                self.log(f"Complexity: {cx.summary()} (optimal time is {cx.optimal}) "
                         "-- looks brute-force/half-solved.\n", "fail")
            elif cx.measured != "unknown":
                self.log(f"Complexity: {cx.summary()}.\n", "muted")
            if review:
                self.log(f"Next refresh: {review['due']} "
                         f"({progress.level_name(review['level'])}).\n", "info")
            committed = result.get("committed")
            if not committed:
                self.log(f"Nothing to commit ({result.get('reason', 'no changes')}) "
                         f"at {result['path']}.\n", "muted")
            else:
                self.log(f"Committed: {result['message']}\n", "pass")
                self.log(f"Path: {result['path']}  (README.md updated)\n", "muted")
                if result.get("pushed"):
                    self.log("Pushed to remote.\n", "pass")
                else:
                    self.log(f"Push failed: {result.get('push_error', 'unknown')}\n", "fail")
            self.refresh_streak()
            self._refresh_practice_after_solve()
            self._refresh_stats()
            self._refresh_refresh_tab()
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
