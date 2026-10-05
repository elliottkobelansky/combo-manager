"""Output writer: core.Result -> Schedule.xlsx, and reading it back after hand edits."""
import re
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill



# A semester's files in the data folder: moved together into Archive/<semester>/ when a new semester starts
# (archive_semester).
ARCHIVE = "Archive"
SEMESTER_FILES = ["Schedule.xlsx", "Schedule.pdf", "Combos.pdf", "Contact lists.xlsx", "Schedule backups"]


def schedule_semester(path, settings=None):
    """The semester Schedule.xlsx was made for (kept in the file's properties). For a file made before that was
    recorded: settings.semester_name if all its nights fall within the settings' dates, else None (unknown)."""
    from openpyxl import load_workbook
    from util import to_date
    try:
        wb = load_workbook(path, read_only=True)
    except FileNotFoundError:
        return None
    try:
        if wb.properties.subject:
            return wb.properties.subject
        if settings is None or "Schedule" not in wb.sheetnames:
            return None
        dates = []
        for r in wb["Schedule"].iter_rows(min_row=2, max_col=1, values_only=True):
            try:
                if r[0] is not None:
                    dates.append(to_date(r[0]))
            except ValueError:
                pass
        inside = dates and all(settings.start_date <= d <= settings.end_date for d in dates if d)
        return settings.semester_name if inside else None
    finally:
        wb.close()


def record_semester(path, semester):
    """Writes the semester into an older Schedule.xlsx that doesn't say yet (best effort: skipped if it's open)."""
    from openpyxl import load_workbook
    try:
        wb = load_workbook(path)
        if not wb.properties.subject:
            wb.properties.subject = semester
            wb.save(path)
    except (OSError, KeyError):
        pass


def check_semester(path, settings):
    """Raises ScheduleFileError when Schedule.xlsx (if there is one) belongs to another semester than the
    settings'."""
    if not Path(path).exists():
        return
    sem = schedule_semester(path, settings)
    if sem != settings.semester_name:
        raise ScheduleFileError(f"{Path(path).name} is for {sem or 'another semester'}, not {settings.semester_name}. "
                                f"Make the {settings.semester_name} schedule (Run tab, step 2); the old files are moved "
                                "into the data folder's Archive first.")


def semester_paths(folder):
    """The SEMESTER_FILES that are there (Schedule backups is in App data)."""
    from util import app_data
    folder = Path(folder)
    paths = [app_data(folder) / n if n == "Schedule backups" else folder / n for n in SEMESTER_FILES]
    return [p for p in paths if p.exists()]


def archive_semester(folder, semester):
    """Moves a semester's files (SEMESTER_FILES) into folder/Archive/<semester>/ (or '<semester> (2)', ... if that
    exists). Returns the new folder, or None when there was nothing to move."""
    import shutil
    folder = Path(folder)
    present = semester_paths(folder)
    if not present:
        return None
    name = re.sub(r'[\\/:*?"<>|]+', "-", str(semester or "Old schedule")).strip() or "Old schedule"
    archive = folder / ARCHIVE
    dest, n = archive / name, 2
    while dest.exists():
        dest, n = archive / f"{name} ({n})", n + 1
    dest.mkdir(parents=True)
    for p in present:
        shutil.move(str(p), str(dest / p.name))
    return dest


