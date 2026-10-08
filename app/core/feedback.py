"""Moving feedback nights on an existing schedule (Schedule tab: Move / Make / Remove feedback night), checked like a
swap: the same rule check as --stats (every combo on enough feedback nights, feedback nights full, the cap, a
first-year combo's first show), before and after. What it would break is listed (and asked about), what it only
makes less ideal is a warning: a combo on more than one feedback night, a night that isn't a 'Feedback nights
preferred' show day, the wrong half of the semester for the settings' timing.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Set

from .model import Combo, Night, ScheduleInput, Settings, make_label
from .stats import schedule_stats


@dataclass
class FeedbackOption:
    source: Optional[date]                     # the feedback night it stops being (None: one is added)
    target: Optional[date]                     # the night that becomes one (None: one is removed)
    title: str
    notes: List[str] = field(default_factory=list)      # which combos gain or lose a feedback night
    warnings: List[str] = field(default_factory=list)   # less ideal, allowed
    breaks: List[str] = field(default_factory=list)     # hard rules it breaks (asked before it's added)
    score: float = 0.0                         # lower = better


def feedback_option(sets, nights: List[Night], combos: Dict[str, Combo], inp: ScheduleInput, settings: Settings,
                    supervised: Set[date], typed: Dict, source: Optional[date], target: Optional[date],
                    name_of=lambda e: e, before=None) -> FeedbackOption:
    """source -> target (either may be None: add or remove one). before: the rule check's problems now (worked out
    here when not given)."""
    nmap = {n.date: n for n in nights}

    def problems(sup):
        return set(schedule_stats(sets, nights, combos, inp, settings, sup, name_of, typed)[1])
    if before is None:
        before = problems(supervised)
    after_sup = (set(supervised) - {source}) | ({target} if target else set())
    breaks = sorted(problems(after_sup) - before)

    def playing(d):
        return {c for c in sets.get(d, {}).values() if c} if d else set()
    gain, lose = playing(target) - playing(source), playing(source) - playing(target)
    count = {c: sum(1 for d in after_sup if c in playing(d)) for c in combos}
    name = lambda c: combos[c].name
    notes = ([f"{', '.join(sorted(map(name, lose)))} no longer on a feedback night there"] if lose else []) + (
        [f"{', '.join(sorted(map(name, gain)))} now on a feedback night"] if gain else [])
    warnings = [f"{name(c)} would be on {count[c]} feedback nights" for c in sorted(gain, key=name) if count[c] > 1]
    if target:
        if any(n.supervision_preferred for n in nights) and not nmap[target].supervision_preferred:
            warnings.append(f"{nmap[target].venue} isn't a 'Feedback nights preferred' show day")
        if settings.supervision_timing in ("early", "late") and nights:
            mid = nights[0].date + (nights[-1].date - nights[0].date) / 2
            if (target <= mid) != (settings.supervision_timing == "early"):
                half = "first" if settings.supervision_timing == "early" else "second"
                warnings.append(f"not in the {half} half of the semester (preferred)")
    if source and target:
        title = f"Move the feedback night from {make_label(source)} to {make_label(target)}"
    elif target:
        title = f"Make {make_label(target)} a feedback night"
    else:
        title = f"{make_label(source)} is no longer a feedback night"
    distance = abs((target - source).days) if source and target else 0
    return FeedbackOption(source, target, title, notes, warnings, breaks,
                          score=1000 * len(breaks) + 10 * len(warnings) + distance / 100)


def feedback_moves(sets, nights: List[Night], combos: Dict[str, Combo], inp: ScheduleInput, settings: Settings,
                   supervised: Set[date], typed: Dict, source: date, name_of=lambda e: e) -> List[FeedbackOption]:
    """Every night the feedback night `source` could move to, best first (rule-breaking ones last)."""
    before = set(schedule_stats(sets, nights, combos, inp, settings, supervised, name_of, typed)[1])
    return sorted((feedback_option(sets, nights, combos, inp, settings, supervised, typed, source, n.date, name_of,
                                   before) for n in nights if n.date not in supervised),
                  key=lambda o: (o.score, o.target))
