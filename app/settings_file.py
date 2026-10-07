"""The settings: semester.json, edited in the app's Semester tab (scheduler_app.py), read into a core.Settings object
with plain-language checks.

    python app/settings_file.py --new FOLDER       # write a semester.json with example values into FOLDER's AppFiles
                                                   # (refuses to overwrite)

semester.json is plain text; you can read it, but the app is the easy way to change it. Dates are YYYY-MM-DD, set
times HH:MM (24-hour).
"""
import json
import re
import sys
from pathlib import Path

from core.model import WEEKDAYS, Settings, ShowDay
from shared_folder import write_text
from data_folder import problem, settings_path
from util import blank, to_date, to_time

DEFAULTS = {
    "semester_name": "Winter 2027",
    "start_date": "2027-01-12",
    "end_date": "2027-04-09",
    "use_first_year": True,
    "first_year_earliest_date": "2027-01-26",
    "first_year_first_show_supervised": True,
    "min_days_between_shows": 28,
    "max_blocked_dates_per_person": 3,
    "min_usable_nights_per_combo": 3,
    "min_members_per_combo": 4,
    "extra_slot_policy": "open",
    "min_shows_per_combo": 2,
    "max_shows_per_combo": 4,
    "min_supervised_per_combo": 1,
    "max_supervised_nights": 10,
    "supervision_timing": "none",
    "solver_time_limit_sec": 90,
    "student_email_domain": "mail.mcgill.ca",
    "professor_email_domain": "mcgill.ca",
    "show_days": [
        {"weekday": "Tuesday", "venue": "Upstairs", "sets": 4, "min_per_combo": 1, "first_set": "19:00",
         "set_length": 45, "break": 15, "supervision_preferred": True},
        {"weekday": "Friday", "venue": "Clara", "sets": 4, "min_per_combo": 0, "first_set": "19:00",
         "set_length": 30, "break": 15, "supervision_preferred": False},
    ],
    "skip_dates": [{"date": "2027-03-02", "reason": "PLACEHOLDER - reading week"},
                   {"date": "2027-03-05", "reason": "PLACEHOLDER - reading week"}],
    "extra_dates": [],
}

# What each general setting means (shown in the app next to the field, and in the README).
HELP = {
    "semester_name": "Must match the form's Semester answer exactly (e.g. Winter 2027).",
    "start_date": "First day shows could happen.",
    "end_date": "Last day shows could happen.",
    "use_first_year": "On: combos marked First year in the approvals don't play before the date below (unless "
                      "there's no other way). Off: every combo is treated the same.",
    "first_year_earliest_date": "The first day first-year combos can play. Needed while the switch above is on.",
    "first_year_first_show_supervised": "On: a first-year combo's first show is on a supervised night, so they get "
                                        "feedback on their first set (a strong preference, can add a supervised "
                                        "night). Needs supervised nights on.",
    "min_days_between_shows": "Ideal gap between one combo's shows; closer pairs are avoided, the closer the more.",
    "max_blocked_dates_per_person": "Warning only: flags students who blocked more show nights than this.",
    "min_usable_nights_per_combo": "Warning only: flags combos whose members' conflicts leave fewer usable nights.",
    "min_members_per_combo": "Warning only: flags combos with fewer members than this (e.g. after someone is "
                             "removed in the Combos tab). Blank = no warning.",
    "extra_slot_policy": "Leave open: each combo gets its shows; the sets left over stay open for volunteers, or you "
                         "fill them by hand (Schedule or Swaps tab). Fill every set: some combos get extra shows.",
    "min_shows_per_combo": "Every combo gets at least this many shows, at any venues (each venue's minimum still "
                           "applies). With leftover sets left open: exactly this many.",
    "max_shows_per_combo": "Cap on total shows per combo. Blank = no cap.",
    "min_supervised_per_combo": "How many nights each combo plays with a professor attending from start to end "
                                "(those nights have no open sets). Usually 1; 0 = no supervised nights at all.",
    "max_supervised_nights": "The most supervised nights in the whole semester, all professors together "
                             "(not per professor). One night covers every combo playing it. Blank = no limit (still "
                             "as few as possible).",
    "supervision_timing": "A light preference for when the supervised nights fall: earlier or later in the "
                          "semester. First-year combos' first shows still come first.",
    "solver_time_limit_sec": "How long the solver searches (roughly seconds). 90 is plenty: it stops early once it has the best schedule.",
    "student_email_domain": "Students' email domain, e.g. mail.mcgill.ca. Other addresses are fine, just listed. "
                            "Blank = don't check.",
    "professor_email_domain": "Supervisors' email domain, e.g. mcgill.ca: a supervisor with another address is "
                              "pointed out (a typo?). Blank = don't check.",
}

