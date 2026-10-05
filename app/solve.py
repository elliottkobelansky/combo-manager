"""settings.json + Combo Approvals.xlsx + Conflicts.xlsx -> Schedule.xlsx

    python app/solve.py                # build the schedule (asks to confirm first; add -y to skip the question)
    python app/solve.py --check        # validate the data and print warnings, don't solve
    python app/solve.py --pdf          # also write Schedule.pdf, a printable calendar (needs: pip install reportlab)
    python app/solve.py --compare-gaps 14 21 28 35   # try several min_days_between_shows values, write nothing
    python app/solve.py --stats        # stats + rule check for the Schedule.xlsx on disk (also after hand edits), no solving
    python app/solve.py --stats --pdf  # ...and rebuild Schedule.pdf from that edited Schedule.xlsx

Reads the two downloads directly (see inputs.py) and prints their warnings first: combos still Pending, conflict
form problems. Writes nothing but Schedule.xlsx (and Schedule.pdf).
Needs: pip install openpyxl ortools
"""
import argparse
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from statistics import median

from core import ScheduleError, generate_nights, run_schedule
from core.checks import analyze
from core.stats import schedule_stats
from inputs import APPROVALS_FILE, CONFLICTS_FILE, InputError, load_input, name_from_email
from store import Store
from util import DATA_FOLDER
from outputs.excel_schedule import (ScheduleFileError, archive_semester, check_semester, read_schedule,
                                    schedule_nights, schedule_semester, write_schedule)
from settings_file import SETTINGS_FILE, SettingsError, load_settings


def show(report, levels=("warn",)):
    for lvl, txt in report:
        if lvl in levels:
            print(f"  [{lvl.upper()}] {txt}")


def compare_gaps(inp, settings, values):
    """Solve once per min_days_between_shows value and print how far apart each combo's shows end up."""
    print(f"\n{'ideal gap':>9} | {'closest':>7} | {'median':>6} | {'< 14 days':>9} | sets filled | solver")
    for v in values:
        result = run_schedule(inp, replace(settings, min_days_between_shows=v))
        shows = defaultdict(list)
        for d, cs in result.lineup.items():
            for c in cs:
                shows[c].append(d)
        gaps = [(b - a).days for ds in shows.values() for a, b in zip(sorted(ds), sorted(ds)[1:])]
        filled = result.stats["total_sets"] - result.stats["empty_sets"]
        if gaps:
            print(f"{v:>7} d | {min(gaps):>5} d | {median(gaps):>4.0f} d | {sum(g < 14 for g in gaps):>9} | "
                  f"{filled:>5}/{result.stats['total_sets']:<5} | {result.stats['status']}")
        else:
            print(f"{v:>7} d | no combo has two shows | {filled}/{result.stats['total_sets']} | {result.stats['status']}")
    print("\nPick the smallest value where 'closest' stops improving and the solver still says OPTIMAL.\n"
          "Then set it in the app's Settings tab (min_days_between_shows) and run solve.py.")


def print_stats(path, inp, settings, names, pdf=None):
    combos = {c.id: c for c in inp.combos}
    sets, file_problems, supervised, typed = read_schedule(path, combos)
    nights = schedule_nights(path, settings)          # the schedule's own nights, whatever the settings say now
    sections, problems = schedule_stats(sets, nights, combos, inp, settings, supervised,
                                        lambda e: names.get(e) or name_from_email(e), typed)
    print(f"\nStats for {path}")
    for title, lines in sections:
        print(f"\n{title}")
        for line in lines:
            print(f"  {line}")
    problems = file_problems + problems
    print("\nRule check")
    if problems:
        for p in problems:
            print(f"  [PROBLEM] {p}")
    else:
        print("  All hard rules hold (no conflicts played, venue minimums met, no combo twice in a night, "
              "every combo on a supervised night).")
    if pdf:
        try:
            from outputs.schedule_pdf import write_schedule_pdf
        except ImportError:
            print("Can't write the PDF: run  pip install reportlab")
            return 1
        entries = {d: {k: ("combo", c) for k, c in row.items() if c is not None} for d, row in sets.items()}
        for d, row in typed.items():
            for k, t in row.items():
                entries.setdefault(d, {})[k] = ("text", t)
        write_schedule_pdf(pdf, nights, entries, combos, supervised or set(), settings)
        print(f"\nWrote {pdf} from {path}" + (" (the rule check found problems: see above)" if problems else "") + ".")
    return 1 if problems else 0


