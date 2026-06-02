"""A lightweight in-app code editor (Tkinter Text + niceties).

Not a full IDE -- but it gives a monospace editor with a line-number gutter,
tab-to-spaces, auto-indent, and simple syntax highlighting, which is plenty for
editing a single LeetCode solution file without leaving the app.
"""

from __future__ import annotations

import keyword
import re
import tkinter as tk
from tkinter import font as tkfont

# Editor palette (dark)
BG = "#1e1e2e"
FG = "#e6e6e6"
GUTTER_BG = "#181825"
GUTTER_FG = "#6c7086"
CUR_LINE = "#2a2a3c"

COLORS = {
    "keyword": "#c792ea",
    "string": "#c3e88d",
    "comment": "#676e95",
    "number": "#f78c6c",
    "def": "#82aaff",
    "builtin": "#ffcb6b",
}

_PY_BUILTINS = {
    "print", "len", "range", "enumerate", "list", "dict", "set", "tuple",
    "int", "str", "float", "bool", "sorted", "min", "max", "sum", "abs",
    "map", "filter", "zip", "self", "None", "True", "False", "Optional",
    "List", "Dict", "Set", "Tuple",
}
_JS_KEYWORDS = {
    "var", "let", "const", "function", "return", "if", "else", "for", "while",
    "do", "switch", "case", "break", "continue", "new", "class", "extends",
    "this", "typeof", "instanceof", "null", "undefined", "true", "false",
}


