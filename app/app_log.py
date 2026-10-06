"""The log: what the app did, for "send this to whoever maintains it". One file per computer in the data folder,
App data/Logs/<computer>.txt (two computers on a shared folder never write the same file): every step's output,
saves (swaps, combo changes, text in a set), backups, folder changes, and every error with its details.
Kept to about LIMIT bytes (the oldest half goes). Writing it never raises: a log must not break the app.

Standard library only.
"""
import socket
import traceback
from datetime import datetime
from pathlib import Path

from data_folder import app_data

LIMIT = 1_000_000
_folder = None


def set_folder(folder):
    """The data folder to log into (None: nowhere, e.g. before one is chosen)."""
    global _folder
    _folder = Path(folder) if folder else None


def path(folder=None):
    return app_data(folder or _folder) / "Logs" / f"{socket.gethostname()}.txt"


def write(text):
    """Adds text (one or more lines) with the time."""
    if not _folder:
        return
    try:
        p = path()
        p.parent.mkdir(parents=True, exist_ok=True)
        lines = str(text).rstrip("\n").splitlines() or [""]
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {lines[0]}\n" + "".join(f"    {l}\n" for l in lines[1:]))
        if p.stat().st_size > LIMIT:                  # keep the newer half, from a line start
            text = p.read_text(encoding="utf-8")
            half = text.find("\n[", len(text) // 2)
            p.write_text(text[half + 1:] if half >= 0 else text[-LIMIT // 2:], encoding="utf-8")
    except Exception:                                 # noqa: BLE001  (never let the log break anything)
        pass


def error(context, exc=None):
    """An error with its details (the current exception, or exc)."""
    details = "".join(traceback.format_exception(exc)) if exc else traceback.format_exc()
    write(f"ERROR {context}\n{details}")