# Settings saved before these existed keep McGill's behaviour. (Domain fixes are no longer set in the app: an
# email is fixed in the Combos tab; settings that still have some keep them.)
LEGACY = {"student_email_domain": "mail.mcgill.ca", "professor_email_domain": "mcgill.ca"}


def parse_domain_fixes(text):
    """'mcgill.ca -> mail.mcgill.ca, gmial.com -> gmail.com' -> {typed: real}. Also takes '=' or '→', and a dict.
    Raises ValueError naming the part it can't read."""
    if isinstance(text, dict):
        pairs = text.items()
    else:
        pairs = []
        for part in re.split(r"[,;\n]+", str(text or "")):
            if not part.strip():
                continue
            bits = re.split(r"\s*(?:->|→|=)\s*", part.strip())
            if len(bits) != 2 or not all(bits):
                raise ValueError(f"can't read '{part.strip()}'. Write it as typed.domain -> real.domain")
            pairs.append(bits)
    fixes = {}
    for typed, real in pairs:
        typed, real = str(typed).strip().lstrip("@").lower(), str(real).strip().lstrip("@").lower()
        if "." not in typed or "." not in real or " " in typed + real:
            raise ValueError(f"'{typed} -> {real}' doesn't look like two email domains")
        fixes[typed] = real
    return fixes


class SettingsError(Exception):
    pass


# what the Semester tab calls each setting (for messages)
LABELS = {"semester_name": "Semester name", "start_date": "First possible show day",
          "end_date": "Last possible show day", "min_shows_per_combo": "Minimum shows per combo",
          "max_shows_per_combo": "Maximum shows per combo", "min_days_between_shows": "Ideal days between shows",
          "first_year_earliest_date": "First-year combos play from",
          "min_supervised_per_combo": "Supervised nights per combo",
          "max_supervised_nights": "Max supervised nights (all professors)",
          "student_email_domain": "Student email domain", "professor_email_domain": "Professor email domain",
          "max_blocked_dates_per_person": "Warn: conflicts per person",
          "min_usable_nights_per_combo": "Warn: usable nights per combo",
          "min_members_per_combo": "Warn: members per combo", "solver_time_limit_sec": "Solver time (seconds)"}


def label(key):
    return LABELS.get(key, key)


