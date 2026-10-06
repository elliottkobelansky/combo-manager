"""Several computers on one data folder (kept in sync by OneDrive, SharePoint, Dropbox, a network drive...). Nothing
here depends on which: on a folder only this computer uses, it all still works and simply never finds anything.

    lock file      'App data/In use.json' says which computer has the app open on this folder; a second computer is
                   told and can open it anyway (it takes the folder over, and the first is told when it next checks)
    safe writes    write_text: a temp file renamed over the old one, so a crash or a sync never leaves half a file
    fingerprints   what a file held when it was read, so a save can tell it changed on disk since (another computer
                   saved it and the sync brought it in)
    copies         a sync app's conflict copies ('Schedule-OFFICE-PC.xlsx', 'settings (1).json',
                   "Schedule (OFFICE-PC's conflicted copy).xlsx"), to point out

Standard library only: the app uses this before checking that the other packages are installed.
"""
import getpass
import hashlib
import json
import os
import re
import socket
import time
from datetime import datetime
from pathlib import Path

from data_folder import APP_DATA_FILES, TOP_FILES, app_data, lock_path
REFRESH = 3 * 60             # seconds between "still here" updates of the lock file
STALE = 15 * 60              # a lock not updated for this long is left over (a crash, a computer put to sleep)


# ---------------------------------------------------------------- safe writes and fingerprints

def write_text(path, text):
    """Writes text to path through a temp file next to it, then renames it over the old one (all or nothing)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def save_workbook(wb, path):
    """openpyxl's wb.save, through a temp file renamed over the old one. PermissionError: open in Excel."""
    path = Path(path)
    tmp = path.with_name(f".{path.stem}.{os.getpid()}.tmp{path.suffix}")
    try:
        wb.save(tmp)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def fingerprint(path):
    """What the file holds now (a hash), or None when it isn't there."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


class ChangedOnDisk(ValueError):
    """A file changed on disk since it was read: saving would overwrite someone else's changes."""


# ---------------------------------------------------------------- the lock file

def me():
    return {"computer": socket.gethostname(), "user": getpass.getuser(), "pid": os.getpid()}


def _is_me(lock):
    m = me()
    return lock.get("computer") == m["computer"] and lock.get("pid") == m["pid"]


def read_lock(folder):
    try:
        lock = json.loads(lock_path(folder).read_text(encoding="utf-8"))
        return lock if isinstance(lock, dict) else None
    except (OSError, ValueError):
        return None


def holder(folder):
    """The lock of another app window that has this folder open now (not left over), else None."""
    lock = read_lock(folder)
    if not lock or _is_me(lock) or time.time() - lock.get("seen", 0) > STALE:
        return None
    return lock


def describe(lock):
    """'OFFICE-PC (ana) since 14:05 Tue Oct 6' / 'another window on this computer since ...'."""
    t = datetime.fromtimestamp(lock.get("since", 0))
    since = f"{t:%H:%M %a %b} {t.day}"
    who = ("another window on this computer" if lock.get("computer") == socket.gethostname()
           else f"{lock.get('computer', '?')} ({lock.get('user', '?')})")
    return f"{who} since {since}"


def claim(folder):
    """Writes our lock (taking the folder over from anyone else). Best effort: a read-only folder just skips it."""
    old = read_lock(folder)
    since = old["since"] if old and _is_me(old) else time.time()
    try:
        write_text(lock_path(folder), json.dumps({**me(), "since": since, "seen": time.time()}))
    except OSError:
        pass


def refresh(folder):
    """The regular "still here": None while the lock is ours (updated); the other lock when another computer took
    the folder over meanwhile (then ours isn't written back)."""
    lock = read_lock(folder)
    if lock and not _is_me(lock) and time.time() - lock.get("seen", 0) <= STALE:
        return lock
    claim(folder)
    return None


def release(folder):
    """Removes our lock (closing the app, changing folder). Someone else's is left alone."""
    lock = read_lock(folder)
    if lock and _is_me(lock):
        try:
            lock_path(folder).unlink()
        except OSError:
            pass


# ---------------------------------------------------------------- conflict copies


def conflict_copies(folder):
    """Files that look like a sync app kept two versions of one of ours: 'Schedule-OFFICE-PC.xlsx',
    'Schedule-OFFICE-PC-2.xlsx', 'settings (1).json' (OneDrive, SharePoint, Google Drive), "Schedule (OFFICE-PC's
    conflicted copy 2026-10-06).xlsx" (Dropbox). -> [(copy, the usual file)], as paths."""
    found = []
    for where, names in ((Path(folder), TOP_FILES), (app_data(folder), APP_DATA_FILES)):
        try:
            present = [p for p in where.iterdir() if p.is_file()]
        except OSError:
            continue
        for name in names:
            stem, ext = os.path.splitext(name)
            pattern = re.compile(re.escape(stem) + r"(-[^.\\/]+| \(\d+\)| \([^()]*conflicted copy[^()]*\))"
                                 + re.escape(ext) + "$", re.IGNORECASE)
            found += [(p, where / name) for p in present if pattern.match(p.name)]
    return sorted(found)
