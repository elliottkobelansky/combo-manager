"""Several computers on one data folder (kept in sync by OneDrive, SharePoint, Dropbox, a network drive...). Nothing
here depends on which: on a folder only this computer uses, it all still works and simply never finds anything.

    lock file      'AppFiles/in_use.json' says which computer has the app open on this folder; a second computer is
                   told and can open it anyway (it takes the folder over, and the first is told when it next checks)
    safe writes    write_text: a temp file renamed over the old one, so a crash or a sync never leaves half a file
    read-only      the app's own files (AppFiles' JSON, the exports) are left read-only, so they're opened, not edited,
                   by hand (the exports' sheets are protected too); the app makes them writable just to save them
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
import shutil
import socket
import stat
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from data_folder import APP_DATA_FILES, EXPORT_FILES, EXPORTS, TOP_FILES, app_data, lock_path
REFRESH = 3 * 60             # seconds between "still here" updates of the lock file
STALE = 15 * 60              # a lock not updated for this long is left over (a crash, a computer put to sleep)


# ---------------------------------------------------------------- safe writes and fingerprints

WRITE = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH


def make_writable(path):
    """Before replacing or deleting one of the app's read-only files (Windows refuses both while it's read-only)."""
    try:
        mode = os.stat(path).st_mode
        if not mode & stat.S_IWUSR:
            os.chmod(path, mode | stat.S_IWUSR)
    except OSError:
        pass


def make_read_only(path):
    """Best effort: a file system that can't do it just leaves the file as it is."""
    try:
        os.chmod(path, os.stat(path).st_mode & ~WRITE)
    except OSError:
        pass


@contextmanager
def read_only_after(path):
    """For a file written in place (the PDFs): writable while it's written, read-only after."""
    make_writable(path)
    yield
    make_read_only(path)


def remove(path):
    """Deletes a file or a folder, read-only files in it included."""
    path = Path(path)
    if path.is_dir() and not path.is_symlink():
        for p in path.rglob("*"):
            make_writable(p)
        shutil.rmtree(path)
    else:
        make_writable(path)
        path.unlink()


def write_text(path, text, read_only=False):
    """Writes text to path through a temp file next to it, then renames it over the old one (all or nothing).
    read_only: one of the app's own files, left read-only."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        make_writable(path)
        os.replace(tmp, path)
        if read_only:
            make_read_only(path)
    finally:
        tmp.unlink(missing_ok=True)


def save_workbook(wb, path):
    """An export: openpyxl's wb.save, through a temp file renamed over the old one; its sheets protected (no password:
    looking, copying, filtering and sorting still work) and the file read-only. PermissionError: open in Excel."""
    path = Path(path)
    for ws in wb.worksheets:
        ws.protection.sheet = True
        ws.protection.autoFilter = ws.protection.sort = False      # (False = allowed)
    tmp = path.with_name(f".{path.stem}.{os.getpid()}.tmp{path.suffix}")
    try:
        wb.save(tmp)
        make_writable(path)
        os.replace(tmp, path)
        make_read_only(path)
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

RUN = uuid.uuid4().hex       # this run of the app: its lock is recognised even if the computer's name changes


def me():
    return {"computer": socket.gethostname(), "user": getpass.getuser(), "pid": os.getpid(), "run": RUN}


def _is_me(lock):
    if "run" in lock:
        return lock["run"] == RUN
    m = me()
    return lock.get("computer") == m["computer"] and lock.get("pid") == m["pid"]


def _gone(lock):
    """A lock left by an app on this computer that isn't running any more (it crashed or was force-quit)."""
    if lock.get("computer") != socket.gethostname() or not isinstance(lock.get("pid"), int):
        return False
    pid = lock["pid"]
    if os.name == "nt":                                   # (os.kill would end the process on Windows)
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)             # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ctypes.GetLastError() != 5             # 5: access denied, so it's there
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value != 259             # 259: still running
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        pass
    return False


def read_lock(folder):
    try:
        lock = json.loads(lock_path(folder).read_text(encoding="utf-8"))
        return lock if isinstance(lock, dict) else None
    except (OSError, ValueError):
        return None


def holder(folder):
    """The lock of another app window that has this folder open now (not left over), else None."""
    lock = read_lock(folder)
    if not lock or _is_me(lock) or time.time() - lock.get("seen", 0) > STALE or _gone(lock):
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
    if lock and not _is_me(lock) and time.time() - lock.get("seen", 0) <= STALE and not _gone(lock):
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
    for where, names in ((Path(folder), TOP_FILES + EXPORT_FILES), (Path(folder) / EXPORTS, EXPORT_FILES),
                         (app_data(folder), APP_DATA_FILES)):
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