def validate(data):
    """data (the semester.json contents) -> (Settings, warnings). Raises SettingsError listing everything wrong."""
    errors, warnings = [], []

    def get_date(key, required=True):
        v = data.get(key)
        if blank(v):
            if required:
                errors.append(f"Semester tab: '{label(key)}' is blank.")
            return None
        try:
            return to_date(v)
        except ValueError as e:
            errors.append(f"Semester tab: '{label(key)}': {e}. Use YYYY-MM-DD.")

    def get_int(key, default=None, low=None):
        v = data.get(key)
        if blank(v):
            return default
        try:
            n = int(float(v))
        except (TypeError, ValueError):
            errors.append(f"Semester tab: '{label(key)}' should be a whole number, not {v!r}.")
            return default
        if low is not None and n < low:
            errors.append(f"Semester tab: '{label(key)}' must be {low} or more.")
            return default
        return n

    name = str(data.get("semester_name") or "").strip()
    if not name:
        errors.append(f"Semester tab: '{label('semester_name')}' is blank.")
    start, end = get_date("start_date"), get_date("end_date")
    if start and end and end < start:
        errors.append(f"Semester tab: the last possible show day ({end}) is before the first ({start}).")

    def set_times(row, where):
        try:
            first = to_time(row.get("first_set"))
        except ValueError as e:
            errors.append(f"{where}: first set start {e}. Use e.g. 19:00.")
            return None, 0, 0
        length, brk = row.get("set_length"), row.get("break")
        try:
            length = int(length) if not blank(length) else 0
            brk = int(brk) if not blank(brk) else 0
            assert length >= 0 and brk >= 0
        except (TypeError, ValueError, AssertionError):
            errors.append(f"{where}: set length and break must be whole numbers of minutes.")
            return None, 0, 0
        if first is not None and not length:
            errors.append(f"{where}: there's a first set start but no set length.")
        if first is None and (length or brk):
            errors.append(f"{where}: set length or break is filled in but the first set start is blank.")
        return first, length, brk

    show_days, seen = [], set()
    lookup = {w.lower(): i for i, w in enumerate(WEEKDAYS)}
    for n, row in enumerate(data.get("show_days") or [], start=1):
        where = f"Show day {n}"
        wd, venue = str(row.get("weekday") or "").strip(), str(row.get("venue") or "").strip()
        if wd.lower() not in lookup:
            errors.append(f"{where}: '{wd}' is not a weekday.")
            continue
        if not venue:
            errors.append(f"{where} ({wd}): the venue is blank.")
            continue
        try:
            sets = int(row.get("sets"))
            assert sets >= 1
            min_pc = int(row.get("min_per_combo") or 0)
            assert min_pc >= 0
        except (TypeError, ValueError, AssertionError):
            errors.append(f"{where} ({wd}): sets must be 1 or more and the minimum per combo 0 or more.")
            continue
        idx = lookup[wd.lower()]
        if idx in seen:
            errors.append(f"{where}: {WEEKDAYS[idx]} appears more than once.")
            continue
        seen.add(idx)
        show_days.append(ShowDay(idx, venue, sets, min_pc, *set_times(row, f"{where} ({wd})"),
                                 bool(row.get("supervision_preferred"))))
    if not show_days and not any(e.startswith("Show day") for e in errors):
        errors.append("Show days: none defined.")

    skips = {}
    for row in data.get("skip_dates") or []:
        try:
            d = to_date(row.get("date"))
        except ValueError as e:
            errors.append(f"Skip dates: {e}.")
            continue
        if d is None:
            continue
        if start and end and not (start <= d <= end):
            warnings.append(f"Skip date {d} is outside the semester; ignored.")
        else:
            skips[d] = str(row.get("reason") or "")

    venue_times = {}
    for sd in show_days:
        if sd.first_set is not None:
            venue_times.setdefault(sd.venue.casefold(), (sd.first_set, sd.set_length, sd.break_minutes))
    extras, extra_times = [], {}
    for row in data.get("extra_dates") or []:
        try:
            d = to_date(row.get("date"))
            n = int(row.get("sets"))
        except (ValueError, TypeError):
            errors.append("Extra dates: each needs a real date and a number of sets.")
            continue
        venue = str(row.get("venue") or "").strip()
        if d is None or not venue:
            errors.append(f"Extra date {d}: the date or venue is blank.")
        elif start and end and not (start <= d <= end):
            errors.append(f"Extra date {d} is outside the semester.")
        else:
            extras.append((d, venue, n))
            times = set_times(row, f"Extra date {d}")
            extra_times[d] = times if times[0] is not None else venue_times.get(venue.casefold(), times)

    policy = str(data.get("extra_slot_policy") or "open").strip().lower()
    if policy not in ("auto", "open"):
        errors.append("Semester tab: 'Leftover sets' must be 'Leave open' or 'Fill every set'.")
    domain = str(data.get("student_email_domain", LEGACY["student_email_domain"]) or "").strip().lstrip("@").lower()
    if domain and ("." not in domain or " " in domain):
        errors.append(f"Semester tab: '{label('student_email_domain')}': '{domain}' isn't an email domain "
                      "(e.g. mail.mcgill.ca).")
    try:
        fixes = parse_domain_fixes(data.get("email_domain_fixes", ""))
    except ValueError as e:
        errors.append(f"Semester tab: email domain fixes: {e}.")
        fixes = {}
    prof_domain = str(data.get("professor_email_domain", LEGACY["professor_email_domain"]) or "").strip().lstrip(
        "@").lower()
    if prof_domain and ("." not in prof_domain or " " in prof_domain):
        errors.append(f"Semester tab: '{label('professor_email_domain')}': '{prof_domain}' isn't an email domain "
                      "(e.g. mcgill.ca).")
    # supervised nights per combo; settings from before say only on (1) or off (0)
    min_sup = (get_int("min_supervised_per_combo", low=0) if "min_supervised_per_combo" in data
               else 1 if data.get("every_combo_supervised", True) else 0) or 0
    fy_date = get_date("first_year_earliest_date", required=False)
    # settings saved before the switch existed: on exactly when there's a date
    use_first_year = bool(data["use_first_year"]) if "use_first_year" in data else bool(fy_date)
    if use_first_year and fy_date is None and blank(data.get("first_year_earliest_date")):
        errors.append("First-year combos is on, but the date they can start playing is blank. Pick that date, or "
                      "turn first-year combos off.")
    timing = str(data.get("supervision_timing") or "none").strip().lower()
    if timing not in ("none", "early", "late"):
        errors.append("Semester tab: 'Supervised nights preferred' must be 'Any time', 'Earlier in the semester' or 'Later in the semester'.")
    min_total, max_total = get_int("min_shows_per_combo", low=1), get_int("max_shows_per_combo", low=1)
    if min_total is None and blank(data.get("min_shows_per_combo")):
        errors.append("Semester tab: the minimum shows per combo is missing (e.g. 2).")
    if min_total and max_total and min_total > max_total:
        errors.append(f"Semester tab: the minimum shows per combo ({min_total}) is more than the maximum ({max_total}).")
    settings = Settings(
        semester_name=name, start_date=start, end_date=end, show_days=show_days,
        skip_dates=skips, extra_dates=extras, extra_times=extra_times,
        min_days_between_shows=get_int("min_days_between_shows", 14, low=0) or 0,
        first_year_earliest_date=fy_date if use_first_year else None,
        max_blocked_dates_per_person=get_int("max_blocked_dates_per_person", low=0),
        min_usable_nights_per_combo=get_int("min_usable_nights_per_combo", low=0),
        min_members_per_combo=get_int("min_members_per_combo", low=1) if "min_members_per_combo" in data else 4,
        max_shows_per_combo=max_total,
        min_shows_per_combo=min_total,
        extra_slot_policy=policy,
        solver_time_limit_sec=get_int("solver_time_limit_sec", 90, low=1) or 90,
        every_combo_supervised=min_sup > 0,
        min_supervised_per_combo=max(min_sup, 1),
        max_supervised_nights=get_int("max_supervised_nights", low=1),
        supervision_timing=timing,
        first_year_first_show_supervised=bool(data.get("first_year_first_show_supervised", True)),
        use_first_year=use_first_year,
        student_email_domain=domain,
        email_domain_fixes=fixes,
        professor_email_domain=prof_domain,
    )
    if errors:
        raise SettingsError("\n".join(f"  - {e}" for e in errors))
    timed = [sd for sd in show_days if sd.first_set is not None]
    if timed and len(timed) < len(show_days):
        warnings.append("Only some show days have set times; the others will show set numbers instead.")
    warnings += year_warnings(settings)
    return settings, warnings


