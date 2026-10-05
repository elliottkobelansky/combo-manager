"""Copying text so it can be pasted anywhere, quickly, and stays pasteable after the app is closed.

On Linux, Tk's own clipboard only lasts while the app runs (the copying program has to answer every paste) and can
make pasting lag, so where the system has a clipboard tool, the text goes to it instead: pbcopy on a Mac; wl-copy,
xclip or xsel on Linux. Windows keeps whatever Tk copies by itself.
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
