"""The schedule: AppFiles/schedule.json in the data folder. Written only by the app and solve.py (a new schedule,
swaps, give-aways, text typed into a set, withdrawn combos); Schedule.xlsx and Schedule.pdf are exports made from it
and never read back, so editing them changes nothing.

    {"semester": "Fall 2026", "made": "2026-10-06T14:05:00", "supervision": true,
     "nights": [{"date": "2026-09-29", "venue": "Upstairs", "sets": 4, "first_set": "19:00", "set_length": 45,
                 "break": 15, "supervised": true}, ...],
     "sets":   {"2026-09-29": {"1": "Combo 28", "2": "Combo 30"}, ...},     combo names; a set not listed is open
     "typed":  {"2026-09-29": {"4": "Jam session"}},                        text in a set (it then counts as taken)
     "faculty": {"2026-09-29": {"title": "Prof.", "name": "Ana Ruiz", "email": "ana.ruiz@..."}},
                                                                            a feedback night's faculty member
     "report": [["warn", "..."], ...],                                      what the solver said when it was made
     "published": true,                                                     locked: Make schedule is off
     "history": [{"saved": "2026-10-20T15:02:11", "computer": "OFFICE-PC", "what": ["Trade with Combo 12: ..."],
                  "changes": [{"night": "2026-10-13", "set": 2, "before": "Combo 05", "after": "Combo 12"}]}, ...]}
                                                                            every change since it was made

Once a schedule exists it decides the nights (dates, venues, sets, times): changing the settings only affects the
next schedule made. "Supervised nights preferred here" still comes from the settings' show days.

Before 2026-10-06 the schedule lived in Schedule.xlsx (hand-editable). A data folder with only that is converted
the first time the schedule is loaded; the old file goes to AppFiles/ScheduleBackups.
"""
import json
import re
import shutil
import socket
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set

from core.model import Night
from data_folder import (ARCHIVE, EXPORT_FILES, SCHEDULE_BACKUPS, SCHEDULE_FILE, SCHEDULE_XLSX, app_data, exports,
                         schedule_backups, schedule_path)
from shared_folder import make_writable, remove, write_text

# A semester's files: moved together into Archive/<semester>/ when a new semester starts (archive_semester).
SEMESTER_FILES = EXPORT_FILES + [SCHEDULE_FILE, SCHEDULE_BACKUPS]


class ScheduleFileError(Exception):
    pass


class Faculty(NamedTuple):
    """A feedback night's faculty member. title: Prof., Dr., Mr., ... or ""."""
    title: str
    name: str
    email: str

    @property
    def full(self):
        """'Prof. Ana Ruiz'"""
        return f"{self.title} {self.name}".strip()


@dataclass
class Schedule:
    semester: str
    nights: List[Night]
    sets: Dict[date, Dict[int, Optional[str]]]   # every set of every night: combo id, or None (open or typed)
    typed: Dict[date, Dict[int, str]]
    supervised: Optional[Set[date]]               # None: this schedule doesn't track supervision
    problems: List[str] = field(default_factory=list)   # combos in it that aren't accepted any more, ...
    report: List[list] = field(default_factory=list)
    history: List[dict] = field(default_factory=list)   # every change since it was made, oldest first
    published: bool = False                       # locked: no new schedule (Schedule tab)
    made: str = ""                                # when it was made (ISO date and time)
    converted: bool = False                       # just made from an old Schedule.xlsx
    faculty: Dict[date, Faculty] = field(default_factory=dict)   # feedback night -> its faculty member


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
        raise ScheduleFileError(f"{schedule_path(folder)} is damaged. Restore it from AppFiles/ScheduleBackups "
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
    faculty = {date.fromisoformat(k): Faculty(v.get("title", ""), v.get("name", ""), v.get("email", ""))
               for k, v in data.get("faculty", {}).items() if k in by_date and (v.get("name") or v.get("email"))}
    return Schedule(data.get("semester", ""), nights, sets, typed, supervised, problems, report=data.get("report", []),
                    history=data.get("history", []), converted=converted, published=bool(data.get("published")),
                    made=data.get("made", ""), faculty=faculty)


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


def _entry(what, changes=()):
    """A history entry: when, on which computer, what was done (titles), and each set's before / after."""
    return {"saved": datetime.now().isoformat(timespec="seconds"), "computer": socket.gethostname(),
            "what": list(what), "changes": list(changes)}


def _shown(data, key, num):
    """What a set holds in the file, as words: a combo's name, the text in it (quoted), or 'open'."""
    name = data.get("sets", {}).get(key, {}).get(num)
    text = data.get("typed", {}).get(key, {}).get(num)
    return name or (f'"{text}"' if text else "open")


def _write(folder, data):
    write_text(schedule_path(folder), json.dumps(data, indent=2, ensure_ascii=False) + "\n", read_only=True)


def backup(folder):
    """Copies schedule.json into AppFiles/ScheduleBackups (timestamped). -> the copy, or None (nothing to copy)."""
    path = schedule_path(folder)
    if not path.exists():
        return None
    dest = schedule_backups(folder)
    dest.mkdir(parents=True, exist_ok=True)
    copy = dest / f"Schedule-{datetime.now():%Y-%m-%d-%H%M%S}.json"
    make_writable(copy)                               # (one made the same second: replaced)
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
        "typed": {}, "report": [list(r) for r in result.report], "history": [_entry(["Schedule made"])]})


