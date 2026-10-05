"""The settings: settings.json, edited in the app's Settings tab (scheduler_app.py), read into a core.Settings object
with plain-language checks.

    python app/settings_file.py --new              # write a settings.json with example values (refuses to overwrite)

settings.json is plain text; you can read it, but the app is the easy way to change it. Dates are YYYY-MM-DD, set
times HH:MM (24-hour).
"""
import json
import re
import sys
from pathlib import Path

from core.model import WEEKDAYS, Settings, ShowDay
from util import DATA_FOLDER, blank, to_date, to_time

SETTINGS_FILE = "settings.json"

DEFAULTS = {
    "semester_name": "Winter 2027",
    "start_date": "2027-01-12",
    "end_date": "2027-04-09",
    "use_first_year": True,
    "first_year_earliest_date": "2027-01-26",
    "min_days_between_shows": 28,
    "max_blocked_dates_per_person": 3,
    "min_usable_nights_per_combo": 3,
    "extra_slot_policy": "open",
    "min_shows_per_combo": 2,
    "max_shows_per_combo": 4,
    "every_combo_supervised": True,
    "max_supervised_nights": 10,
    "solver_time_limit_sec": 30,
    "student_email_domain": "mail.mcgill.ca",
    "email_domain_fixes": "mcgill.ca -> mail.mcgill.ca",
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
    "min_days_between_shows": "Ideal gap between one combo's shows; closer pairs are avoided, the closer the more.",
    "max_blocked_dates_per_person": "Warning only: flags students who blocked more show nights than this.",
    "min_usable_nights_per_combo": "Warning only: flags combos whose members' conflicts leave fewer usable nights.",
    "extra_slot_policy": "Leave open: each combo gets its shows; the sets left over stay open for volunteers, or you "
                         "fill them by hand (Schedule or Swaps tab). Fill every set: some combos get extra shows.",
    "min_shows_per_combo": "Every combo gets at least this many shows, at any venues (each venue's minimum still "
                           "applies). With leftover sets left open: exactly this many.",
    "max_shows_per_combo": "Cap on total shows per combo. Blank = no cap.",
    "every_combo_supervised": "On: every combo plays at least one night a professor attends from start to end (that "
                              "night has no open sets). Off: no supervised nights.",
    "max_supervised_nights": "The most supervised nights in the whole semester, counting all professors together "
                             "(not per professor). One night covers every combo playing it. Blank = no limit (still "
                             "as few as possible).",
    "solver_time_limit_sec": "How long the solver searches (roughly seconds). 30 is plenty unless it says FEASIBLE.",
    "student_email_domain": "Students' email domain, e.g. mail.mcgill.ca. Other addresses are fine, just listed. "
                            "Blank = don't check.",
    "email_domain_fixes": "Domain slips to correct, e.g. mcgill.ca -> mail.mcgill.ca, gmial.com -> gmail.com. "
                          "Blank = none.",
}

# Settings saved before these existed keep McGill's behaviour.
LEGACY = {"student_email_domain": "mail.mcgill.ca", "email_domain_fixes": "mcgill.ca -> mail.mcgill.ca"}


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


