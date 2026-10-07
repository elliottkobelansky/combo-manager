"""The data folder: where the scheduler keeps everything that matters, chosen once per computer (app_config.py). Any
folder works the same: one on this computer, or one kept in sync by OneDrive, SharePoint, Dropbox or a network drive
so several computers can use it. The program itself can be thrown away and reinstalled; the data folder is what
counts (and backup.py zips it).

    Approvals.xlsx, Conflicts.xlsx          the inputs (Microsoft Forms / Power Automate fill them; the Run tab can
                                            pick other files, under any name, anywhere)
    Exports/                                what the app makes for people to read (share this folder alone):
      Schedule.xlsx, Schedule.pdf             this semester's schedule: exports of AppFiles/schedule.json, rebuilt
                                              after every change, never read back
      Combos.pdf, Combos.xlsx                 the combo list (Combos tab; rebuilt any time)
    Archive/<semester>/                     past semesters' files
    AppFiles/semester.json                  the settings (Semester tab), with semester.json.bak
    AppFiles/scheduler_data.json            combo numbers, corrected names and emails, ... (store.py), with .bak
    AppFiles/schedule.json                  the schedule itself: who plays which set (schedule_file.py)
    AppFiles/ScheduleBackups/               schedule.json as it was before each change
    AppFiles/in_use.json                    which computer has the folder open (shared_folder.py)

Every path into the data folder is made here. Standard library only: the app uses this before checking that the
other packages are installed.
"""
import os
import shutil
from pathlib import Path

APPROVALS_FILE, CONFLICTS_FILE = "Approvals.xlsx", "Conflicts.xlsx"
OLD_APPROVALS_FILE = "Combo Approvals.xlsx"     # the usual name before 2026-10-06: still read when it's the only one
SCHEDULE_XLSX, SCHEDULE_PDF = "Schedule.xlsx", "Schedule.pdf"
COMBOS_PDF, COMBOS_XLSX = "Combos.pdf", "Combos.xlsx"
ARCHIVE = "Archive"
EXPORTS = "Exports"
EXPORT_FILES = [SCHEDULE_XLSX, SCHEDULE_PDF, COMBOS_PDF, COMBOS_XLSX]
# The program's own files live in a subfolder, so the top shows only what people open.
APP_DATA = "AppFiles"
SETTINGS_FILE, STORE_FILE, LOCK_FILE = "semester.json", "scheduler_data.json", "in_use.json"
SCHEDULE_FILE = "schedule.json"
SCHEDULE_BACKUPS = "ScheduleBackups"
BEFORE_RESTORE, LOGS = "BeforeRestore", "Logs"
DEFAULT_NAME = "ComboManagerData"                 # a new data folder's suggested name
# Names before 2026-10-07 (with spaces): a folder that has them is renamed the first time it's opened
OLD_APP_DATA = "App data"
RENAMED = {"settings.json": SETTINGS_FILE, "settings.json.bak": SETTINGS_FILE + ".bak",
           "Schedule backups": SCHEDULE_BACKUPS, "Before restore": BEFORE_RESTORE, "In use.json": LOCK_FILE}

TOP_FILES = [APPROVALS_FILE, OLD_APPROVALS_FILE, CONFLICTS_FILE]
APP_DATA_FILES = [SETTINGS_FILE, STORE_FILE, SCHEDULE_FILE]
_MOVED_IN = ("settings.json", "settings.json.bak", STORE_FILE, STORE_FILE + ".bak", "Schedule backups")


def _move(old, new):
    """old -> new when new isn't there yet; a folder into one that is: what's in it, one by one."""
    if not old.exists():
        return
    if not new.exists():
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old), str(new))
    elif old.is_dir() and new.is_dir():
        for p in list(old.iterdir()):
            _move(p, new / p.name)
        try:
            old.rmdir()                                   # (left when something in it couldn't move)
        except OSError:
            pass


def app_data(folder):
    """folder/AppFiles, the program's own files. A data folder from before is tidied the first time: files at the
    top moved in (the oldest layout), 'AppFiles' renamed, and the names with spaces renamed (RENAMED). Writers create
    the folder."""
    folder = Path(folder)
    sub = folder / APP_DATA
    try:
        for name in _MOVED_IN:
            _move(folder / name, sub / RENAMED.get(name, name))
        _move(folder / OLD_APP_DATA, sub)
        for old, new in RENAMED.items():
            _move(sub / old, sub / new)
    except OSError:
        pass                                              # (a file in use: tried again next time)
    return sub


def exports(folder):
    """folder/Exports (made if needed). In a data folder from before (the exports at the top), they're moved in the
    first time; one open in Excel is left where it is, and made again in Exports. An old hand-editable
    Schedule.xlsx (no schedule.json yet) stays at the top until it's converted."""
    folder = Path(folder)
    sub = folder / EXPORTS
    sub.mkdir(exist_ok=True)
    for name in EXPORT_FILES:
        old, new = folder / name, sub / name
        if old.exists() and not new.exists() and (name != SCHEDULE_XLSX or schedule_path(folder).exists()):
            try:
                shutil.move(str(old), str(new))
            except OSError:
                pass
    return sub


def export_path(folder, name):
    """Where an export (EXPORT_FILES) goes: folder/Exports/name."""
    return exports(folder) / name


def usual_inputs(folder):
    """{"approvals": path, "conflicts": path}: the input files read when none are picked. A folder that only has the
    old Combo Approvals.xlsx keeps working (the flow that writes it may know it by that name)."""
    folder = Path(folder)
    approvals = folder / APPROVALS_FILE
    if not approvals.exists() and (folder / OLD_APPROVALS_FILE).exists():
        approvals = folder / OLD_APPROVALS_FILE
    return {"approvals": approvals, "conflicts": folder / CONFLICTS_FILE}


def settings_path(folder):
    return app_data(folder) / SETTINGS_FILE


def store_path(folder):
    return app_data(folder) / STORE_FILE


def schedule_path(folder):
    return app_data(folder) / SCHEDULE_FILE


def lock_path(folder):
    return app_data(folder) / LOCK_FILE


def schedule_backups(folder):
    return app_data(folder) / SCHEDULE_BACKUPS


def archive(folder):
    return Path(folder) / ARCHIVE


def problem(folder):
    """None when folder can be used as the data folder; else why not, in a few words."""
    if not folder:
        return "no folder chosen"
    folder = Path(folder)
    if not folder.exists():
        return "it can't be found"
    if not folder.is_dir():
        return "it isn't a folder"
    probe = folder / f".combo-scheduler-check.{os.getpid()}.tmp"
    try:
        probe.write_text("x")
    except OSError:
        return "the app can't save files in it"
    finally:
        try:
            probe.unlink()
        except OSError:
            pass
    return None


def looks_like_data_folder(folder):
    """True when folder holds scheduler files (or nothing at all, a new one); False for any other folder with things in
    it (Documents, say), where the scheduler's files would end up mixed with others."""
    folder = Path(folder)
    try:
        names = {p.name for p in folder.iterdir() if not p.name.startswith(".")}
    except OSError:
        return False
    return not names or bool(names & {APP_DATA, OLD_APP_DATA, ARCHIVE, EXPORTS, *TOP_FILES, *EXPORT_FILES})
