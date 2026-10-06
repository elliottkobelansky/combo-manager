"""The data folder: where the scheduler keeps everything that matters, chosen once per computer (app_config.py). Any
folder works the same: one on this computer, or one kept in sync by OneDrive, SharePoint, Dropbox or a network drive
so several computers can use it. The program itself can be thrown away and reinstalled; the data folder is what
counts (and backup.py zips it).

    Approvals.xlsx, Conflicts.xlsx          the inputs (Microsoft Forms / Power Automate fill them; the Run tab can
                                            pick other files, under any name, anywhere)
    Schedule.xlsx, Schedule.pdf             this semester's schedule (the PDF is rebuilt from the xlsx)
    Combos.pdf, Contact lists.xlsx          exported from the app (rebuilt any time)
    Archive/<semester>/                     past semesters' files
    App data/settings.json                  the settings (Settings tab), with settings.json.bak
    App data/scheduler_data.json            combo numbers, corrected names and emails, ... (store.py), with .bak
    App data/Schedule backups/              Schedule.xlsx as it was before each swap or withdrawal
    App data/In use.json                    which computer has the folder open (shared_folder.py)

Every path into the data folder is made here. Standard library only: the app uses this before checking that the
other packages are installed.
"""
import os
import shutil
from pathlib import Path

APPROVALS_FILE, CONFLICTS_FILE = "Approvals.xlsx", "Conflicts.xlsx"
OLD_APPROVALS_FILE = "Combo Approvals.xlsx"     # the usual name before 2026-10-06: still read when it's the only one
SCHEDULE_XLSX, SCHEDULE_PDF = "Schedule.xlsx", "Schedule.pdf"
COMBOS_PDF, CONTACTS_XLSX = "Combos.pdf", "Contact lists.xlsx"
ARCHIVE = "Archive"
# The program's own files live in a subfolder, so the top shows only what people open.
APP_DATA = "App data"
SETTINGS_FILE, STORE_FILE, LOCK_FILE = "settings.json", "scheduler_data.json", "In use.json"
SCHEDULE_BACKUPS = "Schedule backups"

TOP_FILES = [APPROVALS_FILE, OLD_APPROVALS_FILE, CONFLICTS_FILE, SCHEDULE_XLSX, SCHEDULE_PDF, COMBOS_PDF, CONTACTS_XLSX]
APP_DATA_FILES = [SETTINGS_FILE, STORE_FILE]
_MOVED_IN = (SETTINGS_FILE, SETTINGS_FILE + ".bak", STORE_FILE, STORE_FILE + ".bak", SCHEDULE_BACKUPS)


def app_data(folder):
    """folder/App data. In a data folder from before (those files at the top), they're moved in the first time.
    Writers create the folder."""
    folder = Path(folder)
    sub = folder / APP_DATA
    for name in _MOVED_IN:
        old, new = folder / name, sub / name
        if old.exists() and not new.exists():
            sub.mkdir(exist_ok=True)
            shutil.move(str(old), str(new))
    return sub


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
        return "the scheduler can't save files in it"
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
    return not names or bool(names & {APP_DATA, ARCHIVE, *TOP_FILES})