def write_schedule(path, result, settings):
    wb = Workbook()
    wb.properties.subject = settings.semester_name     # which semester this schedule is for (schedule_semester)
    hfont, hfill, base = Font(name="Arial", bold=True), PatternFill("solid", fgColor="DDEBF7"), Font(name="Arial")
    first = [True]

    def sheet(title, header, rows, widths):
        ws = wb.active if first[0] else wb.create_sheet()
        first[0] = False
        ws.title = title
        ws.append(header)
        for c in ws[1]:
            c.font, c.fill = hfont, hfill
        for r in rows:
            ws.append(r)
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.font = base
        for letter, w in zip("ABCDEFGHIJ", widths):
            ws.column_dimensions[letter].width = w
        ws.freeze_panes = "A2"
        return ws

    policy, combos = settings.extra_slot_policy, result.combos

    timed = any(n.first_set is not None for n in result.nights)   # Start/End columns only when set times are set up
    rows = []
    for n in result.nights:
        order = result.lineup.get(n.date, [])
        for k in range(1, n.n_slots + 1):
            c = order[k - 1] if k <= len(order) else None
            rows.append([n.date, n.weekday, n.venue, k] + ([n.set_time(k), n.set_end(k)] if timed else [])
                        + [combos[c].name if c else ("OPEN - volunteer" if policy == "open" else "(empty)")]
                        + (["Yes" if n.date in result.supervised else ""] if settings.every_combo_supervised else []))
    header = (["Date", "Day", "Venue", "Set"] + (["Start", "End"] if timed else []) + ["Combo"]
              + (["Supervised"] if settings.every_combo_supervised else []))
    ws = sheet("Schedule", header, rows, (14, 12, 14, 6) + ((10, 10) if timed else ()) + (36, 12))
    for r in range(2, ws.max_row + 1):
        ws.cell(row=r, column=1).number_format = "yyyy-mm-dd"
        if timed:
            ws.cell(row=r, column=5).number_format = ws.cell(row=r, column=6).number_format = "h:mm AM/PM"

    if settings.every_combo_supervised:
        sheet("Supervision", ["Date", "Day", "Venue", "Professor (fill in)"],
              [[n.date, n.weekday, n.venue, ""] for n in result.nights if n.date in result.supervised],
              (14, 12, 14, 30))
        for r in range(2, wb["Supervision"].max_row + 1):
            wb["Supervision"].cell(row=r, column=1).number_format = "yyyy-mm-dd"

    sheet("Report", ["Level", "Message"], [[l.upper(), t] for l, t in result.report], (10, 120))
    wb.save(path)


def read_schedule(path, combos):
    """Schedule.xlsx (possibly edited by hand) -> (sets, problems, supervised, typed).
    sets = {date: {set number: combo id or None}}. A Combo cell that is blank, 'OPEN...' or '(empty)' is open (None).
    Anything else that isn't a combo name (e.g. 'Jam session') goes in typed = {date: {set number: text}}: shown on
    the PDF as written, and the set counts as taken (None in sets). Text that looks like a mistyped combo name
    ('Combo 5') is reported instead. supervised = the dates with Yes in the Supervised column, or None if the file
    has no such column."""
    from openpyxl import load_workbook
    from util import blank, to_date
    try:
        wb = load_workbook(path, data_only=True)
    except FileNotFoundError:
        raise ScheduleFileError(f"No {Path(path).name} yet: make the schedule first (Run tab, step 2).")
    if "Schedule" not in wb.sheetnames:
        raise ScheduleFileError(f"{path} has no 'Schedule' sheet.")
    ws = wb["Schedule"]
    by_name = {c.name.strip().casefold(): c.id for c in combos.values()}
    head = [str(v or "").strip().lower() for v in next(ws.iter_rows(max_row=1, values_only=True), ())]
    di, si, ci = (head.index(h) if h in head else j for h, j in (("date", 0), ("set", 3), ("combo", 4)))
    vi = head.index("supervised") if "supervised" in head else None
    sets, problems, supervised, typed = defaultdict(dict), [], set(), defaultdict(dict)
    for i, r in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        r = tuple(r) + (None,) * (max(di, si, ci, vi or 0) + 1 - len(r))
        if all(blank(v) for v in (r[di], r[si], r[ci])):
            continue
        try:
            d, k = to_date(r[di]), int(r[si])
        except (ValueError, TypeError):
            problems.append(f"Schedule row {i}: can't read the date or set number; row ignored.")
            continue
        if vi is not None and str(r[vi] or "").strip().lower() in ("yes", "y", "x", "true"):
            supervised.add(d)
        name = "" if r[ci] is None else str(r[ci]).strip()
        if not name or name.upper().startswith("OPEN") or name == "(empty)":
            cid = None
        elif name.casefold() in by_name:
            cid = by_name[name.casefold()]
        elif re.match(r"(?i)combo\s*\d", name):
            problems.append(f"Schedule row {i}: '{name}' isn't an accepted combo (withdrawn, or a typo?). Treated "
                            "as open: give the set away or leave it open (Schedule or Swaps tab).")
            cid = None
        else:
            typed[d][k] = name
            cid = None
        if k in sets[d]:
            problems.append(f"Schedule row {i}: {d} set {k} appears twice; using the later row.")
        sets[d][k] = cid
    return dict(sets), problems, (supervised if vi is not None else None), dict(typed)


