"""Backups of the data folder: one zip with everything in it (the spreadsheets, App data with the settings, combo
numbers, .bak copies and Schedule backups, and Archive), plus backup-info.json saying when and where it was made.
For when the computer, or the data folder, is lost: install the program again and restore the zip into a new folder.

    create_backup   the data folder -> a zip, written through a temp file renamed at the end (all or nothing)
    read_backup     checks a zip is one of ours and whole; -> its backup-info
    restore_backup  a zip -> a new folder (never into a folder that has things in it: nothing is overwritten)

Standard library only.
"""
import getpass
import json
import os
import shutil
import socket
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from data_folder import APP_DATA, APPROVALS_FILE, CONFLICTS_FILE, LOCK_FILE, app_data, usual_inputs

INFO = "backup-info.json"
PREFIX = "Combo Scheduler backup"


class BackupError(ValueError):
    """Not a backup, a damaged one, or one that can't be restored there."""


def backup_name(now=None):
    """'Combo Scheduler backup 2026-10-06 1405.zip'"""
    return f"{PREFIX} {(now or datetime.now()):%Y-%m-%d %H%M}.zip"


def _left_out(rel):
    """The lock file, half-written temp files, hidden files and earlier backups saved in the folder."""
    name = rel.name
    return (name == LOCK_FILE or name.startswith(".") or name.endswith(".tmp")
            or (name.startswith(PREFIX) and name.endswith(".zip")))


def create_backup(folder, dest, inputs=None):
    """Zips the data folder into dest. inputs: {"approvals": path, "conflicts": path}, the input files actually read
    (app_config.input_files); one picked from outside the data folder goes in under its usual name, so the restored
    folder reads it without picking it again. Returns how many files went in."""
    folder, dest = Path(folder), Path(dest)
    app_data(folder)                                  # an old-layout folder is tidied first
    files = {}
    for p in sorted(folder.rglob("*")):
        rel = p.relative_to(folder)
        if p.is_file() and not any(_left_out(Path(part)) for part in rel.parts):
            files[rel.as_posix()] = p
    usual = {"approvals": APPROVALS_FILE, "conflicts": CONFLICTS_FILE}
    outside = {}
    for which, path in (inputs or {}).items():
        path = Path(path)
        if path.is_file() and path != usual_inputs(folder)[which]:
            files[usual[which]] = path
            outside[which] = str(path)
    info = {"made": datetime.now().isoformat(timespec="seconds"), "computer": socket.gethostname(),
            "user": getpass.getuser(), "folder": str(folder), "files": len(files), "inputs from": outside}
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.tmp")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(INFO, json.dumps(info, indent=2, ensure_ascii=False) + "\n")
            for name, p in files.items():
                zf.write(p, name)
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    return len(files)


def read_backup(path):
    """The zip's backup-info (made, computer, files, ...) and what it holds: semester (its settings'), schedule (the
    semester of its schedule, or None), past (the semesters in its Archive). Raises BackupError if it isn't a whole
    backup."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if INFO not in names and not any(n.startswith(APP_DATA + "/") for n in names):
                raise BackupError(f"{Path(path).name} isn't a Combo Scheduler backup.")
            bad = [n for n in names if PurePosixPath(n).is_absolute() or ".." in PurePosixPath(n).parts or ":" in n]
            if bad:
                raise BackupError(f"{Path(path).name} has files that would land outside the folder: {bad[0]}")
            damaged = zf.testzip()
            if damaged:
                raise BackupError(f"{Path(path).name} is damaged ({damaged} can't be read).")
            try:
                info = json.loads(zf.read(INFO)) if INFO in names else {}
            except ValueError:
                info = {}

            def inside(name, key):
                try:
                    return json.loads(zf.read(f"{APP_DATA}/{name}")).get(key) if f"{APP_DATA}/{name}" in names else None
                except (ValueError, AttributeError):
                    return None
            past = sorted({PurePosixPath(n).parts[1] for n in names if n.startswith("Archive/")
                           and len(PurePosixPath(n).parts) > 2})
            return {**info, "files": len([n for n in names if n != INFO and not n.endswith("/")]),
                    "semester": inside("settings.json", "semester_name"),
                    "schedule": inside("schedule.json", "semester") or (
                        "(old format)" if "Schedule.xlsx" in names else None), "past": past}
    except (zipfile.BadZipFile, OSError) as e:
        raise BackupError(f"Can't read {Path(path).name} as a backup ({e}).")


def new_folder(parent, name):
    """parent/name, or 'name (2)', 'name (3)', ... when that's taken."""
    dest, n = Path(parent) / name, 2
    while dest.exists():
        dest, n = Path(parent) / f"{name} ({n})", n + 1
    return dest


def restore_backup(path, dest):
    """Unpacks the backup into dest, which must not exist yet or be empty. Unpacked next to it first and renamed at
    the end, so a failure leaves no half-restored folder. Returns dest."""
    read_backup(path)
    dest = Path(dest)
    if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
        raise BackupError(f"{dest} already has things in it: restore into a new folder.")
    work = dest.with_name(f".{dest.name}.{os.getpid()}.restoring")
    shutil.rmtree(work, ignore_errors=True)
    try:
        with zipfile.ZipFile(path) as zf:
            zf.extractall(work, [n for n in zf.namelist() if n != INFO])
        if dest.exists():
            dest.rmdir()
        os.replace(work, dest)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return dest
