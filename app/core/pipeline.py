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
        raise ScheduleError("No show nights were generated. Check the dates and ShowDays in Settings.")
    combos = {c.id: c for c in inp.combos}
    if not combos:
        raise ScheduleError("There are no combos for this semester.")

    report = list(inp.notes)
    allowed, check_report = analyze(inp, settings, nights)
    report += check_report
    show_min = venue_minimums(settings)

    problems = (precheck(combos, allowed, nights, show_min) + precheck_total(combos, allowed, settings)
                + precheck_supervision(combos, nights, settings))
    if problems:
        raise ScheduleError("Can't build a schedule. Problems found in the input:\n" + "\n".join(f"  - {p}" for p in problems))

    chosen, stats = solve_combos(combos, allowed, nights, show_min, settings)
    if chosen is None:
        warns = "\n".join(f"  - {t}" for lvl, t in report if lvl == "warn")
        raise ScheduleError(f"No valid schedule found (solver status: {stats}).\n"
                            "Common causes: too many pooled conflicts, a first-year combo with few usable nights, "
                            "or combos sharing members who are all blocked on the same dates. Warnings so far:\n" + warns)

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
