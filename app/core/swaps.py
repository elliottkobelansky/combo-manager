"""Swap finder: every legal way to change one show of one combo, best first.

Works on the schedule as it is on disk (after earlier swaps and hand edits), like solve.py --stats. For a chosen show
(combo A on night d, set k) it tries
  - a trade with every other combo's show (B on night d2, set k2): A takes B's place and B takes A's;
  - a move to every open set (blank / OPEN; not sets with something typed in);
  - giving the show away: to every combo not playing that night (A has one show fewer, B one more), or leaving
    it open. Only possible when A doesn't need it (venue minimum, min_shows_per_combo, supervision);
and keeps the options that break no hard rule the schedule didn't already break (the same rule check as --stats:
conflicts, twice in a night, venue minimums, total shows, supervision). Soft rules are reported, not blocked:
a student playing twice in one night, shows closer together, a first-year combo before the first-year date.
Three-way swaps aren't tried.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Set, Tuple

from .model import Combo, Night, ScheduleInput, Settings, make_label
from .solver import venue_minimums
from .stats import schedule_stats

Sets = Dict[date, Dict[int, Optional[str]]]   # {night: {set number: combo id or None (open)}}


@dataclass
class SwapOption:
    kind: str                                  # "trade", "move", "give" (to another combo), "drop" (leave open), "claim"
    title: str                                 # one line, e.g. "Trade with Combo 12: ..."
    changes: Dict[Tuple[date, int], Optional[str]]   # (night, set) -> new combo id, None = open
    notes: List[str] = field(default_factory=list)   # what else changes (spacing, venue, set time)
    warnings: List[str] = field(default_factory=list)   # soft rules broken by this swap
    score: float = 0.0                         # lower = better
    partner: str = ""                          # who it swaps with: a combo name, or "open set"
    place: str = ""                            # where the chosen combo plays instead
    same_night: bool = False                   # only the running order changes


def shows_of(sets: Sets, cid: str) -> List[Tuple[date, int]]:
    return sorted((d, k) for d, row in sets.items() for k, c in row.items() if c == cid)


def closest_gap(days: List[date]) -> Optional[int]:
    days = sorted(days)
    return min(((b - a).days for a, b in zip(days, days[1:])), default=None)


def doubles(sets: Sets, d: date, combos: Dict[str, Combo]) -> Set[str]:
    """Students playing more than once on night d."""
    seen, twice = set(), set()
    for c in sets.get(d, {}).values():
        for m in (combos[c].members if c else ()):
            (twice if m in seen else seen).add(m)
    return twice


def swap_options(sets: Sets, nights: List[Night], combos: Dict[str, Combo], inp: ScheduleInput, settings: Settings,
                 supervised: Optional[Set[date]], typed: Dict, cid: str, d: Optional[date] = None,
                 k: Optional[int] = None, name_of=lambda e: e, slot=None) -> List[SwapOption]:
    """Options for combo cid's show on night d, set k. Without d and k: the open sets cid could claim (only the
    open set `slot` = (night, set) if given)."""
    nmap = {n.date: n for n in nights}

    def problems(s):
        return set(schedule_stats(s, nights, combos, inp, settings, supervised, name_of, typed)[1])
    before = problems(sets)

    def label(dd, kk):
        n = nmap.get(dd)
        when = n.set_range(kk) if n else ""
        return f"{make_label(dd)} set {kk}" + (f" ({when})" if when else "") + (f", {n.venue}" if n else "")

    def place(dd, kk):
        n = nmap.get(dd)
        return " \u00b7 ".join(x for x in (make_label(dd), f"set {kk}", n.set_range(kk) if n else "",
                                             n.venue if n else "") if x)

    me = combos[cid].name
    candidates = []                            # (kind, changes, title, partner, place, same_night)
    if d is None:                              # claim: take an open set without giving anything up
        for d2 in sorted(nmap):
            if cid in sets.get(d2, {}).values():
                continue
            for k2 in range(1, nmap[d2].n_slots + 1):
                if slot and (d2, k2) != slot:
                    continue
                if sets.get(d2, {}).get(k2) is None and k2 not in typed.get(d2, {}):
                    candidates.append(("claim", {(d2, k2): cid}, f"Claim the open set {label(d2, k2)}",
                                       "open set", place(d2, k2), False))
    for d2 in sorted(set(sets) | set(nmap)) if d is not None else []:
        row = sets.get(d2, {})
        for k2 in range(1, nmap[d2].n_slots + 1) if d2 in nmap else []:
            if (d2, k2) == (d, k) or k2 in typed.get(d2, {}):
                continue
            other = row.get(k2)
            if other == cid:
                continue
            changes = {(d, k): other, (d2, k2): cid}
            if other is None:
                title = (f"Move to set {k2} the same night ({label(d2, k2)})" if d2 == d else
                         f"Move to the open set {label(d2, k2)}")
                candidates.append(("move", changes, title, "open set", place(d2, k2), d2 == d))
            else:
                name = combos[other].name
                title = (f"Swap set order with {name} (set {k} \u2194 set {k2}, same night)" if d2 == d else
                         f"Trade with {name}: {me} plays {label(d2, k2)}; {name} plays {label(d, k)}")
                candidates.append(("trade", changes, title, name, place(d2, k2), d2 == d))
    # give the show away: to a combo not playing that night, or leave the set open
    playing = {c for c in sets.get(d, {}).values() if c}
    for other in sorted(combos, key=lambda c: combos[c].name) if d is not None else []:
        if other not in playing:
            candidates.append(("give", {(d, k): other}, f"Give it to {combos[other].name}: they play {label(d, k)}; "
                               f"{me} has one show fewer", combos[other].name, place(d, k), False))
    if d is not None:
        candidates.append(("drop", {(d, k): None}, f"Give it up: {label(d, k)} becomes an open set; {me} has one "
                           "show fewer", "nobody (leave open)", place(d, k), False))

    cutoff = settings.first_year_earliest_date
    show_min = venue_minimums(settings)

    def summary(s, c):
        days = [x for x, _ in shows_of(s, c)]
        return dict(days=days, gap=closest_gap(days), n=len(days),
                    venues={v: sum(1 for x in days if nmap[x].venue == v) for v in {n.venue for n in nights}},
                    sup=sum(1 for x in days if supervised and x in supervised),
                    early=sum(1 for x in days if combos[c].first_year and cutoff and x < cutoff))

    options = []
    for kind, changes, title, partner, where, same in candidates:
        new = {dd: dict(row) for dd, row in sets.items()}
        for (dd, kk), c in changes.items():
            new.setdefault(dd, {})[kk] = c
        after = problems(new)
        if after - before:
            continue                                         # breaks a hard rule: not offered
        opt = SwapOption(kind, title, changes, partner=partner, place=where, same_night=same)
        for fixed in sorted(before - after):
            opt.notes.insert(0, f"Fixes: {fixed}")
            opt.score -= 20
        # soft rules and side effects, per night and per combo touched
        for dd in sorted({dd for dd, _ in changes}):
            extra = doubles(new, dd, combos) - doubles(sets, dd, combos)
            if extra:
                opt.warnings.append(f"{', '.join(sorted(name_of(m) for m in extra))} would play twice on "
                                    f"{make_label(dd)}")
        touched = {c for c in [sets.get(dd, {}).get(kk) for dd, kk in changes] + list(changes.values()) if c}
        for c in sorted(touched, key=lambda c: combos[c].name):
            a, b, name = summary(sets, c), summary(new, c), combos[c].name
            if b["n"] != a["n"]:
                opt.notes.append(f"{name}: {a['n']} \u2192 {b['n']} shows")
            if b["early"] > a["early"]:
                opt.warnings.append(f"{name} is a first-year combo and would play before {make_label(cutoff)}")
            cap = max(settings.min_shows_per_combo or 0, sum(show_min.values()))
            if (combos[c].first_year and settings.extra_slot_policy != "open"
                    and b["n"] > cap and b["n"] > a["n"]):
                opt.warnings.append(f"{name} is a first-year combo and would get an extra show (they normally "
                                    "don't)")
            if b["n"] == a["n"]:
                for v in sorted(a["venues"]):
                    if a["venues"][v] and not b["venues"][v]:
                        opt.warnings.append(f"{name} would no longer play at {v}")
                    elif b["venues"][v] and not a["venues"][v]:
                        opt.notes.append(f"{name} would play at {v} too")
            if b["days"] == a["days"]:
                continue
            if b["gap"] is not None and (a["gap"] is None or b["gap"] < a["gap"]):
                msg = f"{name}'s shows {b['gap']} days apart" + (f" (was {a['gap']})" if a["gap"] is not None else "")
                (opt.warnings if b["gap"] < 14 else opt.notes).append(msg)
                opt.score += max(0, (a["gap"] or b["gap"]) - b["gap"]) / 7
            elif b["gap"] is not None and a["gap"] is not None and b["gap"] > a["gap"]:
                opt.notes.append(f"{name}'s shows {b['gap']} days apart (was {a['gap']})")
            moved = [v for v in a["venues"] if a["venues"][v] != b["venues"][v]]
            if moved and b["n"] == a["n"]:
                opt.notes.append(f"{name}: " + ", ".join(f"{v} {a['venues'][v]}\u2192{b['venues'][v]}" for v in sorted(moved)))
            if b["sup"] != a["sup"]:
                opt.notes.append(f"{name} {'gains' if b['sup'] > a['sup'] else 'leaves'} a supervised night")
        if kind == "move" and not same:
            opt.notes.append(f"{label(d, k)} becomes open")
        opt.score += 10 * len(opt.warnings) + 0.5 * len(opt.notes) + {"trade": 0, "move": 0.2}.get(kind, 0)
        options.append(opt)
    return sorted(options, key=lambda o: (o.same_night, o.score, o.title))   # other nights first


def claimers(sets: Sets, nights: List[Night], combos: Dict[str, Combo], inp: ScheduleInput, settings: Settings,
             supervised: Optional[Set[date]], typed: Dict, d: date, k: int, name_of=lambda e: e) -> List[SwapOption]:
    """Every combo that could legally take the open set (d, k), best first."""
    out = []
    for cid in sorted(combos, key=lambda c: combos[c].name):
        out += swap_options(sets, nights, combos, inp, settings, supervised, typed, cid, name_of=name_of, slot=(d, k))
    return sorted(out, key=lambda o: (o.score, o.title))


def apply_option(sets: Sets, option: SwapOption) -> Sets:
    new = {dd: dict(row) for dd, row in sets.items()}
    for (dd, kk), c in option.changes.items():
        new.setdefault(dd, {})[kk] = c
    return new


def involved(sets: Sets, option: SwapOption, combos: Dict[str, Combo], first: Optional[str] = None) -> List[str]:
    """The combos whose shows the option changes: `first` (the combo it was found for) first, then by name."""
    ids = {c for (d, k), new in option.changes.items() for c in (sets.get(d, {}).get(k), new) if c}
    return sorted(ids, key=lambda c: (c != first, combos[c].name))


def swap_summary(sets: Sets, nights: List[Night], combos: Dict[str, Combo], option: SwapOption,
                 first: Optional[str] = None, name_of=lambda e: e) -> str:
    """The option in plain words, for the combos it touches: a heading, then what changes for each of them (both
    sides of a trade or a give-away), sets that become open, heads-ups, and the liaisons' names (no emails: those are
    copied separately). sets: before the option."""
    nmap = {n.date: n for n in nights}

    def where(cell, near=None):
        """'Fri Oct 16, set 2 (8:00–8:30 pm), Clara'; just 'set 2 (8:00–8:30 pm)' when on the same night as near."""
        d, k = cell
        n = nmap.get(d)
        when = f"set {k}" + (f" ({n.set_range(k)})" if n and n.set_range(k) else "")
        return when if near and near[0] == d else f"{make_label(d)}, {when}" + (f", {n.venue}" if n else "")

    old = {cell: sets.get(cell[0], {}).get(cell[1]) for cell in option.changes}
    after = apply_option(sets, option)
    ids = involved(sets, option, combos, first)
    names = [combos[c].name for c in ids]
    moves = {}
    for c in ids:
        lost = [cell for cell, was in sorted(old.items()) if was == c and option.changes[cell] != c]
        gained = [cell for cell, now in sorted(option.changes.items()) if now == c and old[cell] != c]
        moves[c] = (lost[0] if lost else None, gained[0] if gained else None)

    a = names[0]
    givers = [c for c in ids if moves[c][0] and not moves[c][1]]
    takers = [c for c in ids if moves[c][1] and not moves[c][0]]
    if len(ids) == 2 and option.same_night:
        heading = f"{a} and {names[1]} swap set order on {make_label(next(iter(option.changes))[0])}"
    elif len(ids) == 2 and not givers:
        heading = f"{a} and {names[1]} trade shows"
    elif len(ids) == 2:
        heading = f"{combos[givers[0]].name} gives a show to {combos[takers[0]].name}"
    elif givers:
        heading = f"{a} gives up a show (the set becomes open)"
    elif takers:
        heading = f"{a} takes an open set"
    else:
        heading = f"{a} moves to " + ("another set the same night" if option.same_night else "an open set")
    lines = [heading, ""]

    def count(c, s):
        return sum(1 for row in s.values() for x in row.values() if x == c)
    for c in ids:
        lost, gained = moves[c]
        name, shows = combos[c].name, f"({count(c, sets)} → {count(c, after)} shows)"
        was_open = ", an open set until now" if gained and old[gained] is None else ""
        if lost and gained:
            lines.append(f"• {name} now plays {where(gained)}{was_open}, instead of {where(lost, gained)}.")
        elif gained:
            lines.append(f"• {name} now also plays {where(gained)}{was_open} {shows}.")
        elif lost:
            lines.append(f"• {name} no longer plays {where(lost)} {shows}.")
    lines += [f"• {where(cell)} becomes an open set." for cell, now in sorted(option.changes.items())
              if now is None and old[cell] is not None]
    if option.warnings:
        lines += [""] + [f"Heads-up: {w}." for w in option.warnings]
    contacts = [f"{combos[c].name}: {name_of(combos[c].liaison)}" for c in ids
                if combos[c].liaison]
    if contacts:
        lines += ["", ("Liaison: " if len(contacts) == 1 else "Liaisons: ") + "; ".join(contacts)]
    return "\n".join(lines)
