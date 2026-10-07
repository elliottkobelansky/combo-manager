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
        many = [(e, len(person_blocked.get(e, ()))) for e in sorted(members_all)
                if len(person_blocked.get(e, ())) > limit]
        if many:                                      # one line for all of them
            report.append(("warn", f"{len(many)} student(s) blocked more than {limit} show nights: "
                                   + ", ".join(f"{e} ({n})" for e, n in many) + "."))

    allowed: Dict[str, Set] = {}
    seen_sets = {}
    for c in inp.combos:
        blocked = set().union(*[person_blocked.get(m, set()) for m in c.members]) if c.members else set()
        ok = night_dates - blocked
        allowed[c.id] = ok                     # the first-year cutoff is a strong preference, handled by the solver
        if c.first_year and settings.first_year_earliest_date:
            ok = {d for d in ok if d >= settings.first_year_earliest_date}
        few = settings.min_members_per_combo
        if not c.members:
            report.append(("warn", f"{c.name} has no members."))
        elif few and len(c.members) < few:
            report.append(("warn", f"{c.name} has only {len(c.members)} member{'s' if len(c.members) > 1 else ''} "
                                   f"(fewer than {few})."))
        mu = settings.min_usable_nights_per_combo
        if mu and len(ok) < mu:
            why = ", first-year rule" if c.first_year else ""
            report.append(("warn", f"{c.name} has only {len(ok)} usable nights (pooled member conflicts{why})."))
        if c.members in seen_sets and c.members:
            report.append(("warn", f"{c.name} has exactly the same members as {seen_sets[c.members]}: "
                                   "duplicate submission?"))
        seen_sets.setdefault(c.members, c.name)
    return allowed, report


def instrument_limits(combos, instruments, settings: Settings, rhythm, name_of=lambda e: e):
    """Warnings for players in more combos than the Semester tab allows: max_combos_rhythm for anyone playing a
    rhythm-section instrument (rhythm: a set of names) in one of their combos, max_combos_other for the rest. People
    with no instrument set aren't checked. instruments: {(combo name, email): instrument}."""
    where: Dict[str, List[str]] = {}
    for c in sorted(combos, key=lambda c: c.name):
        for e in c.members:
            where.setdefault(e, []).append(c.name)
    out = []
    for e, names in sorted(where.items(), key=lambda x: name_of(x[0]).lower()):
        played = {instruments[(n, e)] for n in names if instruments.get((n, e))}
        if not played:
            continue
        is_rhythm = bool(played & set(rhythm))
        limit = settings.max_combos_rhythm if is_rhythm else settings.max_combos_other
        if limit and len(names) > limit:
            out.append(f"{name_of(e)} ({', '.join(sorted(played))}) is in {len(names)} combos "
                       f"({', '.join(names)}): the limit for {'rhythm-section' if is_rhythm else 'other'} players is "
                       f"{limit}.")
    return out


def check_new_combo(new, combos, blocked, nights, settings: Settings, instruments, rhythm, name_of=lambda e: e):
    """What approving `new` (a combo waiting for a decision) would mean, next to the accepted `combos`. -> (problems:
    it couldn't be scheduled as things are, heads_ups: worth knowing). blocked: {email: dates}; instruments:
    {(combo name, email): instrument}, with the new combo's members' usual instruments under its name."""
    problems, heads = [], []
    if not new.members:
        return ["It has no members."], []
    night_dates = {n.date for n in nights}
    no = set().union(*[set(blocked.get(e, ())) for e in new.members]) & night_dates
    ok = night_dates - no
    show_min = {}
    for sd in settings.show_days:
        show_min[sd.venue] = max(show_min.get(sd.venue, 0), sd.min_per_combo)
    for venue in sorted({n.venue for n in nights}):
        need = show_min.get(venue, 0)
        usable = sum(1 for n in nights if n.venue == venue and n.date in ok)
        sets = sum(n.n_slots for n in nights if n.venue == venue)
        if need and usable < need:
            problems.append(f"Its members' conflicts leave {usable} usable {venue} night(s); every combo needs {need}.")
        if need and (len(combos) + 1) * need > sets:
            problems.append(f"{venue} has {sets} sets: not enough for {len(combos) + 1} combos x {need} show(s).")
    if settings.min_shows_per_combo and len(ok) < settings.min_shows_per_combo:
        problems.append(f"Its members' conflicts leave {len(ok)} usable night(s); every combo needs "
                        f"{settings.min_shows_per_combo}.")
    elif settings.min_usable_nights_per_combo and len(ok) < settings.min_usable_nights_per_combo:
        heads.append(f"Only {len(ok)} usable nights (its members' conflicts).")
    few = settings.min_members_per_combo
    if few and len(new.members) < few:
        heads.append(f"Only {len(new.members)} member{'s' if len(new.members) != 1 else ''} (fewer than {few}).")
    if not new.professor:
        heads.append("No supervisor listed.")
    for c in combos:
        if c.members == new.members:
            heads.append(f"The same members as {c.name}: a duplicate submission?")
    for e in sorted(new.members, key=lambda e: name_of(e).lower()):
        others = sorted(c.name for c in combos if e in c.members)
        if others:
            heads.append(f"{name_of(e)} is also in {', '.join(others)}.")
    heads += [w for w in instrument_limits(list(combos) + [new], instruments, settings, rhythm, name_of)
              if any(f"{name_of(e)} (" in w for e in new.members)]
    return problems, heads
