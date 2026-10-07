"""The one function the outside world calls: run_schedule(ScheduleInput, Settings) -> Result."""
from collections import defaultdict

from .checks import analyze
from .model import Result, ScheduleError, ScheduleInput, Settings, make_label
from .slots import generate_nights
from .solver import (open_set_options, order_sets, precheck, precheck_supervision, precheck_total, solve_combos,
                     venue_minimums)


def run_schedule(inp: ScheduleInput, settings: Settings) -> Result:
    nights = generate_nights(settings)
    if not nights:
        raise ScheduleError("There are no show nights: check the first and last show day, the show days and the "
                            "skip dates (Settings tab).")
    combos = {c.id: c for c in inp.combos}
    if not combos:
        raise ScheduleError("There are no combos for this semester yet (Combos tab: enter them, or link the "
                            "sign-up sheet and Sync).")

    report = list(inp.notes)
    allowed, check_report = analyze(inp, settings, nights)
    report += check_report
    show_min = venue_minimums(settings)

    problems = (precheck(combos, allowed, nights, show_min) + precheck_total(combos, allowed, settings)
                + precheck_supervision(combos, nights, settings))
    if problems:
        raise ScheduleError("No schedule is possible as things are:\n" + "\n".join(f"  - {p}" for p in problems)
                            + "\n\nChange the settings (Settings tab) or the combos and conflicts (Combos tab), then "
                            "try again.")

    chosen, stats = solve_combos(combos, allowed, nights, show_min, settings)
    if chosen is None:
        raise ScheduleError(why_no_schedule(stats, combos, allowed, nights, show_min, settings, report))

    lineup = order_sets(chosen, nights, combos)
    open_sets = open_set_options(lineup, nights, combos, allowed) if settings.extra_slot_policy == "open" else []

    total = sum(n.n_slots for n in nights)
    empty = sum(n.n_slots - len(lineup.get(n.date, [])) for n in nights)
    report.append(("info", f"Solver status: {stats['status']} (objective {stats['objective']:.0f}, "
                           f"lower bound {stats['bound']:.0f})."))
    report.append(("info", f"{total - empty} of {total} sets filled; {empty} "
                           f"{'open for volunteers' if settings.extra_slot_policy == 'open' else 'empty'}."))
    for n, k, el in open_sets:
        if not el:
            report.append(("warn", f"Open set {n.label} #{k}: no combo can take it."))
    for d, c in stats["early_first_year"]:
        report.append(("warn", f"First-year {combos[c].name} plays {make_label(d)}, before the first-year date "
                               f"({make_label(settings.first_year_earliest_date)}): it had no other way to get its show."))
    for d, a, b in stats["shared_nights"]:
        who = ", ".join(sorted(combos[a].members & combos[b].members))
        report.append(("warn", f"{make_label(d)}: {combos[a].name} and {combos[b].name} both play; "
                               f"{who} play(s) twice that night."))
    if settings.every_combo_supervised:
        sup = sorted(stats["supervised"])
        cap = settings.max_supervised_nights
        report.append(("info", f"Supervised nights (a professor attends), {len(sup)}"
                               f"{f' of at most {cap}' if cap else ''}: {', '.join(make_label(d) for d in sup)}."))
        for c in stats["first_year_unsupervised"]:
            first = min(d for d, cs in lineup.items() if c in cs)
            report.append(("warn", f"First-year {combos[c].name}'s first show ({make_label(first)}) isn't on a "
                                   "supervised night: no way to fit it without breaking a more important goal."))
    if stats["spacing_violations"]:
        report.append(("warn", f"{int(stats['spacing_violations'])} pair(s) of shows for one combo are closer than "
                               f"{settings.min_days_between_shows} days."))
    counts = defaultdict(lambda: defaultdict(int))
    for n in nights:
        for c in lineup.get(n.date, []):
            counts[c][n.venue] += 1
    for v in sorted({n.venue for n in nights}):
        vals = [counts[c][v] for c in combos]
        report.append(("info", f"{v}: shows per combo range from {min(vals)} to {max(vals)}."))
        none_here = sorted(combos[c].name for c in combos if counts[c][v] == 0)
        if none_here and not show_min.get(v, 0):
            report.append(("info", f"{v}: {len(none_here)} combo(s) have no show here (their shows are at other "
                                   f"venues, usually because of conflicts): {', '.join(none_here)}."))

    stats.update(total_sets=total, empty_sets=empty)
    return Result(nights=nights, lineup=lineup, combos=combos, open_sets=open_sets, report=report, stats=stats,
                  supervised=set(stats["supervised"]))


def why_no_schedule(status, combos, allowed, nights, show_min, settings, report):
    """The message when the solver finds nothing: whether it's impossible or it ran out of time, the numbers from the
    settings that are tightest, and what to change."""
    if status != "INFEASIBLE":
        head = (f"No schedule found in the time allowed ({settings.solver_time_limit_sec:g} seconds). It may still "
                "be possible: try a longer 'Solver time' (Settings tab). If that doesn't help, the settings are "
                "probably too tight:")
    else:
        head = "No schedule fits these settings: it's impossible as they are, not just hard. The tightest numbers:"
    n, sets = len(combos), sum(nt.n_slots for nt in nights)
    lines = []
    need = n * (settings.min_shows_per_combo or 1)
    lines.append(f"{n} combos x {settings.min_shows_per_combo or 1} show(s) = {need} shows needed; there are {sets} "
                 f"sets on {len(nights)} nights." + (" Too few: lower 'Minimum shows per combo' or add nights."
                                                     if need > sets else ""))
    for venue, low in sorted(show_min.items()):
        if low:
            room = sum(nt.n_slots for nt in nights if nt.venue == venue)
            lines.append(f"{venue}: every combo needs {low} show(s) there = {n * low}; it has {room} sets."
                         + (" Too few: lower that show day's minimum." if n * low > room else ""))
    if settings.every_combo_supervised:
        cap, per = settings.max_supervised_nights, settings.min_supervised_per_combo
        lines.append(f"Supervision: {per} supervised night(s) per combo, "
                     + (f"at most {cap} supervised nights" if cap else "no limit on supervised nights")
                     + " (a supervised night has no open sets).")
    tight = sorted((len(allowed[c]), combos[c].name) for c in combos)[:3]
    lines.append("Fewest usable nights (members' conflicts): " + ", ".join(f"{name} {k}" for k, name in tight) + ".")
    warns = [t for lvl, t in report if lvl == "warn"][:6]
    return (head + "\n" + "\n".join(f"  - {x}" for x in lines)
            + "\n\nWhat usually helps: lower 'Minimum shows per combo' or a venue's minimum, allow more supervised "
            "nights, add show nights, or turn first-year combos off for a moment to see if they're the cause."
            + ("\n\nWarnings from the combos and conflicts:\n" + "\n".join(f"  - {w}" for w in warns) if warns else ""))
