"""Statistics and a rule check for a finished schedule.

Works on a freshly solved schedule or on the saved one after swaps (schedule_file.py), so it
re-checks the hard rules rather than trusting the solver.
"""
from collections import Counter, defaultdict
from statistics import median
from datetime import date
from typing import Callable, Dict, List, Optional, Set, Tuple

from .model import Combo, Night, ScheduleInput, Settings, make_label
from .solver import venue_minimums

Sets = Dict  # {date: {set number: combo id, or None for an open/empty set}}


def counts_line(counter, unit):
    """Counter({2: 30, 3: 3}) -> '2 shows: 30 combos, 3 shows: 3 combos'"""
    return ", ".join(f"{k} show{'' if k == 1 else 's'}: {v} {unit}{'' if v == 1 else 's'}"
                     for k, v in sorted(counter.items()))


def schedule_stats(sets: Sets, nights: List[Night], combos: Dict[str, Combo], inp: ScheduleInput,
                   settings: Settings, supervised: Optional[Set[date]] = None,
                   name_of: Optional[Callable[[str], str]] = None, typed: Optional[Dict] = None
                   ) -> Tuple[List[Tuple[str, List[str]]], List[str]]:
    """Returns (sections, problems). sections = [(title, lines)]; problems = broken hard rules.
    supervised = nights marked as supervised (None = not tracked by this schedule).
    typed = {date: {set number: text}}: sets with something other than a combo typed in; they count as taken."""
    typed = typed or {}
    n_typed = sum(len(v) for v in typed.values())
    name_of = name_of or (lambda e: e)
    nmap = {n.date: n for n in nights}
    venues = sorted({n.venue for n in nights})
    sections, problems = [], []

    # ---- what is playing where
    shows = defaultdict(list)                              # combo -> [(date, set number)]
    for d in sorted(sets):
        if d not in nmap:
            problems.append(f"{make_label(d)} is in the schedule but isn't a show night in the Semester tab.")
            continue
        seen = set()
        for k, c in sorted(sets[d].items()):
            if c is None:
                continue
            if k > nmap[d].n_slots:
                problems.append(f"{make_label(d)}: set {k}, but that night only has {nmap[d].n_slots} sets.")
            if c in seen:
                problems.append(f"{make_label(d)}: {combos[c].name} plays twice.")
            seen.add(c)
            shows[c].append((d, k))

    # ---- overview
    lines = []
    total = sum(n.n_slots for n in nights)
    filled = sum(len(v) for v in shows.values())
    open_word = "open for volunteers" if settings.extra_slot_policy == "open" else "empty"
    lines.append(f"{len(nights)} show nights, {total} sets: {filled} filled by combos, "
                 + (f"{n_typed} with other entries, " if n_typed else "") + f"{total - filled - n_typed} {open_word}.")
    for v in venues:
        vn = [n for n in nights if n.venue == v]
        vs = sum(n.n_slots for n in vn)
        vf = sum(1 for ss in shows.values() for d, _ in ss if nmap[d].venue == v)
        lines.append(f"  {v}: {len(vn)} nights, {vs} sets, {vf} filled.")
    sections.append(("Overview", lines))

    # ---- shows per combo
    per_venue = {c: Counter(nmap[d].venue for d, _ in shows.get(c, [])) for c in combos}
    lines = [f"Total: {counts_line(Counter(len(shows.get(c, [])) for c in combos), 'combo')}."]
    for v in venues:
        lines.append(f"  {v}: {counts_line(Counter(per_venue[c][v] for c in combos), 'combo')}.")
    none = sorted(combos[c].name for c in combos if not shows.get(c))
    if none:
        lines.append(f"No shows at all: {', '.join(none)}.")
    sections.append(("Shows per combo", lines))

    # ---- hard rules
    show_min = venue_minimums(settings)
    for c, ss in shows.items():
        for d, k in ss:
            for m in sorted(combos[c].members):
                if d in inp.blocked.get(m, ()):
                    problems.append(f"{make_label(d)}: {combos[c].name} plays, but {name_of(m)} ({m}) "
                                    "marked a conflict that night.")
    for c in combos:
        for v, need in show_min.items():
            if per_venue[c][v] < need:
                problems.append(f"{combos[c].name} has {per_venue[c][v]} {v} show(s) but needs {need}.")
        need = settings.min_shows_per_combo
        if need and len(shows.get(c, [])) < need:
            problems.append(f"{combos[c].name} has {len(shows.get(c, []))} show(s) but needs {need} (Semester tab: "
                            "minimum shows per combo).")
        cap = settings.max_shows_per_combo
        if cap and len(shows.get(c, [])) > cap:
            problems.append(f"{combos[c].name} has {len(shows[c])} shows, more than the cap of {cap}.")

    # ---- supervision
    if settings.every_combo_supervised:
        if supervised is None:
            sections.append(("Supervision", ["This schedule doesn't track supervised nights, so supervision isn't checked."]))
        else:
            sup = sorted(d for d in supervised if d in nmap)
            cap = settings.max_supervised_nights
            on_sup = defaultdict(list)
            for c, ss in shows.items():
                on_sup[c] = [d for d, _ in ss if d in supervised]
            lines = [f"{len(sup)} supervised night(s){f' (at most {cap})' if cap else ''}: "
                     + (", ".join(make_label(d) for d in sup) or "none") + "."]
            lines.append(f"Combos on more than one supervised night: {sum(1 for c in combos if len(on_sup[c]) > 1)}.")
            pref = [d for d in sup if nmap[d].supervision_preferred]
            if any(n.supervision_preferred for n in nights):
                lines.append(f"On a 'Supervision preferred' show day: {len(pref)} of {len(sup)}.")
            fy = [c for c in combos if combos[c].first_year and shows.get(c)]
            if fy and settings.first_year_first_show_supervised:
                missed = sorted(combos[c].name for c in fy if min(d for d, _ in shows[c]) not in supervised)
                lines.append(f"First-year combos whose first show is supervised: {len(fy) - len(missed)} of {len(fy)}"
                             + (f" (not: {', '.join(missed)})." if missed else "."))
            if sup and settings.supervision_timing in ("early", "late"):
                first, last = nights[0].date, nights[-1].date
                mid = first + (last - first) / 2
                half = sum(1 for d in sup if (d <= mid) == (settings.supervision_timing == "early"))
                lines.append(f"In the {'first' if settings.supervision_timing == 'early' else 'second'} half of the "
                             f"semester (preferred): {half} of {len(sup)}.")
            sections.append(("Supervision", lines))
            need = settings.min_supervised_per_combo
            for c in combos:
                if len(on_sup[c]) < need:
                    problems.append(f"{combos[c].name} plays {len(on_sup[c])} supervised night(s) but needs {need}.")
            for d in sup:
                empty = [k for k in range(1, nmap[d].n_slots + 1)
                         if sets.get(d, {}).get(k) is None and k not in typed.get(d, {})]
                if empty:
                    problems.append(f"{make_label(d)} is a supervised night but has open set(s) "
                                    f"{', '.join(map(str, empty))}: supervised nights must be full.")
            if cap and len(sup) > cap:
                problems.append(f"{len(sup)} supervised nights, more than the settings' maximum of {cap}.")

    # ---- spacing
    gaps = []                                              # (days, combo, d1, d2)
    for c, ss in shows.items():
        ds = sorted(d for d, _ in ss)
        gaps += [((b - a).days, c, a, b) for a, b in zip(ds, ds[1:])]
    if gaps:
        days = sorted(g[0] for g in gaps)
        buckets = [("under 7 days", 0, 7), ("7-13", 7, 14), ("14-20", 14, 21), ("21-27", 21, 28), ("28+", 28, 10 ** 6)]
        lines = [f"Closest {days[0]} days, median {median(days):.0f}, widest {days[-1]} "
                 f"(ideal set in the Semester tab: {settings.min_days_between_shows}).",
                 "  " + ", ".join(f"{label}: {sum(lo <= x < hi for x in days)}" for label, lo, hi in buckets) + "."]
        closest = sorted(gaps, key=lambda g: (g[0], combos[g[1]].name))[:5]
        lines.append("Closest pairs: " + "; ".join(f"{combos[c].name} {make_label(a)} -> {make_label(b)} ({g} days)"
                                                     for g, c, a, b in closest) + ".")
    else:
        lines = ["No combo has more than one show."]
    sections.append(("Spacing between a combo's shows", lines))

    # ---- running order
    first, last = Counter(), Counter()                     # playing set 1 / the night's last set
    for d, row in sets.items():
        if d in nmap:
            if row.get(1) is not None:
                first[row[1]] += 1
            if row.get(nmap[d].n_slots) is not None:
                last[row[nmap[d].n_slots]] += 1
    always_first = sorted(combos[c].name for c, ss in shows.items() if len(ss) > 1 and first[c] == len(ss))
    always_last = sorted(combos[c].name for c, ss in shows.items() if len(ss) > 1 and last[c] == len(ss))
    lines = [f"{sum(1 for c in combos if first[c])} combos open a night at least once; "
             f"{sum(1 for c in combos if first[c] > 1)} open more than once.",
             f"{sum(1 for c in combos if last[c])} combos close a night at least once; "
             f"{sum(1 for c in combos if last[c] > 1)} close more than once."]
    if always_first:
        lines.append(f"Open every one of their shows: {', '.join(always_first)}.")
    if always_last:
        lines.append(f"Close every one of their shows: {', '.join(always_last)}.")
    sections.append(("Running order", lines))

    # ---- students
    member_of = defaultdict(list)
    for c in combos.values():
        for m in c.members:
            member_of[m].append(c.id)
    per_student = {m: sum(len(shows.get(c, [])) for c in cs) for m, cs in member_of.items()}
    multi = sum(1 for cs in member_of.values() if len(cs) > 1)
    lines = [f"{len(member_of)} students; {multi} are in more than one combo.",
             f"Shows per student: {counts_line(Counter(per_student.values()), 'student')}."]
    doubles = []
    for d, row in sorted(sets.items()):
        tonight = defaultdict(list)
        for k, c in sorted(row.items()):
            if c is not None:
                for m in combos[c].members:
                    tonight[m].append(k)
        for m, ks in sorted(tonight.items()):
            if len(ks) > 1:
                doubles.append(f"{make_label(d)}: {name_of(m)} plays sets {', '.join(map(str, ks))}")
    lines.append("Nobody plays twice in one night." if not doubles else
                 f"Playing twice in one night ({len(doubles)}): " + "; ".join(doubles) + ".")
    sections.append(("Students", lines))

    # ---- first-year combos
    fy = [c for c in combos if combos[c].first_year]
    cutoff = settings.first_year_earliest_date
    if fy:
        early = [f"{combos[c].name} {make_label(d)}" for c in fy for d, _ in shows.get(c, []) if cutoff and d < cutoff]
        lines = [f"{len(fy)} first-year combos."]
        if cutoff:
            lines.append(f"All play on or after {make_label(cutoff)}." if not early else
                         f"Before {make_label(cutoff)} ({len(early)}): {', '.join(early)}.")
        sections.append(("First-year combos", lines))

    # ---- typed entries
    if n_typed:
        sections.append(("Other entries (shown on the PDF as typed)",
                         [f"{make_label(d)} set {k}: {t}" for d in sorted(typed) for k, t in sorted(typed[d].items())]))

    # ---- open sets
    if total > filled + n_typed:
        lines, nobody = [], []
        for n in nights:
            row = sets.get(n.date, {})
            playing = {c for c in row.values() if c is not None}
            for k in range(1, n.n_slots + 1):
                if row.get(k) is not None or k in typed.get(n.date, {}):
                    continue
                ok = [c for c in combos if c not in playing
                      and not any(n.date in inp.blocked.get(m, ()) for m in combos[c].members)]
                if not ok:
                    nobody.append(f"{n.label} set {k}")
        lines.append(f"{total - filled - n_typed} set(s) {open_word}. " +
                     ("Every one has at least one combo that could take it." if not nobody else
                      f"No combo can take: {', '.join(nobody)}."))
        sections.append(("Open sets", lines))

    return sections, problems