class ScheduleFileError(Exception):
    pass


def schedule_nights(path, settings):
    """The show nights as Schedule.xlsx has them (date, venue, number of sets, set times), sorted. Once a schedule
    exists it decides which nights there are: changing dates or show days in the settings only affects the next
    schedule made. ("Supervised nights preferred here" still comes from the settings' show days.)"""
    from datetime import datetime as dt
    from openpyxl import load_workbook
    from core.model import Night
    from util import to_date, to_time
    try:
        ws = load_workbook(path, data_only=True)["Schedule"]
    except (FileNotFoundError, KeyError):
        raise ScheduleFileError(f"Can't read the nights from {path}.")
    head = [str(v or "").strip().lower() for v in next(ws.iter_rows(max_row=1, values_only=True), ())]
    col = {h: head.index(h) for h in ("date", "venue", "set", "start", "end") if h in head}
    rows = defaultdict(dict)                          # date -> {set: (venue, start, end)}
    for r in ws.iter_rows(min_row=2, values_only=True):
        r = tuple(r) + (None,) * (len(head) + 1 - len(r))
        try:
            d, k = to_date(r[col.get("date", 0)]), int(r[col.get("set", 3)])
            start = to_time(r[col["start"]]) if "start" in col else None
            end = to_time(r[col["end"]]) if "end" in col else None
        except (ValueError, TypeError):
            continue                                  # read_schedule reports unreadable rows
        if d:
            rows[d][k] = (str(r[col.get("venue", 2)] or "").strip(), start, end)
    # as in core.slots: a regular show day's own flag; any other night is preferred when its venue is
    by_day = {(sd.weekday, sd.venue.casefold()): sd.supervision_preferred for sd in settings.show_days}
    preferred_venues = {sd.venue.casefold() for sd in settings.show_days if sd.supervision_preferred}

    def minutes(a, b):
        return int((dt.combine(dt.min, b) - dt.combine(dt.min, a)).total_seconds() // 60)
    nights = []
    for d, sets in sorted(rows.items()):
        venue, first, end1 = sets[min(sets)]
        length = minutes(first, end1) if first and end1 else 0
        gap = minutes(end1, sets[2][1]) if first and end1 and 2 in sets and sets[2][1] else 0
        nights.append(Night(d, venue, max(sets), first if length > 0 else None, max(length, 0), max(gap, 0),
                            by_day.get((d.weekday(), venue.casefold()), venue.casefold() in preferred_venues)))
    return nights


def open_label(settings):
    """What an open set says in Schedule.xlsx."""
    return "OPEN - volunteer" if settings.extra_slot_policy == "open" else "(empty)"


def write_swap(path, changes, combos, open_label):
    """Writes swapped sets into the Combo column of Schedule.xlsx (everything else, including hand edits, stays).
    changes = {(date, set number): combo id or None (open)}. A copy of the file as it was goes into a
    'App data/Schedule backups' folder in the data folder first. Returns the backup's path."""
    import shutil
    from datetime import datetime
    from openpyxl import load_workbook
    from util import app_data, to_date
    path = Path(path)
    backups = app_data(path.parent) / "Schedule backups"
    backups.mkdir(parents=True, exist_ok=True)
    backup = backups / f"{path.stem} {datetime.now():%Y-%m-%d %H%M%S}{path.suffix}"
    shutil.copy2(path, backup)
    wb = load_workbook(path)
    ws = wb["Schedule"]
    head = [str(v or "").strip().lower() for v in next(ws.iter_rows(max_row=1, values_only=True), ())]
    di, si, ci = (head.index(h) if h in head else j for h, j in (("date", 0), ("set", 3), ("combo", 4)))
    todo = dict(changes)
    for row in ws.iter_rows(min_row=2):
        try:
            key = (to_date(row[di].value), int(row[si].value))
        except (ValueError, TypeError):
            continue
        if key in todo:
            c = todo.pop(key)
            row[ci].value = combos[c].name if c else open_label
    if todo:
        raise ScheduleFileError("Couldn't find these sets in Schedule.xlsx: "
                                + ", ".join(f"{d} set {k}" for d, k in sorted(todo)) + ". Nothing was changed.")
    try:
        wb.save(path)
    except PermissionError:
        raise ScheduleFileError(f"Can't save {path.name}: it's open in Excel. Close it and try again. "
                                "Nothing was changed.")
    return backup