def summary(folder):
    """What a new schedule would replace: {made, changes (saved changes since it was made), typed (sets with text),
    published}; {} when there's no schedule.json."""
    data = _read(folder)
    if data is None:
        return {}
    return dict(made=data.get("made", ""), published=bool(data.get("published")),
                changes=sum(1 for h in data.get("history", []) if h.get("changes")),
                typed=sum(len(r) for r in data.get("typed", {}).values()))


@dataclass
class Version:
    """An earlier version of the schedule: a copy in AppFiles/ScheduleBackups, made just before it was changed."""
    path: Path
    replaced: datetime                    # when it stopped being the schedule (the copy was made)
    same: bool                            # the same schedule as now (not one from before a Make a new schedule)
    made: str                             # when its schedule was made
    since: List[List[str]]                # same: what was done since, in order (each a history entry's titles)


def versions(folder):
    """The earlier versions of this semester's schedule, newest first (copies from another semester, or that can't
    be read, are left out)."""
    current = _read(folder) or {}
    history = current.get("history", [])
    found = []
    for p in schedule_backups(folder).glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or "sets" not in data or data.get("semester") != current.get("semester"):
            continue
        m = re.search(r"(\d{4})-(\d\d)-(\d\d)-(\d\d)(\d\d)(\d\d)", p.name)
        replaced = datetime(*map(int, m.groups())) if m else datetime.fromtimestamp(p.stat().st_mtime)
        own = data.get("history", [])
        same = data.get("made") == current.get("made") and history[:len(own)] == own
        found.append(Version(p, replaced, same, data.get("made", ""),
                             [h.get("what", []) for h in history[len(own):]] if same else []))
    return sorted(found, key=lambda v: v.replaced, reverse=True)