def validate(data):
    """data (the settings.json contents) -> (Settings, warnings). Raises SettingsError listing everything wrong."""
    errors, warnings = [], []

    def get_date(key, required=True, where="Settings"):
        v = data.get(key)
        if blank(v):
            if required:
                errors.append(f"{where}: '{key}' is missing.")
            return None
        try:
            return to_date(v)
        except ValueError as e:
            errors.append(f"{where} {key}: {e}. Use YYYY-MM-DD.")

    def get_int(key, default=None, low=None):
        v = data.get(key)
        if blank(v):
            return default
        try:
            n = int(float(v))
        except (TypeError, ValueError):
            errors.append(f"Settings {key}: expected a whole number, found {v!r}.")
            return default
        if low is not None and n < low:
            errors.append(f"Settings {key}: must be {low} or more.")
            return default
        return n

    name = str(data.get("semester_name") or "").strip()
    if not name:
        errors.append("Settings: 'semester_name' is missing.")
    start, end = get_date("start_date"), get_date("end_date")
    if start and end and end < start:
        errors.append(f"Settings: end_date ({end}) is before start_date ({start}).")

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
        errors.append("Settings extra_slot_policy must be open or auto.")
    domain = str(data.get("student_email_domain", LEGACY["student_email_domain"]) or "").strip().lstrip("@").lower()
    if domain and ("." not in domain or " " in domain):
        errors.append(f"Settings student_email_domain: '{domain}' isn't an email domain (e.g. mail.mcgill.ca).")
    try:
        fixes = parse_domain_fixes(data.get("email_domain_fixes", LEGACY["email_domain_fixes"]))
    except ValueError as e:
        errors.append(f"Settings email_domain_fixes: {e}.")
        fixes = {}
    fy_date = get_date("first_year_earliest_date", required=False)
    # settings saved before the switch existed: on exactly when there's a date
    use_first_year = bool(data["use_first_year"]) if "use_first_year" in data else bool(fy_date)
    if use_first_year and fy_date is None and blank(data.get("first_year_earliest_date")):
        errors.append("First-year combos is on, but the date they can start playing is blank. Pick that date, or "
                      "turn first-year combos off.")
    min_total, max_total = get_int("min_shows_per_combo", low=1), get_int("max_shows_per_combo", low=1)
    if min_total is None and blank(data.get("min_shows_per_combo")):
        errors.append("Settings: the minimum shows per combo is missing (e.g. 2).")
    if min_total and max_total and min_total > max_total:
        errors.append(f"Settings: min_shows_per_combo ({min_total}) is more than max_shows_per_combo ({max_total}).")
    settings = Settings(
        semester_name=name, start_date=start, end_date=end, show_days=show_days,
        skip_dates=skips, extra_dates=extras, extra_times=extra_times,
        min_days_between_shows=get_int("min_days_between_shows", 14, low=0) or 0,
        first_year_earliest_date=fy_date if use_first_year else None,
        max_blocked_dates_per_person=get_int("max_blocked_dates_per_person", low=0),
        min_usable_nights_per_combo=get_int("min_usable_nights_per_combo", low=0),
        max_shows_per_combo=max_total,
        min_shows_per_combo=min_total,
        extra_slot_policy=policy,
        solver_time_limit_sec=get_int("solver_time_limit_sec", 30, low=1) or 30,
        every_combo_supervised=bool(data.get("every_combo_supervised", True)),
        max_supervised_nights=get_int("max_supervised_nights", low=1),
        use_first_year=use_first_year,
        student_email_domain=domain,
        email_domain_fixes=fixes,
    )
    if errors:
        raise SettingsError("\n".join(f"  - {e}" for e in errors))
    timed = [sd for sd in show_days if sd.first_set is not None]
    if timed and len(timed) < len(show_days):
        warnings.append("Only some show days have set times; the others will show set numbers instead.")
    return settings, warnings


def read_data(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SettingsError(f"Can't find {path}. Open the app's Settings tab (or run: python app/settings_file.py --new).")
    except ValueError as e:
        raise SettingsError(f"{path} isn't valid settings ({e}). Fix it in the app, or restore a backup.")


def save_data(path, data):
    """Writes settings.json, keeping the previous version as settings.json.bak."""
    path = Path(path)
    if path.exists():
        path.with_name(path.name + ".bak").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_settings(path):
    """settings.json -> (Settings, warnings)."""
    return validate(read_data(Path(path)))


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--new"]:
        path = DATA_FOLDER / SETTINGS_FILE
        if path.exists():
            sys.exit(f"{path} already exists.")
        DATA_FOLDER.mkdir(exist_ok=True)
        save_data(path, DEFAULTS)
        print(f"Wrote {path} with example values.")
    else:
        print(__doc__)
