"""Backups of the data folder: one zip with everything in it (the spreadsheets, AppFiles with the settings, combo
numbers, .bak copies and ScheduleBackups, and Archive), plus backup-info.json saying when and where it was made.

    create_backup     the data folder -> a zip, written through a temp file renamed at the end (all or nothing)
    read_backup       checks a zip is one of ours and whole; -> its backup-info and what it holds
    restore_in_place  a zip -> the data folder in use (the usual case: something went wrong, go back): it's backed up
                      first (AppFiles/BeforeRestore), and the input spreadsheets the forms write are kept, so the
                      same folder stays in use by every computer and by the flows
    restore_backup    a zip -> a new folder (when the data folder itself is lost; never into one with things in it)

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

from data_folder import (APP_DATA, APPROVALS_FILE, BEFORE_RESTORE, CONFLICTS_FILE, LOCK_FILE, LOGS, OLD_APP_DATA,
                         OLD_APPROVALS_FILE, SETTINGS_FILE, app_data, exports, usual_inputs)

INFO = "backup-info.json"
PREFIX = "ComboManager-backup"
PREFIXES = (PREFIX, "Combo Manager backup", "Combo Scheduler backup")   # (the names before 2026-10-07)
# in AppFiles: BEFORE_RESTORE, the folder as it was before each in-place restore
INPUTS = (APPROVALS_FILE, OLD_APPROVALS_FILE, CONFLICTS_FILE)   # written by the forms' flows: kept by default
KEPT_HERE = (LOCK_FILE, LOGS, BEFORE_RESTORE)         # in AppFiles: this folder's own, never taken from a backup


class BackupError(ValueError):
    """Not a backup, a damaged one, or one that can't be restored there."""


def backup_name(now=None):
    """'ComboManager-backup-2026-10-06-1405.zip'"""
    return f"{PREFIX}-{(now or datetime.now()):%Y-%m-%d-%H%M}.zip"


def _left_out(rel):
    """The lock file, half-written temp files, hidden files and earlier backups saved in the folder."""
    name = rel.name
    return (name == LOCK_FILE or name.startswith(".") or name.endswith(".tmp")
            or (name.startswith(PREFIXES) and name.endswith(".zip")))


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
            if INFO not in names and not any(n.startswith((APP_DATA + "/", OLD_APP_DATA + "/")) for n in names):
                raise BackupError(f"{Path(path).name} isn't a Combo Manager backup.")
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

            def inside(name, key, old_name=None):
                """A value from a JSON file in the backup's AppFiles (or 'AppFiles', with the old name: older
                backups)."""
                for where in (f"{APP_DATA}/{name}", f"{OLD_APP_DATA}/{old_name or name}"):
                    if where in names:
                        try:
                            return json.loads(zf.read(where)).get(key)
                        except (ValueError, AttributeError):
                            return None
                return None
            past = sorted({PurePosixPath(n).parts[1] for n in names if n.startswith("Archive/")
                           and len(PurePosixPath(n).parts) > 2})
            return {**info, "files": len([n for n in names if n != INFO and not n.endswith("/")]),
                    "semester": inside(SETTINGS_FILE, "semester_name", "settings.json"),
                    "schedule": inside("schedule.json", "semester") or (
                        "(old format)" if "Schedule.xlsx" in names else None), "past": past}
    except (zipfile.BadZipFile, OSError) as e:
        raise BackupError(f"Can't read {Path(path).name} as a backup ({e}).")


def new_folder(parent, name):
    """parent/name, or 'name-2', 'name-3', ... when that's taken."""
    dest, n = Path(parent) / name, 2
    while dest.exists():
        dest, n = Path(parent) / f"{name}-{n}", n + 1
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
        app_data(work)                                # an older backup: its names as they are now
        exports(work)
        if dest.exists():
            dest.rmdir()
        os.replace(work, dest)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return dest


def restore_in_place(path, folder, keep_inputs=True):
    """Puts the backup's files into the data folder in use, replacing the scheduler's own (settings, combo edits, the
    schedule and its history and backups, Archive, the exports). First the folder as it is now is backed up into
    AppFiles/BeforeRestore (restoring that zip undoes this). Kept: the input spreadsheets (unless keep_inputs is False:
    an old copy would lose sign-ups the forms added since), the lock, the logs, and backup zips saved in the folder.
    The backup is unpacked beside it first, so a damaged zip changes nothing. -> the safety backup's path."""
    read_backup(path)
    folder = Path(folder)
    app = app_data(folder)
    stem, n = backup_name().replace(".zip", "-before-restoring"), 2
    safety = app / BEFORE_RESTORE / f"{stem}.zip"
    while safety.exists() or safety == Path(path):     # never over an earlier one (or the zip being restored)
        safety, n = app / BEFORE_RESTORE / f"{stem}-{n}.zip", n + 1
    create_backup(folder, safety)
    work = app / f".restoring.{os.getpid()}"
    shutil.rmtree(work, ignore_errors=True)

    def ours(p):
        """Stays as it is: hidden, a backup zip, the lock / logs / safety backups, the inputs (when kept)."""
        return (p.name.startswith(".") or (p.name.startswith(PREFIXES) and p.name.endswith(".zip"))
                or (p.parent == app and p.name in KEPT_HERE) or (keep_inputs and p.parent == folder
                                                                 and p.name in INPUTS))
    try:
        with zipfile.ZipFile(path) as zf:
            zf.extractall(work, [n for n in zf.namelist() if n != INFO])
        for p in list(folder.iterdir()) + list(app.iterdir()):
            if p == app or ours(p):
                continue
            shutil.rmtree(p) if p.is_dir() else p.unlink()
        new_app = work / APP_DATA
        for p in list(work.iterdir()) + (list(new_app.iterdir()) if new_app.is_dir() else []):
            if p == new_app:
                continue
            dest = (app if p.parent == new_app else folder) / p.name
            if ours(dest) and (dest.exists() or dest.name not in INPUTS):   # an input the folder lacks: taken
                continue
            shutil.move(str(p), str(dest))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return safety
