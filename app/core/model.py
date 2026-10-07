"""Plain data structures. This is the ONLY contract between the scheduler core and the outside world.

An input adapter (see adapters/) builds a ScheduleInput. The core returns a Result.
Nothing in core/ knows about Excel, Forms, or McGill email formats.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEEKDAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def make_label(d: date) -> str:
    """'Tue Oct 14'. Fixed English names so a French-language machine can't change the output."""
    return f"{WEEKDAY_ABBR[d.weekday()]} {MONTH_ABBR[d.month - 1]} {d.day}"


def format_time(t: time, suffix=True) -> str:
    """20:45 -> '8:45 pm' (or '8:45' without the suffix). Fixed English, like make_label."""
    return f"{t.hour % 12 or 12}:{t.minute:02d}" + ((" am" if t.hour < 12 else " pm") if suffix else "")


class ScheduleError(Exception):
    """The schedule can't be built; the message is meant for the director."""


@dataclass(frozen=True)
class ShowDay:
    weekday: int            # 0 = Monday
    venue: str
    slots: int              # combo sets per show night
    min_per_combo: int = 0  # every combo must play at least this many nights at this venue
    first_set: Optional[time] = None   # start time of set 1 (None = no set times)
    set_length: int = 0                # minutes each set lasts
    break_minutes: int = 0             # minutes between one set's end and the next set's start
    supervision_preferred: bool = False   # supervised nights should fall on this show day (ShowDays column H)


@dataclass
class Settings:
    semester_name: str
    start_date: date
    end_date: date
    show_days: List[ShowDay]
    skip_dates: Dict[date, str] = field(default_factory=dict)
    extra_dates: List[Tuple[date, str, int]] = field(default_factory=list)   # (date, venue, slots)
    extra_times: Dict[date, Tuple[Optional[time], int, int]] = field(default_factory=dict)  # (first_set, set_length, break)
    min_days_between_shows: int = 14
    first_year_earliest_date: Optional[date] = None
    max_blocked_dates_per_person: Optional[int] = 3
    min_usable_nights_per_combo: Optional[int] = 3
    min_members_per_combo: Optional[int] = 4      # warning only: combos with fewer members are flagged
    max_shows_per_combo: Optional[int] = 4
    min_shows_per_combo: Optional[int] = None   # total, at any venues (venue minimums still apply); open mode: exactly.
                                                # Required in semester.json; None only for a hand-built Settings
    extra_slot_policy: str = "auto"       # "auto": fill every set. "open": leave extras for volunteers
    solver_time_limit_sec: float = 90
    every_combo_supervised: bool = True   # every combo plays nights a professor attends (off = no supervision)
    min_supervised_per_combo: int = 1     # ...at least this many each (with supervision on)
    max_supervised_nights: Optional[int] = None   # cap on those nights (None = no cap); within it, as few as possible
    supervision_timing: str = "none"      # supervised nights preferred "early" or "late" in the semester, or "none"
    first_year_first_show_supervised: bool = True   # a first-year combo's first show on a supervised night (soft)
    use_first_year: bool = True           # off: no combo is treated as first-year (the input adapter clears the flag)
    # Read by the input adapter only (the core never sees an email rule): the students' address domain (blank = any),
    # and domain typos to correct, {typed domain: real domain}.
    student_email_domain: str = ""
    email_domain_fixes: Dict[str, str] = field(default_factory=dict)
    professor_email_domain: str = ""


@dataclass(frozen=True)
class Night:
    date: date
    venue: str
    n_slots: int
    first_set: Optional[time] = None
    set_length: int = 0
    break_minutes: int = 0
    supervision_preferred: bool = False

    @property
    def label(self) -> str:
        return make_label(self.date)

    def set_time(self, k: int) -> Optional[time]:
        """Start time of set k (1-based), or None when this night has no set times."""
        if self.first_set is None:
            return None
        start = datetime.combine(self.date, self.first_set)
        return (start + timedelta(minutes=(k - 1) * (self.set_length + self.break_minutes))).time()

    def set_end(self, k: int) -> Optional[time]:
        """End time of set k, or None when this night has no set times."""
        t = self.set_time(k)
        return None if t is None else (datetime.combine(self.date, t) + timedelta(minutes=self.set_length)).time()

    def set_range(self, k: int, suffix=True) -> str:
        """'7:00–7:45 pm' (or '7:00–7:45' without the suffix); '' when this night has no set times."""
        t = self.set_time(k)
        if t is None:
            return ""
        end = self.set_end(k)
        both = suffix and (t.hour < 12) != (end.hour < 12)           # '11:30 am–12:15 pm' when it crosses noon
        return f"{format_time(t, both)}\u2013{format_time(end, suffix)}"

    @property
    def weekday(self) -> str:
        return WEEKDAYS[self.date.weekday()]


@dataclass
class Combo:
    id: str                       # unique within the semester (the parser uses the combo name)
    name: str
    members: FrozenSet[str]       # normalised student identifiers (emails)
    first_year: bool = False
    liaison: str = ""             # leader's email (Student 1 on the form)
    professor: str = ""           # supervising professor's email (display only; not used by the solver yet)
    ref: str = ""                 # id in the data source (the Forms response Id); bookkeeping only




@dataclass
class ScheduleInput:
    combos: List[Combo]                            # approved combos only
    blocked: Dict[str, Set[date]]                  # student -> dates they cannot play
    notes: List[Tuple[str, str]] = field(default_factory=list)  # (level, text) from the adapter
    withdrawn: List[Combo] = field(default_factory=list)        # withdrawn in the app (shown, never scheduled)
    pending: List[Combo] = field(default_factory=list)          # waiting for a decision (shown, never scheduled)


@dataclass
class Result:
    nights: List[Night]
    lineup: Dict[date, List[str]]                  # night -> combo ids in set order
    combos: Dict[str, Combo]
    open_sets: List[Tuple[Night, int, List[str]]]  # (night, set number, eligible combos)
    report: List[Tuple[str, str]]                  # (level, text)
    stats: dict
    supervised: Set[date] = field(default_factory=set)   # nights that need a professor
