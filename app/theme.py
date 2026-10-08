"""Look of the app: Tk's built-in 'clam' theme, recoloured in light or dark. (The Sun Valley theme looked a little
smoother but drew everything from images, which made every tab switch 3 to 6 times slower.)

apply(root, mode) sets the look and returns the palette (colours for the parts ttk doesn't draw: the output panel,
its highlighted lines, hint text, menus and the calendar pop-up).
"""
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

PALETTES = {
    "light": dict(bg="#F7F7F9", panel="#FFFFFF", text="#1C1C1E", muted="#6B6B76", border="#D9D9E0",
                  warn="#B25E00", bad="#D11A2A", good="#1F8A4C", accent="#005FB8", accent_text="#FFFFFF",
                  accent_hover="#0A6CCB", accent_fg="#005FB8", band="#EEF1F6", hover="#ECEDF2"),
    "dark": dict(bg="#1C1C1C", panel="#232326", text="#ECECF1", muted="#A0A0AB", border="#3A3A40",
                 warn="#F0A54A", bad="#FF6B6B", good="#4CD787", accent="#005FB8", accent_text="#FFFFFF",
                 accent_hover="#0A6CCB", accent_fg="#4DA3F0", band="#2C2D33", hover="#2E2F35"),
}


PALETTE = PALETTES["light"]                           # the colours in use (set by apply)


def ui_font():
    if sys.platform.startswith("win"):
        return "Segoe UI"
    if sys.platform == "darwin":
        return "Helvetica Neue"
    return tkfont.nametofont("TkDefaultFont").actual("family")


def mono_font():
    if sys.platform.startswith("win"):
        return "Cascadia Mono" if "Cascadia Mono" in tkfont.families() else "Consolas"
    if sys.platform == "darwin":
        return "Menlo"
    return tkfont.nametofont("TkFixedFont").actual("family")


SCALE = 1.0                                           # text size (1.0 = normal), set by apply()
SCALES = [0.85, 1.0, 1.15, 1.3, 1.5, 1.75]            # the steps of the A- / A+ buttons
_BASE_SIZES = {}                                      # named font -> its size at 100%


def size(points):
    """A font size (or pixel width) at the current text size."""
    return max(6, round(points * SCALE))


def _scale_named_fonts(root):
    """Resizes Tk's named fonts (TkDefaultFont, TkHeadingFont, ...): almost all text uses them."""
    family = ui_font()
    for name in tkfont.names(root):
        f = tkfont.nametofont(name, root=root)
        base = _BASE_SIZES.setdefault(name, f.actual("size") if f.cget("size") == 0 else f.cget("size"))
        new = round(base * SCALE) or (1 if base > 0 else -1)
        f.configure(size=new, **({"family": family} if name != "TkFixedFont" and name.startswith("Tk") else {}))