class CodeEditor(tk.Frame):
    def __init__(self, parent: tk.Misc, language: str = "python", **kw) -> None:
        super().__init__(parent, **kw)
        self.language = language
        self.font = tkfont.Font(family="Consolas", size=11)

        self.gutter = tk.Canvas(self, width=46, bg=GUTTER_BG, highlightthickness=0)
        self.gutter.pack(side="left", fill="y")

        self.text = tk.Text(
            self, wrap="none", undo=True, bg=BG, fg=FG, insertbackground=FG,
            relief="flat", font=self.font, tabs=("1c",), padx=6, pady=4,
            selectbackground="#3a3a5c", spacing1=1, spacing3=1)
        self.text.pack(side="left", fill="both", expand=True)

        self.vsb = tk.Scrollbar(self, command=self._on_scroll_drag)
        self.vsb.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=self._on_text_scroll)

        for tag, col in COLORS.items():
            self.text.tag_configure(tag, foreground=col)
        self.text.tag_configure("curline", background=CUR_LINE)

        self.text.bind("<KeyRelease>", self._on_key_release)
        self.text.bind("<Tab>", self._on_tab)
        self.text.bind("<Shift-Tab>", self._on_shift_tab)
        self.text.bind("<Return>", self._on_return)
        self.text.bind("<ButtonRelease-1>", lambda e: (self._highlight_current_line(),
                                                       self._redraw_gutter()))
        self.text.bind("<Configure>", lambda e: self._redraw_gutter())
        self.text.bind("<MouseWheel>", lambda e: self.after(2, self._redraw_gutter))

        # Find + font-zoom
        self.font_size = 11
        self.text.tag_configure("find", background="#5a5a2c")
        self.text.bind("<Control-f>", lambda e: self._show_find())
        self.text.bind("<Control-equal>", lambda e: self._zoom(1))
        self.text.bind("<Control-plus>", lambda e: self._zoom(1))
        self.text.bind("<Control-minus>", lambda e: self._zoom(-1))

        self._find = tk.Frame(self, bg="#2a2a3c", bd=1, relief="solid")
        self._find_var = tk.StringVar()
        tk.Label(self._find, text="Find", bg="#2a2a3c", fg=FG,
                 font=("Segoe UI", 9)).pack(side="left", padx=(6, 2), pady=3)
        self._find_entry = tk.Entry(self._find, textvariable=self._find_var, width=22,
                                    bg=BG, fg=FG, insertbackground=FG, relief="flat")
        self._find_entry.pack(side="left", padx=2, pady=3)
        self._find_entry.bind("<Return>", lambda e: self._find_next())
        self._find_entry.bind("<Escape>", lambda e: self._hide_find())

    # -- find + zoom ---------------------------------------------------- #
    def _show_find(self) -> str:
        self._find.place(relx=1.0, x=-18, y=6, anchor="ne")
        self._find_entry.focus_set()
        self._find_entry.select_range(0, "end")
        return "break"

    def _hide_find(self) -> str:
        self._find.place_forget()
        self.text.tag_remove("find", "1.0", "end")
        self.text.focus_set()
        return "break"

    def _find_next(self) -> str:
        term = self._find_var.get()
        if not term:
            return "break"
        self.text.tag_remove("find", "1.0", "end")
        idx = "1.0"
        first = None
        while True:
            idx = self.text.search(term, idx, stopindex="end", nocase=1)
            if not idx:
                break
            end = f"{idx}+{len(term)}c"
            self.text.tag_add("find", idx, end)
            if first is None:
                first = idx
            idx = end
        nxt = self.text.search(term, "insert", stopindex="end", nocase=1) or first
        if nxt:
            self.text.mark_set("insert", f"{nxt}+{len(term)}c")
            self.text.see(nxt)
        return "break"

    def _zoom(self, delta: int) -> str:
        self.font_size = max(8, min(24, self.font_size + delta))
        self.font.configure(size=self.font_size)
        self._redraw_gutter()
        return "break"

    # -- public API ----------------------------------------------------- #
    def get_code(self) -> str:
        return self.text.get("1.0", "end-1c")

    def set_code(self, code: str, language: str | None = None) -> None:
        if language:
            self.language = language
        self.text.delete("1.0", "end")
        self.text.insert("1.0", code)
        self.text.edit_reset()  # clear undo history
        self.highlight_all()
        self._redraw_gutter()
        self._highlight_current_line()

    def focus_editor(self) -> None:
        self.text.focus_set()

    # -- scrolling / gutter --------------------------------------------- #
    def _on_text_scroll(self, *args) -> None:
        self.vsb.set(*args)
        self._redraw_gutter()

    def _on_scroll_drag(self, *args) -> None:
        self.text.yview(*args)
        self._redraw_gutter()

    def _redraw_gutter(self) -> None:
        self.gutter.delete("all")
        i = self.text.index("@0,0")
        while True:
            info = self.text.dlineinfo(i)
            if info is None:
                break
            y = info[1]
            line_no = i.split(".")[0]
            self.gutter.create_text(40, y, anchor="ne", text=line_no,
                                    fill=GUTTER_FG, font=self.font)
            i = self.text.index(f"{i}+1line")
            if int(line_no) > 100000:
                break

    # -- editing behaviour ---------------------------------------------- #
    def _on_tab(self, _event) -> str:
        self.text.insert("insert", "    ")
        return "break"

    def _on_shift_tab(self, _event) -> str:
        line_start = self.text.index("insert linestart")
        line = self.text.get(line_start, f"{line_start} lineend")
        strip = len(line) - len(line.lstrip(" "))
        remove = min(4, strip)
        if remove:
            self.text.delete(line_start, f"{line_start}+{remove}c")
        return "break"

    def _on_return(self, _event) -> str:
        line_start = self.text.index("insert linestart")
        line = self.text.get(line_start, "insert")
        indent = re.match(r"[ \t]*", line).group(0)
        if line.rstrip().endswith(":"):
            indent += "    "
        self.text.insert("insert", "\n" + indent)
        self.after(1, self._redraw_gutter)
        return "break"

    def _on_key_release(self, event) -> None:
        if event.keysym in ("Up", "Down", "Left", "Right", "Home", "End",
                            "Prior", "Next"):
            self._highlight_current_line()
            return
        self.highlight_all()
        self._highlight_current_line()
        self._redraw_gutter()

    # -- highlighting ---------------------------------------------------- #
    def _highlight_current_line(self) -> None:
        self.text.tag_remove("curline", "1.0", "end")
        self.text.tag_add("curline", "insert linestart", "insert lineend+1c")
        self.text.tag_lower("curline")

    def highlight_all(self) -> None:
        for tag in COLORS:
            self.text.tag_remove(tag, "1.0", "end")
        code = self.text.get("1.0", "end-1c")

        def add(tag, start_idx, end_idx):
            self.text.tag_add(tag, f"1.0+{start_idx}c", f"1.0+{end_idx}c")

        # strings (triple first, then single/double), then comments override
        for m in re.finditer(r'(""".*?"""|\'\'\'.*?\'\'\'|"(?:[^"\\]|\\.)*"'
                             r"|'(?:[^'\\]|\\.)*')", code, re.S):
            add("string", m.start(), m.end())

        comment_re = r"#[^\n]*" if self.language == "python" else r"//[^\n]*"
        for m in re.finditer(comment_re, code):
            add("comment", m.start(), m.end())

        for m in re.finditer(r"\b\d+(?:\.\d+)?\b", code):
            add("number", m.start(), m.end())

        kws = (keyword.kwlist if self.language == "python" else list(_JS_KEYWORDS))
        for m in re.finditer(r"\b([A-Za-z_]\w*)\b", code):
            word = m.group(1)
            if word in kws:
                add("keyword", m.start(), m.end())
            elif word in _PY_BUILTINS:
                add("builtin", m.start(), m.end())

        for m in re.finditer(r"\b(?:def|class|function)\s+([A-Za-z_]\w*)", code):
            add("def", m.start(1), m.end(1))
