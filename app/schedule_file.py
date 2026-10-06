"""The schedule: App data/schedule.json in the data folder. Written only by the app and solve.py (a new schedule,
swaps, give-aways, text typed into a set, withdrawn combos); Schedule.xlsx and Schedule.pdf are exports made from it
and never read back, so editing them changes nothing.

    {"semester": "Fall 2026", "made": "2026-10-06T14:05:00", "supervision": true,
     "nights": [{"date": "2026-09-29", "venue": "Upstairs", "sets": 4, "first_set": "19:00", "set_length": 45,
                 "break": 15, "supervised": true}, ...],
     "sets":   {"2026-09-29": {"1": "Combo 28", "2": "Combo 30"}, ...},     combo names; a set not listed is open
     "typed":  {"2026-09-29": {"4": "Jam session"}},                        text in a set (it then counts as taken)
     "report": [["warn", "..."], ...]}                                      what the solver said when it was made

Once a schedule exists it decides the nights (dates, venues, sets, times): changing the settings only affects the
next schedule made. "Supervised nights preferred here" still comes from the settings' show days.

Before 2026-10-06 the schedule lived in Schedule.xlsx (hand-editable). A data folder with only that is converted
the first time the schedule is loaded; the old file goes to App data/Schedule backups.
"""
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, List, Optional, Set

from core.model import Night
from data_folder import (ARCHIVE, COMBOS_PDF, COMBOS_XLSX, CONTACTS_XLSX, SCHEDULE_BACKUPS, SCHEDULE_FILE, SCHEDULE_PDF,
                         SCHEDULE_XLSX, app_data, schedule_backups, schedule_path)
from shared_folder import write_text

# A semester's files: moved together into Archive/<semester>/ when a new semester starts (archive_semester).
SEMESTER_FILES = [SCHEDULE_XLSX, SCHEDULE_PDF, COMBOS_PDF, COMBOS_XLSX, CONTACTS_XLSX, SCHEDULE_FILE, SCHEDULE_BACKUPS]


class ScheduleFileError(Exception):
    pass


@dataclass
class Schedule:
    semester: str
    nights: List[Night]
    sets: Dict[date, Dict[int, Optional[str]]]   # every set of every night: combo id, or None (open or typed)
    typed: Dict[date, Dict[int, str]]
    supervised: Optional[Set[date]]               # None: this schedule doesn't track supervision
    problems: List[str] = field(default_factory=list)   # combos in it that aren't accepted any more, ...
    report: List[list] = field(default_factory=list)
    converted: bool = False                       # just made from an old Schedule.xlsx


# ---------------------------------------------------------------- reading

def has_schedule(folder):
    """True when the data folder has a schedule (or an old Schedule.xlsx that will become one)."""
    return schedule_path(folder).exists() or _old_xlsx(folder) is not None