def apply(root, mode="light", scale=None):
    global SCALE
    if scale:
        SCALE = scale
    global PALETTE
    mode = mode if mode in PALETTES else "light"
    p = PALETTE = PALETTES[mode]
    style = ttk.Style(root)
    style.theme_use("clam")
    _scale_named_fonts(root)
    family = ui_font()
    bg, panel, text, muted, border, accent = p["bg"], p["panel"], p["text"], p["muted"], p["border"], p["accent"]
    style.configure(".", background=bg, foreground=text, fieldbackground=panel, bordercolor=border,
                    lightcolor=bg, darkcolor=bg, troughcolor=bg, selectbackground=accent,
                    selectforeground=p["accent_text"], insertcolor=text, focuscolor=accent, arrowcolor=text)
    style.map(".", foreground=[("disabled", muted)])
    # buttons: flat, a light border; the accent ones solid blue
    style.configure("TButton", padding=(size(12), size(5)), background=panel, bordercolor=border,
                    lightcolor=panel, darkcolor=panel, focusthickness=0)
    style.map("TButton", background=[("pressed", border), ("active", p["hover"])],
              lightcolor=[("pressed", border), ("active", p["hover"])],
              darkcolor=[("pressed", border), ("active", p["hover"])])
    style.configure("Accent.TButton", background=accent, foreground=p["accent_text"], bordercolor=accent,
                    lightcolor=accent, darkcolor=accent)
    style.map("Accent.TButton", background=[("disabled", border), ("pressed", accent), ("active", p["accent_hover"])],
              lightcolor=[("disabled", border), ("active", p["accent_hover"])],
              darkcolor=[("disabled", border), ("active", p["accent_hover"])],
              bordercolor=[("disabled", border), ("active", p["accent_hover"])],
              foreground=[("disabled", muted)])
    style.configure("Big.Accent.TButton", font=(family, size(11), "bold"), padding=(size(18), size(8)))
    # fields
    for w in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(w, fieldbackground=panel, background=panel, bordercolor=border, lightcolor=panel,
                        darkcolor=panel, padding=size(4))
        style.map(w, bordercolor=[("focus", accent)], lightcolor=[("focus", panel)])
    style.map("TCombobox", fieldbackground=[("readonly", panel)], selectbackground=[("readonly", panel)],
              selectforeground=[("readonly", text)], background=[("active", p["hover"])])
    root.option_add("*TCombobox*Listbox.background", panel)
    root.option_add("*TCombobox*Listbox.foreground", text)
    root.option_add("*TCombobox*Listbox.selectBackground", accent)
    root.option_add("*TCombobox*Listbox.selectForeground", p["accent_text"])
    for w in ("TCheckbutton", "TRadiobutton"):
        style.configure(w, background=bg, indicatorbackground=panel, indicatorforeground=p["accent_fg"],
                        upperbordercolor=muted, lowerbordercolor=muted, indicatorsize=size(15),
                        indicatormargin=(0, 0, size(6), 0))
        style.map(w, background=[("active", bg)], indicatorbackground=[("pressed", p["hover"])])
    # tabs: the open one white with blue text
    style.configure("TNotebook", background=bg, bordercolor=border, lightcolor=bg, darkcolor=bg, tabmargins=(0, 0, 0, 0))
    for w in ("TNotebook.Tab", "TButton", "TCheckbutton", "TRadiobutton"):   # no dotted box after a click
        style.layout(w, _without_focus(style.layout(w)))
    style.configure("TNotebook.Tab", padding=(size(14), size(6)), background=bg, bordercolor=border, lightcolor=bg,
                    darkcolor=bg, foreground=muted)
    style.map("TNotebook.Tab", background=[("selected", panel), ("active", p["hover"])],
              foreground=[("selected", p["accent_fg"]), ("active", text)], lightcolor=[("selected", panel)],
              expand=[("selected", (0, 0, 0, 0))])
    # tables
    style.configure("Treeview", background=panel, fieldbackground=panel, foreground=text, bordercolor=border,
                    lightcolor=panel, darkcolor=panel, rowheight=size(26))
    style.map("Treeview", background=[("selected", accent)], foreground=[("selected", p["accent_text"])])
    style.configure("Treeview.Heading", background=bg, foreground=muted, bordercolor=border, lightcolor=bg,
                    darkcolor=bg, relief="flat", padding=(size(6), 2, 2, 2), font=(family, size(9), "bold"))
    style.map("Treeview.Heading", background=[("active", p["hover"])])
    style.configure("TScrollbar", background=border, troughcolor=bg, bordercolor=bg, lightcolor=border,
                    darkcolor=border, arrowcolor=muted, gripcount=0)
    style.map("TScrollbar", background=[("active", muted)])
    style.configure("Card.TFrame", background=bg, bordercolor=border, relief="solid", borderwidth=1)
    style.configure("Fold.TButton", anchor="w", background=bg, bordercolor=border, lightcolor=bg, darkcolor=bg,
                    foreground=muted)
    style.map("Fold.TButton", background=[("active", p["hover"])], lightcolor=[("active", p["hover"])],
              darkcolor=[("active", p["hover"])])
    style.configure("TSeparator", background=border)
    # text styles
    style.configure("Title.TLabel", font=(family, size(18), "bold"))
    style.configure("Sub.TLabel", font=(family, size(10)), foreground=muted)
    style.configure("Hint.TLabel", font=(family, size(9)), foreground=muted)
    style.configure("CardTitle.TLabel", font=(family, size(12), "bold"))
    style.configure("Link.TLabel", font=(family, size(11)), foreground=p["accent_fg"])
    style.configure("Warn.TLabel", foreground=p["warn"])
    style.configure("Step.TLabel", font=(family, size(12), "bold"), foreground=p["accent_fg"])
    root.configure(background=bg)
    root.option_add("*Toplevel.background", bg)
    for w in _toplevels(root):                         # windows already open (a theme switch)
        w.configure(background=bg)
    return p


def _without_focus(layout):
    """A ttk layout minus its '.focus' elements (the dotted box drawn around a clicked tab, button or checkbox);
    their children move up a level."""
    out = []
    for name, opts in layout:
        children = _without_focus(opts.get("children", []))
        if name.endswith(".focus"):
            out += children
        else:
            out.append((name, {**opts, "children": children} if children else
                        {k: v for k, v in opts.items() if k != "children"}))
    return out


def _toplevels(widget):
    out = []
    for child in widget.winfo_children():
        if child.winfo_class() == "Toplevel":
            out.append(child)
        out += _toplevels(child)
    return out


def scrolled_tree(parent, spec, **kw):
    """A Treeview in a frame with a vertical scrollbar, and a horizontal one that only shows when the columns don't
    fit. spec = [(column, heading, width, stretch)] ("#0" = the tree column); a column never gets narrower than its
    width (times the text size), so a narrow window scrolls instead of squashing the text. Returns (frame, tree)."""
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, columns=[c for c, *_ in spec if c != "#0"], **kw)
    vbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    hbar = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)

    def xset(lo, hi):
        if float(lo) <= 0 and float(hi) >= 1:
            hbar.grid_remove()
        else:
            hbar.grid()
        hbar.set(lo, hi)
    tree.configure(yscrollcommand=vbar.set, xscrollcommand=xset)
    tree.grid(row=0, column=0, sticky="nsew")
    vbar.grid(row=0, column=1, sticky="ns")
    hbar.grid(row=1, column=0, sticky="ew")
    hbar.grid_remove()
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    tree.spec = spec
    for col, text, _, _ in spec:
        tree.heading(col, text=text, anchor="w")
    size_columns(tree)
    return frame, tree


