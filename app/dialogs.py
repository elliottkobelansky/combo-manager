"""The app's own pop-ups, in its look (colours, dark mode, text size), used instead of tkinter.messagebox: a heading,
the message, and buttons named for what they do. Same calls as messagebox, plus the button names:

    dialogs.showinfo / showwarning / showerror(title, message)
    dialogs.askyesno(title, message, yes="Unlock", no="Keep locked", default="no", icon="warning")  -> True / False
    dialogs.askyesnocancel(title, message, yes=..., no=..., cancel=...)                              -> True / False / None
    dialogs.askokcancel(title, message, ok=..., cancel=...)                                          -> True / False
    dialogs.askstring(title, message, initialvalue="", ok="OK")                     -> the text typed / None (cancelled)

Enter = the default button (blue), Escape or closing the window = cancel (No where there's no Cancel).
"""
import tkinter as tk
from tkinter import ttk

import theme

MARKS = {"warning": ("⚠", "warn"), "error": ("✖", "bad")}   # icon -> (mark, palette colour)


def grab(win, tries=80):
    """Makes win modal; until it's on screen (Linux refuses to grab a window that isn't shown yet), tries again."""
    try:
        win.grab_set()
    except tk.TclError:
        if tries and win.winfo_exists():
            win.after(25, grab, win, tries - 1)


def _ask(title, message, buttons, default, cancel, icon=None, parent=None, entry=None, choices=None):
    """buttons: [(label, value)], left to right; default / cancel: the values for Enter / Escape. entry: a text box
    under the message, with this text in it; the default button then returns what's typed. choices: the text box
    is a dropdown of these (anything can still be typed)."""
    root = parent.winfo_toplevel() if parent else tk._default_root
    p = theme.PALETTE
    win = tk.Toplevel(root)
    win.withdraw()
    win.title(title)
    win.transient(root)
    win.resizable(False, False)
    win.configure(background=p["bg"])
    result = [cancel]

    def close(value):
        result[0] = box_.get() if box_ is not None and value == default else value
        win.grab_release()
        win.destroy()
    box = ttk.Frame(win, padding=(22, 20, 22, 16))
    box.pack(fill="both", expand=True)
    head = ttk.Frame(box)
    head.pack(fill="x")
    if icon in MARKS:
        mark, colour = MARKS[icon]
        ttk.Label(head, text=mark, foreground=p[colour], font=(theme.ui_font(), theme.size(16))).pack(
            side="left", anchor="n", padx=(0, 10))
    ttk.Label(head, text=title, style="CardTitle.TLabel", wraplength=theme.size(440)).pack(side="left", anchor="w")
    ttk.Label(box, text=message.strip(), wraplength=theme.size(470), justify="left").pack(anchor="w", pady=(10, 0))
    box_ = None
    if entry is not None:
        box_ = ttk.Combobox(box, values=choices, width=16) if choices else ttk.Entry(box, width=52)
        box_.insert(0, entry)
        box_.select_range(0, "end")
        box_.pack(anchor="w", fill="x" if not choices else None, pady=(10, 0))
    bar = ttk.Frame(box)
    bar.pack(fill="x", pady=(18, 0))
    for label, value in reversed(buttons):            # right-aligned, in the given order
        b = ttk.Button(bar, text=label, command=lambda v=value: close(v),
                       style="Accent.TButton" if value == default else "TButton")
        b.pack(side="right", padx=(8, 0))
        if value == default and box_ is None:
            b.focus_set()
    if box_ is not None:
        box_.focus_set()
    win.bind("<Return>", lambda _: close(default))
    win.bind("<KP_Enter>", lambda _: close(default))
    win.bind("<Escape>", lambda _: close(cancel))
    win.protocol("WM_DELETE_WINDOW", lambda: close(cancel))
    win.update_idletasks()                            # centred over the app's window
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    x = root.winfo_rootx() + max(0, (root.winfo_width() - w) // 2)
    y = root.winfo_rooty() + max(0, (root.winfo_height() - h) // 3)
    win.geometry(f"+{x}+{y}")
    win.deiconify()
    win.lift()
    grab(win)
    root.wait_window(win)
    return result[0]


def showinfo(title, message, parent=None, **_):
    _ask(title, message, [("OK", True)], True, None, "info", parent)


def showwarning(title, message, parent=None, **_):
    _ask(title, message, [("OK", True)], True, None, "warning", parent)


def showerror(title, message, parent=None, **_):
    _ask(title, message, [("OK", True)], True, None, "error", parent)


def askyesno(title, message, yes="Yes", no="No", default="yes", icon=None, parent=None, **_):
    return bool(_ask(title, message, [(no, False), (yes, True)], default != "no", False, icon, parent))


def askyesnocancel(title, message, yes="Yes", no="No", cancel="Cancel", default="yes", icon=None, parent=None, **_):
    return _ask(title, message, [(cancel, None), (no, False), (yes, True)],
                {"yes": True, "no": False, "cancel": None}.get(default, True), None, icon, parent)


def askokcancel(title, message, ok="OK", cancel="Cancel", default="ok", icon=None, parent=None, **_):
    return bool(_ask(title, message, [(cancel, False), (ok, True)], default != "cancel", False, icon, parent))


def askstring(title, message, initialvalue="", ok="OK", parent=None, choices=None, **_):
    """A line of text: what's typed (or picked from choices), or None when cancelled."""
    return _ask(title, message, [("Cancel", None), (ok, True)], True, None, None, parent, entry=initialvalue or "",
                choices=choices)