def _read(folder):
    try:
        data = json.loads(schedule_path(folder).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except ValueError:
        raise ScheduleFileError(f"{schedule_path(folder)} is damaged. Restore it from App data/Schedule backups "
                                "(the newest copy), or from a backup.")
    return data if isinstance(data, dict) else {}


def semester_of(folder, settings=None):
    """The semester the folder's schedule is for; None when there's none (or, for an old Schedule.xlsx, unknown)."""
    data = _read(folder)
    if data is not None:
        return data.get("semester") or None
    old = _old_xlsx(folder)
    if old is None:
        return None
    from outputs.excel_schedule import old_schedule_semester
    return old_schedule_semester(old, settings)


def check_semester(folder, settings):
    """Raises ScheduleFileError when the schedule belongs to another semester than the settings'."""
    sem = semester_of(folder, settings)
    if has_schedule(folder) and sem != settings.semester_name:
        raise ScheduleFileError(f"The schedule is for {sem or 'another semester'}, not {settings.semester_name}. "
                                f"Make the {settings.semester_name} schedule (Run tab, step 2); the old files are "
                                "moved into the data folder's Archive first.")


def load(folder, combos, settings):
    """The folder's schedule, checked against the settings' semester. combos: {id: Combo}, the accepted combos; a
    set naming any other combo (withdrawn in the approvals since, say) counts as open and is listed in problems.
    Raises ScheduleFileError when there's none, or it's another semester's."""
    if not has_schedule(folder):
        raise ScheduleFileError("No schedule yet: make it first (Run tab, step 2).")
    check_semester(folder, settings)
    converted = False
    if not schedule_path(folder).exists():
        convert_old(folder, combos, settings)
        converted = True
    data = _read(folder)
    by_date = {d["date"]: d for d in data.get("nights", [])}
    by_name = {c.name.strip().casefold(): c.id for c in combos.values()}
    nights, sets, typed, problems = [], {}, {}, []
    by_day = {(sd.weekday, sd.venue.casefold()): sd.supervision_preferred for sd in settings.show_days}
    preferred_venues = {sd.venue.casefold() for sd in settings.show_days if sd.supervision_preferred}
    for key in sorted(by_date):
        n = by_date[key]
        d, venue = date.fromisoformat(key), n.get("venue", "")
        first = time.fromisoformat(n["first_set"]) if n.get("first_set") else None
        nights.append(Night(d, venue, int(n.get("sets", 0)), first, int(n.get("set_length", 0)), int(n.get("break", 0)),
                            by_day.get((d.weekday(), venue.casefold()), venue.casefold() in preferred_venues)))
        row = data.get("sets", {}).get(key, {})
        sets[d] = {}
        for k in range(1, int(n.get("sets", 0)) + 1):
            name = row.get(str(k))
            if name and name.strip().casefold() in by_name:
                sets[d][k] = by_name[name.strip().casefold()]
            else:
                sets[d][k] = None
                if name:
                    problems.append(f"{d:%a %b} {d.day} set {k}: {name} isn't an accepted combo any more (withdrawn?). "
                                    "Treated as open: give the set away or leave it open (Schedule or Swaps tab).")
        texts = {int(k): t for k, t in data.get("typed", {}).get(key, {}).items() if t}
        if texts:
            typed[d] = texts
    supervised = ({date.fromisoformat(n["date"]) for n in data.get("nights", []) if n.get("supervised")}
                  if data.get("supervision", True) else None)
    return Schedule(data.get("semester", ""), nights, sets, typed, supervised, problems, data.get("report", []),
                    converted)


def entries(schedule):
    """{date: {set: ("combo", id) or ("text", text)}}: what the PDF draws."""
    out = {d: {k: ("combo", c) for k, c in row.items() if c} for d, row in schedule.sets.items()}
    for d, row in schedule.typed.items():
        for k, t in row.items():
            out.setdefault(d, {})[k] = ("text", t)
    return out


# ---------------------------------------------------------------- writing

def _night_json(n, supervised):
    return {"date": n.date.isoformat(), "venue": n.venue, "sets": n.n_slots,
            "first_set": n.first_set.strftime("%H:%M") if n.first_set else None, "set_length": n.set_length,
            "break": n.break_minutes, "supervised": n.date in supervised}


def _write(folder, data):
    write_text(schedule_path(folder), json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def backup(folder):
    """Copies schedule.json into App data/Schedule backups (timestamped). -> the copy, or None (nothing to copy)."""
    path = schedule_path(folder)
    if not path.exists():
        return None
    dest = schedule_backups(folder)
    dest.mkdir(parents=True, exist_ok=True)
    copy = dest / f"Schedule {datetime.now():%Y-%m-%d %H%M%S}.json"
    shutil.copy2(path, copy)
    return copy


def save_new(folder, result, settings):
    """A brand-new schedule (core.Result) for the settings' semester; the one before (if any) is backed up first."""
    backup(folder)
    supervised = set(result.supervised or ())
    _write(folder, {
        "semester": settings.semester_name, "made": datetime.now().isoformat(timespec="seconds"),
        "supervision": bool(settings.every_combo_supervised),
        "nights": [_night_json(n, supervised) for n in result.nights],
        "sets": {d.isoformat(): {str(k): result.combos[c].name for k, c in enumerate(cs, start=1)}
                 for d, cs in sorted(result.lineup.items()) if cs},
        "typed": {}, "report": [list(r) for r in result.report]})


def save_changes(folder, combos, sets=None, typed=None):
    """Changes some sets: sets = {(date, set): combo id or None (open)}, typed = {(date, set): text or None (open)}.
    Reads the file again first, so changes saved meanwhile elsewhere (other sets) are kept; a backup goes into App
    data/Schedule backups first. -> the backup's path. Raises ScheduleFileError (nothing changed) for a set that
    isn't in the schedule."""
    data = _read(folder)
    if data is None:
        raise ScheduleFileError("No schedule yet: make it first (Run tab, step 2). Nothing was changed.")
    size = {n["date"]: int(n.get("sets", 0)) for n in data.get("nights", [])}
    todo = list((sets or {}).items()) + [((d, k), ("text", t)) for (d, k), t in (typed or {}).items()]
    missing = [f"{d} set {k}" for (d, k), _ in todo if not 1 <= k <= size.get(d.isoformat(), 0)]
    if missing:
        raise ScheduleFileError("These sets aren't in the schedule: " + ", ".join(missing) + ". Nothing was changed.")
    copy = backup(folder)
    for (d, k), value in todo:
        key, num = d.isoformat(), str(k)
        row, texts = data.setdefault("sets", {}).setdefault(key, {}), data.setdefault("typed", {}).setdefault(key, {})
        if isinstance(value, tuple):                  # text typed in (or cleared): the set has no combo
            row.pop(num, None)
            if value[1] and value[1].strip():
                texts[num] = value[1].strip()
            else:
                texts.pop(num, None)
        elif value:                                   # a combo takes the set (any text in it goes)
            row[num] = combos[value].name
            texts.pop(num, None)
        else:
            row.pop(num, None)
    data["sets"] = {d: r for d, r in data["sets"].items() if r}
    data["typed"] = {d: r for d, r in data["typed"].items() if r}
    _write(folder, data)
    return copy


# ---------------------------------------------------------------- archive, and the old Schedule.xlsx

def semester_paths(folder):
    """The SEMESTER_FILES that are there."""
    folder = Path(folder)
    paths = [app_data(folder) / n if n in (SCHEDULE_FILE, SCHEDULE_BACKUPS) else folder / n for n in SEMESTER_FILES]
    return [p for p in paths if p.exists()]


def archive_semester(folder, semester):
    """Moves a semester's files (SEMESTER_FILES) into folder/Archive/<semester>/ (or '<semester> (2)', ... if that
    exists). Returns the new folder, or None when there was nothing to move."""
    folder = Path(folder)
    present = semester_paths(folder)
    if not present:
        return None
    name = re.sub(r'[\\/:*?"<>|]+', "-", str(semester or "Old schedule")).strip() or "Old schedule"
    dest, n = folder / ARCHIVE / name, 2
    while dest.exists():
        dest, n = folder / ARCHIVE / f"{name} ({n})", n + 1
    dest.mkdir(parents=True)
    for p in present:
        shutil.move(str(p), str(dest / p.name))
    return dest


def _old_xlsx(folder):
    """Schedule.xlsx when it's the old, hand-editable kind (a 'Schedule' sheet) and there's no schedule.json."""
    path = Path(folder) / SCHEDULE_XLSX
    if schedule_path(folder).exists() or not path.exists():
        return None
    from outputs.excel_schedule import is_old_schedule
    return path if is_old_schedule(path) else None


def convert_old(folder, combos, settings):
    """Turns an old Schedule.xlsx into schedule.json (its sets, typed text, supervised nights and nights), then moves
    the old file into App data/Schedule backups. What couldn't be read goes into the report."""
    from outputs.excel_schedule import old_schedule_nights, read_old_schedule
    old = _old_xlsx(folder)
    sets, problems, supervised, typed = read_old_schedule(old, combos)
    nights = old_schedule_nights(old, settings)
    _write(folder, {
        "semester": settings.semester_name, "made": datetime.fromtimestamp(old.stat().st_mtime).isoformat(
            timespec="seconds"), "supervision": supervised is not None,
        "nights": [_night_json(n, supervised or set()) for n in nights],
        "sets": {d.isoformat(): {str(k): combos[c].name for k, c in row.items() if c} for d, row in sorted(sets.items())
                 if any(row.values())},
        "typed": {d.isoformat(): {str(k): t for k, t in row.items()} for d, row in sorted(typed.items())},
        "report": [["warn", f"From the old Schedule.xlsx: {p}"] for p in problems]})
    dest = schedule_backups(folder)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.move(str(old), str(dest / f"Schedule (old hand-editable file, {datetime.now():%Y-%m-%d}).xlsx"))