def size_columns(tree):
    """(Re)sets a scrolled_tree's column widths for the current text size."""
    for col, _, width, stretch in tree.spec:
        tree.column(col, width=size(width), minwidth=size(width), stretch=stretch, anchor="w")


def in_background(widget, work, done):
    """Runs work() in a thread, then done(result) back in the window's thread. A calculation of a few tenths of a
    second on the window's own thread stops it drawing, which a Mac shows as a black window."""
    import queue
    import threading
    results = queue.Queue()

    def run():
        try:
            results.put((True, work()))
        except Exception as e:                        # passed on, so it shows up like any other error
            results.put((False, e))
    threading.Thread(target=run, daemon=True).start()

    def poll():
        try:
            ok, value = results.get_nowait()
        except queue.Empty:
            widget.after(30, poll)
            return
        if not ok:
            raise value
        done(value)
    widget.after(30, poll)


def popup(menu, x, y):
    """Shows a pop-up menu at (x, y). It keeps Tk's mouse grab, so on Linux a click anywhere else closes it (the
    usual 'try: tk_popup / finally: grab_release' recipe left it stuck open there); Escape closes it too."""
    menu.bind("<Escape>", lambda _: menu.unpost())
    menu.tk_popup(x, y)


RIGHT_CLICK = ("<Button-3>", "<Button-2>", "<Control-Button-1>")   # right-click (Mac: also Ctrl-click)


def bind_right_click(widget, handler):
    """Right-click anywhere on a tab: the widget and everything in it, except text boxes (typing)."""
    if not isinstance(widget, (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox, ttk.Spinbox)):
        for ev in RIGHT_CLICK:
            widget.bind(ev, handler)
    for child in widget.winfo_children():
        bind_right_click(child, handler)


def calendar_colors(p):
    """Keyword arguments for tkcalendar.Calendar so the pop-up matches the theme."""
    return dict(background=p["accent"], foreground=p["accent_text"], headersbackground=p["panel"],
                headersforeground=p["muted"], normalbackground=p["panel"], normalforeground=p["text"],
                weekendbackground=p["panel"], weekendforeground=p["text"], othermonthbackground=p["bg"],
                othermonthforeground=p["muted"], othermonthwebackground=p["bg"], othermonthweforeground=p["muted"],
                selectbackground=p["accent"], selectforeground=p["accent_text"], bordercolor=p["border"],
                font=(ui_font(), size(10)))


class ResultsBox(ttk.Frame):
    """A fold-out box for what a check or a run printed: just a title bar until something runs (show())."""

    def __init__(self, parent, title, height=12):
        super().__init__(parent)
        self.title, self.is_open, self.options = title, False, []
        self.head = ttk.Frame(self)                   # the title bar (room on its right for an option: add_option)
        self.head.pack(fill="x")
        self.toggle = ttk.Button(self.head, style="Fold.TButton", command=lambda: self.show(not self.is_open))
        self.toggle.pack(side="left", fill="x", expand=True)
        self.body = ttk.Frame(self, style="Card.TFrame", padding=1)
        bar = ttk.Scrollbar(self.body, orient="vertical")
        bar.pack(side="right", fill="y")
        self.text = tk.Text(self.body, wrap="word", state="disabled", relief="flat", borderwidth=0,
                            highlightthickness=0, padx=14, pady=10, height=height, yscrollcommand=bar.set)
        self.text.pack(side="left", fill="both", expand=True)
        bar.configure(command=self.text.yview)
        self.show(False)

    def show(self, on=True):
        self.is_open = on
        self.toggle.configure(text=("\u25be  " if on else "\u25b8  ") + self.title)
        for w in getattr(self, "options", []):
            if on:
                w.pack(side="right", padx=(10, 4))
            else:
                w.pack_forget()
        if on:
            self.body.pack(fill="both", expand=True)
        else:
            self.body.pack_forget()

    def add_option(self, text, var):
        """A tick on the right of the title bar (e.g. 'All stats'), shown while the box is open."""
        self.options.append(ttk.Checkbutton(self.head, text=text, variable=var))
        self.show(self.is_open)

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


def search_box(parent, var, width=28):
    """A search field with a Clear button next to it (shown while there's text); Escape in the field clears it too.
    Returns the frame to pack."""
    frame = ttk.Frame(parent)
    entry = ttk.Entry(frame, textvariable=var, width=width)
    entry.pack(side="left")
    clear = ttk.Button(frame, text="Clear", command=lambda: (var.set(""), entry.focus_set()))
    entry.bind("<Escape>", lambda _: var.set(""))

    def show(*_):
        if var.get():
            clear.pack(side="left", padx=(6, 0))
        else:
            clear.pack_forget()
    var.trace_add("write", show)
    return frame
