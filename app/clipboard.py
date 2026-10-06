"""Copying text so it can be pasted anywhere, quickly, and stays pasteable after the app is closed.

On Linux, Tk's own clipboard only lasts while the app runs (the copying program has to answer every paste) and can
make pasting lag, so where the system has a clipboard tool, the text goes to it instead: pbcopy on a Mac; wl-copy,
xclip or xsel on Linux. Windows keeps whatever Tk copies by itself. When the text can't be kept, copy() also shows it
in a small window, selected, to copy by hand.
"""
import os
import shutil
import subprocess
import sys


def system_tools():
    """Clipboard programs to try, best first."""
    if sys.platform == "darwin":
        return [["pbcopy"]] if shutil.which("pbcopy") else []
    if sys.platform.startswith("linux"):
        wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
        cmds = [["wl-copy"]] if wayland else []
        cmds += [["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
        return [c for c in cmds if shutil.which(c[0])]
    return []


def copy_text(widget, text):
    """Puts text on the clipboard. Returns True if it will stay pasteable after the app closes.
    When a system tool is there, only the tool holds the text: Tk then never has to answer paste requests itself,
    which can make pasting into other programs lag on Linux."""
    for cmd in system_tools():
        try:
            subprocess.run(cmd, input=text, text=True, timeout=5, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except (OSError, subprocess.SubprocessError):
            continue                                  # try the next one, then Tk's own clipboard
    widget.clipboard_clear()
    widget.clipboard_append(text)
    widget.update()
    return sys.platform.startswith("win")


def copy(widget, text, title, palette=None):
    """Copies text (copy_text); when it won't stay pasteable, also shows it to copy by hand. title: what was copied,
    e.g. '12 student emails for Tue Oct 13'."""
    if not copy_text(widget, text):
        show_text(widget, title, text, palette or {})


def show_text(widget, title, text, palette):
    """Shows text in a small window, already selected, to copy by hand."""
    import tkinter as tk
    from tkinter import ttk
    win = tk.Toplevel(widget)
    win.title("Copied: " + title)
    win.transient(widget.winfo_toplevel())
    box = ttk.Frame(win, padding=14)
    box.pack(fill="both", expand=True)
    ttk.Label(box, text="Copied. If pasting doesn't work, select the text below (it's already selected) and press "
                        "Ctrl+C (Cmd+C on a Mac).", wraplength=520, justify="left").pack(anchor="w")
    txt = tk.Text(box, wrap="word", height=min(18, max(4, text.count("\n") + 2)), width=80, relief="flat",
                  background=palette.get("panel", "white"), foreground=palette.get("text", "black"), padx=8, pady=6)
    txt.insert("1.0", text)
    txt.tag_add("sel", "1.0", "end")
    txt.pack(fill="both", expand=True, pady=10)
    txt.focus_set()
    ttk.Button(box, text="Close", style="Accent.TButton", command=win.destroy).pack(anchor="e")