def confirm(outputs):
    """Ask before building a schedule. Warns about each existing output file that would be overwritten."""
    existing = [p for p in outputs if p.exists()]
    print("\nThis builds a NEW schedule from scratch.")
    for p in existing:
        when = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  WARNING: {p} already exists (last saved {when}) and will be overwritten.")
    if existing:
        print("  Any swaps recorded in the old schedule will be lost. To keep it, rename or copy it first.\n"
              "  To just check the existing schedule, use: python app/solve.py --stats")
    if not sys.stdin.isatty():
        print("Not running interactively: add -y to confirm.")
        return False
    try:
        return input("Continue? [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", default=str(DATA_FOLDER))
    ap.add_argument("--settings", default=SETTINGS_FILE)
    ap.add_argument("--approvals", default=APPROVALS_FILE)
    ap.add_argument("--conflicts", default=CONFLICTS_FILE)
    ap.add_argument("--conflicts-sheet")
    ap.add_argument("--out", default="Schedule.xlsx")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--stats", action="store_true",
                    help="stats and a rule check for the existing Schedule.xlsx (works after hand edits); no solving")
    ap.add_argument("--compare-gaps", nargs="+", type=int, metavar="DAYS",
                    help="try these min_days_between_shows values and print a comparison; writes nothing")
    ap.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation before building the schedule")
    ap.add_argument("--pdf", nargs="?", const="Schedule.pdf", help="also write a printable calendar (default Schedule.pdf)")
    a = ap.parse_args(argv)
    f = Path(a.folder)
    try:
        settings, setting_warnings = load_settings(f / a.settings)
        if a.stats:
            check_semester(f / a.out, settings)          # another semester's schedule isn't this one's
        # --stats looks at the schedule as it is: its own nights; anything else plans from the settings
        nights = schedule_nights(f / a.out, settings) if a.stats and (f / a.out).exists() else generate_nights(settings)
        days, sets = Counter(n.weekday for n in nights), Counter()
        for n in nights:
            sets[n.weekday] += n.n_slots
        detail = ", ".join(f"{c} {d}{'' if c == 1 else 's'} = {sets[d]} sets" for d, c in days.items())
        print(f"\n{settings.semester_name}: {len(nights)} show nights, {sum(sets.values())} sets ({detail})")
        for w in setting_warnings:
            print(f"  [WARN] {w}")
        inp = load_input(f, settings, a.approvals, a.conflicts, conflicts_sheet=a.conflicts_sheet)
        print(f"{len(inp.combos)} combos, {len(inp.blocked)} students with conflicts")
        warnings = [t for lvl, t in inp.notes if lvl in ("pending", "warn")]
        for txt in warnings:
            print(f"\n  WARNING: {txt}")
        if a.check:
            _, report = analyze(inp, settings, nights)
            print("\nInput report:")
            show([(lvl, t) for lvl, t in inp.notes if lvl == "info"] + report, levels=("warn", "info"))
            return 0
        inp = replace(inp, notes=[("warn", t) for t in warnings])      # also saved in the Report sheet
        if a.stats:
            return print_stats(f / a.out, inp, settings, Store(f).names, f / a.pdf if a.pdf else None)
        if a.compare_gaps:
            compare_gaps(inp, settings, a.compare_gaps)
            return 0
        if (f / a.out).exists() and schedule_semester(f / a.out, settings) != settings.semester_name:
            old = schedule_semester(f / a.out)          # recorded in the file, or unknown
            moved = archive_semester(f, old or "Old schedule")
            print(f"\n{a.out} was for {old or 'another semester'}: moved its files to {moved}.")
        outputs = [f / a.out] + ([f / a.pdf] if a.pdf else [])
        if not a.yes and not confirm(outputs):
            print("Cancelled. Nothing was changed.")
            return 1
        print(f"\nMaking the schedule: the solver is working (up to about {settings.solver_time_limit_sec:g} seconds; "
              "it stops early when it has the best schedule)...", flush=True)
        result = run_schedule(inp, settings)
    except (SettingsError, InputError, ScheduleError, ScheduleFileError) as e:
        print(f"\nCan't continue:\n{e}")
        return 1
    write_schedule(f / a.out, result, settings)
    print(f"\nSolver: {result.stats['status']}. {result.stats['total_sets'] - result.stats['empty_sets']}"
          f"/{result.stats['total_sets']} sets filled.")
    show(result.report)
    print(f"\nWrote {f / a.out}. For details: python app/solve.py --stats")
    if a.pdf:
        try:
            from outputs.schedule_pdf import entries_from_result, write_schedule_pdf
        except ImportError:
            print("Can't write the PDF: run  pip install reportlab")
            return 1
        write_schedule_pdf(f / a.pdf, result.nights, entries_from_result(result), result.combos, result.supervised,
                           settings)
        print(f"Wrote {f / a.pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