def restore_version(folder, version):
    """Puts an earlier version back as the schedule. The schedule as it is now is copied into ScheduleBackups first
    (so this can be undone the same way); the lock stays as it is now; the history keeps everything, plus this
    restore with each set it changed. -> the copy of the schedule as it was."""
    current = _read(folder)
    try:
        data = json.loads(Path(version.path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ScheduleFileError(f"{Path(version.path).name} can't be read ({e}). Nothing was changed.")
    if current is None or data.get("semester") != current.get("semester"):
        raise ScheduleFileError("That version is from another semester. Nothing was changed.")
    copy = backup(folder)
    keys = {(d, k) for src in (current, data) for part in ("sets", "typed") for d, row in src.get(part, {}).items()
            for k in row}
    changes = [{"night": d, "set": int(k), "before": _shown(current, d, k), "after": _shown(data, d, k)}
               for d, k in sorted(keys, key=lambda x: (x[0], int(x[1])))
               if _shown(current, d, k) != _shown(data, d, k)]
    data["published"] = bool(current.get("published"))
    data["history"] = current.get("history", []) + [
        _entry([f"Restored the version from {version.replaced:%a %b} {version.replaced.day}, "
                f"{version.replaced:%H:%M}"], changes)]
    _write(folder, data)
    return copy


def set_published(folder, on):
    """Locks the schedule (e.g. once it's final) or unlocks it. While it is, Make schedule is off. Kept in the history."""
    data = _read(folder)
    if data is None or bool(data.get("published")) == bool(on):
        return
    data["published"] = bool(on)
    data.setdefault("history", []).append(_entry(["Locked" if on else "Unlocked"]))
    _write(folder, data)


def save_changes(folder, combos, sets=None, typed=None, what=(), faculty=None):
    """Changes some sets: sets = {(date, set): combo id or None (open)}, typed = {(date, set): text or None (open)},
    and feedback nights' faculty members: faculty = {date: Faculty or None (cleared)};
    what: what was done, in words (e.g. the swaps' titles), for the history. Reads the file again first, so changes
    saved meanwhile elsewhere (other sets) are kept; a backup goes into AppFiles/ScheduleBackups first. -> the
    backup's path. Raises ScheduleFileError (nothing changed) for a set that isn't in the schedule."""
    data = _read(folder)
    if data is None:
        raise ScheduleFileError("No schedule yet: make it first (Run tab, step 2). Nothing was changed.")
    size = {n["date"]: int(n.get("sets", 0)) for n in data.get("nights", [])}
    todo = list((sets or {}).items()) + [((d, k), ("text", t)) for (d, k), t in (typed or {}).items()]
    missing = [f"{d} set {k}" for (d, k), _ in todo if not 1 <= k <= size.get(d.isoformat(), 0)] + [
        f"{d}" for d in (faculty or {}) if d.isoformat() not in size]
    if missing:
        raise ScheduleFileError("These sets aren't in the schedule: " + ", ".join(missing) + ". Nothing was changed.")
    copy = backup(folder)
    before = {(d, k): _shown(data, d.isoformat(), str(k)) for (d, k), _ in todo}
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
    data["sets"] = {d: r for d, r in data.get("sets", {}).items() if r}
    data["typed"] = {d: r for d, r in data.get("typed", {}).items() if r}
    people, faculty_changed = data.setdefault("faculty", {}), False
    for d, who in (faculty or {}).items():
        new = ({**({"title": who.title.strip()} if who.title.strip() else {}), "name": who.name.strip(),
                "email": who.email.strip()} if who else None)
        if people.get(d.isoformat()) != new:
            faculty_changed = True
            if new:
                people[d.isoformat()] = new
            else:
                people.pop(d.isoformat(), None)
    if not people:
        data.pop("faculty")
    changes = [{"night": d.isoformat(), "set": k, "before": before[(d, k)], "after": _shown(data, d.isoformat(), str(k))}
               for d, k in sorted(before) if before[(d, k)] != _shown(data, d.isoformat(), str(k))]
    if changes or faculty_changed:
        data.setdefault("history", []).append(_entry(what, changes))
    _write(folder, data)
    return copy


def sync_faculty(folder, emails=None, names=None, titles=None):
    """A person changed on the Combos tab: the feedback nights they're the faculty member of follow. emails = {old:
    new}, names = {email: name}, titles = {email: title ("" = none)}; matched by email. A backup first, kept in the
    history. -> True when something changed."""
    data = _read(folder)
    emails = {o.lower(): n.lower() for o, n in (emails or {}).items()}
    names = {e.lower(): n.strip() for e, n in (names or {}).items() if n and n.strip()}
    titles = {e.lower(): t.strip() for e, t in (titles or {}).items()}
    people = (data or {}).get("faculty", {})
    new = {}
    for d, who in people.items():
        now = dict(who)
        e = emails.get(now.get("email", "").lower(), now.get("email", "").lower())
        if e != now.get("email", "").lower():
            now["email"] = e
        if e in names:
            now["name"] = names[e]
        if e in titles:
            if titles[e]:
                now["title"] = titles[e]
            else:
                now.pop("title", None)
        if now != who:
            new[d] = now
    if not new:
        return False
    backup(folder)
    people.update(new)
    data.setdefault("history", []).append(_entry([f"Faculty member on {d}: {(w.get('title', '') + ' ' + w['name']).strip()} "
                                                  f"({w['email']})" for d, w in sorted(new.items())]))
    _write(folder, data)
    return True


def open_sets_of(folder, name, what=()):
    """Every set combo `name` plays becomes open (it was withdrawn), going by the schedule as saved now. A backup first.
    -> (the sets [(date, set)], the backup), or ([], None) when it plays none."""
    data = _read(folder)
    cells = sorted((date.fromisoformat(d), int(k)) for d, row in (data or {}).get("sets", {}).items()
                   for k, n in row.items() if n == name)
    if not cells:
        return [], None
    copy = backup(folder)
    data["sets"] = {d: kept for d, row in data["sets"].items() if (kept := {k: n for k, n in row.items() if n != name})}
    data.setdefault("history", []).append(_entry(what or [f"{name} withdrawn"], [
        {"night": d.isoformat(), "set": k, "before": name, "after": "open"} for d, k in cells]))
    _write(folder, data)
    return cells, copy


# ---------------------------------------------------------------- archive, and the old Schedule.xlsx

def semester_paths(folder):
    """The SEMESTER_FILES that are there."""
    folder = Path(folder)
    paths = [app_data(folder) / n if n in (SCHEDULE_FILE, SCHEDULE_BACKUPS) else exports(folder) / n
             for n in SEMESTER_FILES]
    return [p for p in paths if p.exists()]


def archive_semester(folder, semester):
    """Moves a semester's files (SEMESTER_FILES) into folder/Archive/<semester>/ (or '<semester>-2', ... if that
    exists): its final schedule (with the full change history) and its exports. Its per-change copies
    (ScheduleBackups) are deleted, so the archive stays small. Returns the new folder, or None when there was nothing
    to move."""
    folder = Path(folder)
    present = semester_paths(folder)
    if not present:
        return None
    name = re.sub(r'[\\/:*?"<>|\s]+', "-", str(semester or "").strip()).strip("-") or "OldSchedule"
    dest, n = folder / ARCHIVE / name, 2
    while dest.exists():
        dest, n = folder / ARCHIVE / f"{name}-{n}", n + 1
    dest.mkdir(parents=True)
    for p in present:
        if p.name == SCHEDULE_BACKUPS:                # the per-change copies: the schedule keeps the full history
            remove(p)
        else:
            shutil.move(str(p), str(dest / p.name))
    return dest


def archived(folder, semester):
    """The Archive folder with semester's schedule (the newest, if it was archived more than once), or None."""
    found = []
    base = Path(folder) / ARCHIVE
    for d in (base.iterdir() if base.is_dir() else []):
        p = d / SCHEDULE_FILE
        try:
            if p.is_file() and json.loads(p.read_text(encoding="utf-8")).get("semester") == semester:
                found.append((p.stat().st_mtime, d))
        except (OSError, ValueError):
            continue
    return max(found)[1] if found else None


def unarchive_semester(folder, src):
    """Puts an archived semester's files (from archived()) back in place: its schedule and exports. The folder's
    current semester files must be gone (archive_semester) first. The emptied Archive folder is removed."""
    folder, src = Path(folder), Path(src)
    if semester_paths(folder):
        raise ScheduleFileError("The current semester's files are still there: archive them first.")
    for name in SEMESTER_FILES:
        p = src / name
        if p.exists():
            dest = app_data(folder) / name if name in (SCHEDULE_FILE, SCHEDULE_BACKUPS) else exports(folder) / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(dest))
    if not any(src.iterdir()):
        src.rmdir()


def _old_xlsx(folder):
    """Schedule.xlsx when it's the old, hand-editable kind (a 'Schedule' sheet) and there's no schedule.json."""
    path = Path(folder) / SCHEDULE_XLSX
    if schedule_path(folder).exists() or not path.exists():
        return None
    from outputs.excel_schedule import is_old_schedule
    return path if is_old_schedule(path) else None


def convert_old(folder, combos, settings):
    """Turns an old Schedule.xlsx into schedule.json (its sets, typed text, supervised nights and nights), then moves
    the old file into AppFiles/ScheduleBackups. What couldn't be read goes into the report."""
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
        "report": [["warn", f"From the old Schedule.xlsx: {p}"] for p in problems],
        "history": [_entry(["Converted from the old, hand-editable Schedule.xlsx"])]})
    dest = schedule_backups(folder)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.move(str(old), str(dest / f"Schedule-old-hand-editable-{datetime.now():%Y-%m-%d}.xlsx"))