def year_warnings(s):
    """A year in the semester name ('Winter 2027'; '2026-2027' allows both) that the dates don't match: likely
    last semester's dates left in. A warning only."""
    years = {int(y) for y in re.findall(r"\b(?:19|20)\d{2}\b", s.semester_name)}
    if not years:
        return []
    dates = ([("first show day", s.start_date), ("last show day", s.end_date)]
             + [("skip date", d) for d in sorted(s.skip_dates)] + [("extra date", d) for d, _, _ in s.extra_dates])
    off = [f"{what} {d}" for what, d in dates if d and d.year not in years]
    if not off:
        return []
    return [f"The semester is '{s.semester_name}', but these dates are in another year: {', '.join(off)}. "
            "Leftover dates from an earlier semester?"]


def read_data(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SettingsError("No settings yet: fill them in on the Semester tab and click Save.")
    except ValueError as e:
        raise SettingsError(f"{path} isn't valid settings ({e}). Fix it in the app, or restore a backup.")


def save_data(path, data):
    """Writes semester.json, keeping the previous version as semester.json.bak."""
    path = Path(path)
    if path.exists():
        write_text(path.with_name(path.name + ".bak"), path.read_text(encoding="utf-8"))
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def load_settings(path):
    """semester.json -> (Settings, warnings)."""
    return validate(read_data(Path(path)))


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--new"] and len(args) == 2:
        if problem(args[1]):
            sys.exit(f"Can't use {args[1]} as the data folder: {problem(args[1])}.")
        path = settings_path(args[1])
        if path.exists():
            sys.exit(f"{path} already exists.")
        save_data(path, DEFAULTS)
        print(f"Wrote {path} with example values.")
    else:
        print(__doc__)
