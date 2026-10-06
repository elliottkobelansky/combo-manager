"""settings.json + Approvals.xlsx + Conflicts.xlsx -> the schedule (App data/schedule.json, see schedule_file.py)

    python app/solve.py                  # build a new schedule (asks to confirm first; add -y to skip the question)
    python app/solve.py --export         # ...and write Schedule.pdf and Schedule.xlsx from it (--pdf: the same)
    python app/solve.py --check          # validate the data and print warnings, don't solve
    python app/solve.py --compare-gaps 14 21 28 35   # try several min_days_between_shows values, write nothing
    python app/solve.py --stats          # stats + rule check for the schedule as it is (after swaps), no solving
    python app/solve.py --stats --export # ...and rebuild Schedule.pdf and Schedule.xlsx from it

Works on the data folder picked in the app on this computer; --folder FOLDER for another one.
Reads the two downloads directly (see inputs.py) and prints their warnings first: combos still Pending, conflict
form problems. Writes nothing but the schedule (and its exports).
Needs: pip install openpyxl ortools (reportlab for the PDF)
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
from inputs import InputError, load_input, name_from_email
from store import Store
from app_config import saved_folder
from data_folder import SCHEDULE_PDF, SCHEDULE_XLSX, problem, schedule_path, settings_path, usual_inputs
from schedule_file import (ScheduleFileError, archive_semester, check_semester, entries, has_schedule, load,
                           save_new, semester_of)
from settings_file import SettingsError, load_settings


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


def write_exports(folder, sched, combos, settings, store):
    """Schedule.pdf and Schedule.xlsx from the schedule. One open in another program is skipped, with a warning:
    the schedule itself is saved either way."""
    def name_of(e):
        return store.names.get(e) or name_from_email(e)
    try:
        from outputs.schedule_pdf import write_schedule_pdf
        write_schedule_pdf(folder / SCHEDULE_PDF, sched.nights, entries(sched), combos, sched.supervised or set(),
                           settings)
        print(f"Wrote {folder / SCHEDULE_PDF}")
    except ImportError:
        print("Can't write the PDF: run  pip install reportlab")
    except PermissionError:
        print(f"  [WARN] {SCHEDULE_PDF} is open in another program, so it wasn't updated (the schedule itself is "
              "saved). Close it, then Export again (Schedule tab).")
    from outputs.excel_schedule import write_schedule_xlsx
    try:
        write_schedule_xlsx(folder / SCHEDULE_XLSX, sched, combos, settings, name_of,
                            store.instruments(settings.semester_name))
        print(f"Wrote {folder / SCHEDULE_XLSX}")
    except PermissionError:
        print(f"  [WARN] {SCHEDULE_XLSX} is open in Excel, so it wasn't updated (the schedule itself is saved). "
              "Close it, then Export again (Schedule tab).")


def print_stats(folder, sched, inp, settings, store, export=False):
    combos = {c.id: c for c in inp.combos}
    sections, problems = schedule_stats(sched.sets, sched.nights, combos, inp, settings, sched.supervised,
                                        lambda e: store.names.get(e) or name_from_email(e), sched.typed)
    if sched.converted:
        print(f"\nThe old Schedule.xlsx was turned into {schedule_path(folder)} (the schedule is kept there now; the "
              "old file is in App data/Schedule backups).")
    print(f"\nStats for the {sched.semester} schedule in {folder}")
    for title, lines in sections:
        print(f"\n{title}")
        for line in lines:
            print(f"  {line}")
    problems = sched.problems + problems
    print("\nRule check")
    if problems:
        for p in problems:
            print(f"  [PROBLEM] {p}")
    else:
        print("  All hard rules hold (no conflicts played, venue minimums met, no combo twice in a night, "
              "every combo on a supervised night).")
    if export:
        print()
        write_exports(folder, sched, combos, settings, store)
    return 1 if problems else 0


def confirm(folder):
    """Ask before building a schedule. Warns when one exists already (it's backed up, but swaps made in it are
    gone from the new one)."""
    print("\nThis builds a NEW schedule from scratch.")
    if schedule_path(folder).exists():
        when = datetime.fromtimestamp(schedule_path(folder).stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  WARNING: there is a schedule already (last saved {when}); it will be replaced (a copy goes to "
              "App data/Schedule backups).\n  Any swaps made in it won't be in the new one.\n"
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
    ap.add_argument("--folder", help="the data folder (default: the one picked in the app on this computer)")
    ap.add_argument("--settings", help="default: App data/settings.json in the folder")
    ap.add_argument("--approvals", help="default: Approvals.xlsx in the folder")
    ap.add_argument("--conflicts", help="default: Conflicts.xlsx in the folder")
    ap.add_argument("--conflicts-sheet")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--stats", action="store_true",
                    help="stats and a rule check for the schedule as it is (after swaps); no solving")
    ap.add_argument("--compare-gaps", nargs="+", type=int, metavar="DAYS",
                    help="try these min_days_between_shows values and print a comparison; writes nothing")
    ap.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation before building the schedule")
    ap.add_argument("--export", "--pdf", action="store_true", dest="export",
                    help="also write Schedule.pdf and Schedule.xlsx from the schedule")
    a = ap.parse_args(argv)
    f = Path(a.folder) if a.folder else saved_folder()
    if problem(f):
        print(f"Can't use the data folder{' ' + str(f) if f else ''}: {problem(f)}. Pick one in the app, or add --folder FOLDER.")
        return 1
    try:
        settings, setting_warnings = load_settings(f / a.settings if a.settings else settings_path(f))
        if a.stats:
            check_semester(f, settings)               # another semester's schedule isn't this one's
        inp = load_input(f, settings, a.approvals or usual_inputs(f)["approvals"],
                         a.conflicts or usual_inputs(f)["conflicts"], conflicts_sheet=a.conflicts_sheet)
        combos = {c.id: c for c in inp.combos}
        # --stats looks at the schedule as it is: its own nights; anything else plans from the settings
        sched = load(f, combos, settings) if a.stats else None
        nights = sched.nights if sched else generate_nights(settings)
        days, sets = Counter(n.weekday for n in nights), Counter()
        for n in nights:
            sets[n.weekday] += n.n_slots
        detail = ", ".join(f"{c} {d}{'' if c == 1 else 's'} = {sets[d]} sets" for d, c in days.items())
        print(f"\n{settings.semester_name}: {len(nights)} show nights, {sum(sets.values())} sets ({detail})")
        for w in setting_warnings:
            print(f"  [WARN] {w}")
        print(f"{len(inp.combos)} combos, {len(inp.blocked)} students with conflicts")
        warnings = [t for lvl, t in inp.notes if lvl in ("pending", "warn")]
        for txt in warnings:
            print(f"\n  WARNING: {txt}")
        if a.check:
            _, report = analyze(inp, settings, nights)
            print("\nInput report:")
            show([(lvl, t) for lvl, t in inp.notes if lvl == "info"] + report, levels=("warn", "info"))
            return 0
        inp = replace(inp, notes=[("warn", t) for t in warnings])      # also saved in the schedule's report
        if a.stats:
            return print_stats(f, sched, inp, settings, Store(f), a.export)
        if a.compare_gaps:
            compare_gaps(inp, settings, a.compare_gaps)
            return 0
        if has_schedule(f) and semester_of(f, settings) != settings.semester_name:
            old = semester_of(f)                      # recorded in it, or unknown
            moved = archive_semester(f, old or "Old schedule")
            print(f"\nThe schedule was for {old or 'another semester'}: moved its files to {moved}.")
        if not a.yes and not confirm(f):
            print("Cancelled. Nothing was changed.")
            return 1
        print(f"\nMaking the schedule: the solver is working (up to about {settings.solver_time_limit_sec:g} seconds; "
              "it stops early when it has the best schedule)...", flush=True)
        result = run_schedule(inp, settings)
        save_new(f, result, settings)
        sched = load(f, combos, settings)
    except (SettingsError, InputError, ScheduleError, ScheduleFileError) as e:
        print(f"\nCan't continue:\n{e}")
        return 1
    print(f"\nSolver: {result.stats['status']}. {result.stats['total_sets'] - result.stats['empty_sets']}"
          f"/{result.stats['total_sets']} sets filled.")
    show(result.report)
    print(f"\nSaved the schedule ({schedule_path(f)}). For details: python app/solve.py --stats")
    if a.export:
        write_exports(f, sched, combos, settings, Store(f))
    return 0


if __name__ == "__main__":
    sys.exit(main())
