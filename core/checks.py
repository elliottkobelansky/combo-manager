"""Data-source-independent checks on a ScheduleInput, plus the per-combo 'allowed nights'."""
from typing import Dict, List, Set, Tuple

from .model import Night, ScheduleInput, Settings


def analyze(inp: ScheduleInput, settings: Settings, nights: List[Night]):
    """Returns (allowed, report). allowed[combo_id] = set of night dates the combo can play."""
    report: List[Tuple[str, str]] = []
    night_dates = {n.date for n in nights}
    members_all = set().union(*[c.members for c in inp.combos]) if inp.combos else set()

    person_blocked = {e: ds & night_dates for e, ds in inp.blocked.items()}
    non_show = sum(len(ds - night_dates) for e, ds in inp.blocked.items() if e in members_all)
    if non_show:
        report.append(("info", f"{non_show} blocked date(s) were not show nights (no effect)."))
    stray = sorted(e for e in inp.blocked if e not in members_all)
    if stray:
        report.append(("warn", f"{len(stray)} student(s) submitted conflicts but aren't in any approved combo "
                               f"(e.g. {', '.join(stray[:3])}). Their dates are ignored."))

    limit = settings.max_blocked_dates_per_person
    if limit:
        for e in sorted(members_all):
            n = len(person_blocked.get(e, ()))
            if n > limit:
                report.append(("warn", f"{e} blocked {n} show nights (soft limit {limit})."))

    allowed: Dict[str, Set] = {}
    seen_sets = {}
    for c in inp.combos:
        blocked = set().union(*[person_blocked.get(m, set()) for m in c.members]) if c.members else set()
        ok = night_dates - blocked
        allowed[c.id] = ok                     # the first-year cutoff is a strong preference, handled by the solver
        if c.first_year and settings.first_year_earliest_date:
            ok = {d for d in ok if d >= settings.first_year_earliest_date}
        if not c.members:
            report.append(("warn", f"{c.name} has no members."))
        elif len(c.members) < 2:
            report.append(("warn", f"{c.name} has only {len(c.members)} member."))
        mu = settings.min_usable_nights_per_combo
        if mu and len(ok) < mu:
            why = ", first-year rule" if c.first_year else ""
            report.append(("warn", f"{c.name} has only {len(ok)} usable nights (pooled member conflicts{why})."))
        if c.members in seen_sets and c.members:
            report.append(("warn", f"{c.name} has exactly the same members as {seen_sets[c.members]}: "
                                   "duplicate submission?"))
        seen_sets.setdefault(c.members, c.name)
    return allowed, report
