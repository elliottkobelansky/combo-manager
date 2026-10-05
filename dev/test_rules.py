"""Runs fake downloads -> inputs -> solve on fake data and checks every hard rule independently of the solver.

    python dev/test_rules.py
"""
import sys
import tempfile
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))  # the scheduler's code

from core import ScheduleError, generate_nights, run_schedule
from make_fake_forms import OUTSIDE, fake_emails, make
from openpyxl import load_workbook

from inputs import load_input
from settings_file import DEFAULTS, validate


def check(result, inp, settings):
    bad, nights, combos = [], {n.date: n for n in result.nights}, result.combos
    show_min = defaultdict(int)
    for sd in settings.show_days:
        show_min[sd.venue] = max(show_min[sd.venue], sd.min_per_combo)
    cnt = defaultdict(lambda: defaultdict(int))
    for d, cs in result.lineup.items():
        n = nights[d]
        if len(cs) > n.n_slots:
            bad.append(f"{d}: more combos than sets")
        if len(cs) != len(set(cs)):
            bad.append(f"{d}: a combo plays twice in one night")
        for c in cs:
            cnt[c][n.venue] += 1
            for m in combos[c].members:
                if d in inp.blocked.get(m, ()):
                    bad.append(f"{combos[c].name} plays {d} but {m} is blocked")
    for c in combos:
        for v, m in show_min.items():
            if cnt[c][v] < m:
                bad.append(f"{combos[c].name} has {cnt[c][v]} {v} show(s), needs {m}")
        if settings.max_shows_per_combo and sum(cnt[c].values()) > settings.max_shows_per_combo:
            bad.append(f"{combos[c].name} exceeds the show cap")
        total, need = sum(cnt[c].values()), settings.min_shows_per_combo
        if need and total < need:
            bad.append(f"{combos[c].name} has {total} shows, needs {need}")
        if need and settings.extra_slot_policy == "open":
            if total > max(need, sum(show_min.values())):
                bad.append(f"{combos[c].name} got extra shows it shouldn't (open mode: exactly {need})")
        elif combos[c].first_year or settings.extra_slot_policy == "open":
            if any(x > max(settings.core_shows_per_venue, 1) for x in cnt[c].values()):
                bad.append(f"{combos[c].name} got extra shows it shouldn't")
    if settings.every_combo_supervised:
        for c in combos:
            if not any(c in cs for d, cs in result.lineup.items() if d in result.supervised):
                bad.append(f"{combos[c].name} plays no supervised night")
        for d in result.supervised:
            if len(result.lineup.get(d, [])) < nights[d].n_slots:
                bad.append(f"supervised night {d} has open sets")
        cap = settings.max_supervised_nights
        if cap and len(result.supervised) > cap:
            bad.append(f"{len(result.supervised)} supervised nights, cap is {cap}")
    return bad


def check_approvals(combos, approvals_path):
    """Only Accepted rows may be scheduled, and every combo must carry its Response Id."""
    ws = load_workbook(approvals_path)["Sheet1"]
    status = {str(r[0]): str(r[7] or "").strip().lower() for r in ws.iter_rows(min_row=2, values_only=True)}
    return [f"{c.name} (response {c.ref or '?'}) is scheduled but its Status is '{status.get(c.ref)}'"
            for c in combos if status.get(c.ref) != "accepted"]


def check_outside(inp):
    """Non-McGill (Gmail) members stay in their combo, and their conflicts count."""
    members = set().union(*[c.members for c in inp.combos])
    return ([f"{e} was dropped from their combo" for e in OUTSIDE if e not in members]
            + [f"{e}'s conflicts were lost" for e in OUTSIDE if e not in inp.blocked])


def check_parse(inp, expected):
    """inputs.py reads the approvals table into exactly the combos make_fake_forms put in, numbered 01, 02, ..."""
    got = [(c.ref, c.members, c.liaison, c.first_year) for c in sorted(inp.combos, key=lambda c: c.name)]
    bad = [] if got == expected else [f"approvals read wrongly: {len(got)} combos, expected {len(expected)}"
                                      + next((f"; first difference: got {g}, expected {e}"
                                              for g, e in zip(got, expected) if g != e), "")]
    names = sorted(c.name for c in inp.combos)
    if names != [f"Combo {k:02d}" for k in range(1, len(names) + 1)]:
        bad.append(f"combo numbers aren't 01..{len(names):02d}: {names[:3]}...")
    return bad


def check_status(inp):
    """Overruled conflicts don't count; 'ok' (a synonym for Active) does. See make_fake_forms.py."""
    overruled, ok = fake_emails(13)[11], fake_emails(13)[12]
    return ([] if overruled not in inp.blocked else ["an Overruled conflict was counted"]) + \
           ([] if inp.blocked.get(ok) else ["a conflict with Status 'ok' was dropped"])


def main():
    tmp = Path(tempfile.mkdtemp())
    base, _ = validate(DEFAULTS)
    base = replace(base, solver_time_limit_sec=10)
    nights = generate_nights(base)
    failures = 0
    for n_combos, policy in [(8, "auto"), (22, "auto"), (33, "auto"), (33, "open")]:
        s = replace(base, extra_slot_policy=policy)
        (tmp / "scheduler_data.json").unlink(missing_ok=True)          # combo numbers start fresh per scenario
        expected = make(tmp / "a.xlsx", tmp / "f.xlsx", nights, n_combos, seed=1, sem=s.semester_name)
        inp = load_input(tmp, s, "a.xlsx", "f.xlsx")
        result = run_schedule(inp, s)
        bad = check(result, inp, s) + check_parse(inp, expected) + check_approvals(inp.combos, tmp / "a.xlsx") + check_outside(inp) + check_status(inp)
        counts = sorted(sum(1 for cs in result.lineup.values() if c in cs) for c in result.combos)
        print(f"{'PASS' if not bad else 'FAIL'}  {len(result.combos):>2} combos, {policy:<4} | "
              f"{result.stats['total_sets'] - result.stats['empty_sets']}/{result.stats['total_sets']} sets filled | "
              f"shows per combo {counts[0]}-{counts[-1]} | "
              f"soft rules broken: {len(result.stats['shared_nights'])} student double-night(s), "
              f"{len(result.stats['early_first_year'])} early first-year show(s) | "
              f"{len(result.supervised)} supervised nights")
        for b in bad[:5]:
            print("      -", b)
        failures += bool(bad)
    # A combo that can't make any Clara night gets Upstairs twice instead (min_shows_per_combo), never Clara twice.
    s = replace(base, extra_slot_policy="open")
    who = inp.combos[0]
    clara = {n.date for n in nights if n.venue == "Clara"}
    blocked = dict(inp.blocked)
    blocked[sorted(who.members)[0]] = set(blocked.get(sorted(who.members)[0], set())) | clara
    result = run_schedule(replace(inp, blocked=blocked), s)
    mine = [n.venue for n in nights if who.id in result.lineup.get(n.date, [])]
    ok = sorted(mine) == ["Upstairs", "Upstairs"] and not check(result, replace(inp, blocked=blocked), s)
    print(f"{'PASS' if ok else 'FAIL'}  combo with no usable Clara night plays Upstairs twice ({', '.join(mine)})")
    failures += not ok

    # Swap finder: every option it offers must pass this file's own rule check; it must find some.
    from core.swaps import apply_option, swap_options
    s = replace(base, extra_slot_policy="open")
    result = run_schedule(inp, s)
    sets = {d: {k: c for k, c in enumerate(cs, start=1)} for d, cs in result.lineup.items()}
    tried = offered = 0
    bad = []
    for c in sorted(result.combos)[:6]:
        for d, k in [(d, k) for d, row in sets.items() for k, x in row.items() if x == c][:1]:
            for opt in swap_options(sets, result.nights, result.combos, inp, s, result.supervised, {}, c, d, k):
                new = apply_option(sets, opt)
                lineup = {dd: [row[kk] for kk in sorted(row) if row[kk]] for dd, row in new.items()}
                bad += [f"{opt.title}: {b}" for b in check(replace(result, lineup=lineup), inp, s)]
                offered += 1
            tried += 1
    ok = not bad and offered > 0
    print(f"{'PASS' if ok else 'FAIL'}  swap finder: {offered} options for {tried} shows, all keep the hard rules")
    for b in bad[:5]:
        print("      -", b)
    failures += not ok

    # Giving a show away: only a combo with more than it needs can, and every give-away keeps the hard rules.
    s = replace(base, extra_slot_policy="auto")
    result = run_schedule(inp, s)
    sets = {d: {k: c for k, c in enumerate(cs, start=1)} for d, cs in result.lineup.items()}
    count = {c: sum(1 for row in sets.values() for x in row.values() if x == c) for c in result.combos}
    rich = [c for c in sorted(result.combos) if count[c] > (s.min_shows_per_combo or 0)][:3]
    poor = [c for c in sorted(result.combos) if count[c] <= (s.min_shows_per_combo or 0)][:3]
    gives, bad, wrong = 0, [], []
    for c in rich + poor:
        for d, k in [(d, k) for d, row in sets.items() for k, x in row.items() if x == c]:
            for opt in swap_options(sets, result.nights, result.combos, inp, s, result.supervised, {}, c, d, k):
                if opt.kind not in ("give", "drop"):
                    continue
                if c in poor:
                    wrong.append(f"{result.combos[c].name} has only {count[c]} shows but may give one away")
                new = apply_option(sets, opt)
                lineup = {dd: [row[kk] for kk in sorted(row) if row[kk]] for dd, row in new.items()}
                for b in check(replace(result, lineup=lineup), inp, s):
                    # a first-year combo getting an extra show is a soft rule after publishing: must be warned about
                    if not ("got extra shows" in b and any("first-year" in w for w in opt.warnings)):
                        bad.append(f"{opt.title}: {b}")
                gives += 1
    # Claiming an open set (volunteering): every claim keeps the hard rules (the extra show itself is the point).
    s = replace(base, extra_slot_policy="open")
    result = run_schedule(inp, s)
    sets = {d: {k: c for k, c in enumerate(cs, start=1)} for d, cs in result.lineup.items()}
    claims = 0
    for c in sorted(result.combos)[:4]:
        for opt in swap_options(sets, result.nights, result.combos, inp, s, result.supervised, {}, c):
            new = apply_option(sets, opt)
            lineup = {dd: [row[kk] for kk in sorted(row) if row[kk]] for dd, row in new.items()}
            bad += [f"{opt.title}: {b}" for b in check(replace(result, lineup=lineup), inp, s)
                    if "got extra shows" not in b]
            claims += 1
    ok = gives > 0 and claims > 0 and not bad and not wrong and rich and poor
    print(f"{'PASS' if ok else 'FAIL'}  give-aways: {gives} options from combos with extra shows, all legal; "
          f"none from combos at their minimum; {claims} open-set claims, all legal")
    for b in (bad + wrong)[:5]:
        print("      -", b)
    for b in bad[:5]:
        print("      -", b)
    failures += not ok

    # Combo numbers never change: withdraw one combo and add a new one; the others keep their numbers.
    from openpyxl import load_workbook
    (tmp / "scheduler_data.json").unlink(missing_ok=True)
    make(tmp / "a.xlsx", tmp / "f.xlsx", nights, 33, seed=1, sem=base.semester_name)
    before = {c.ref: c.name for c in load_input(tmp, base, "a.xlsx", "f.xlsx").combos}
    wb = load_workbook(tmp / "a.xlsx")
    ws = wb.worksheets[0]
    head = [c.value for c in ws[1]]
    first_ref = sorted(before, key=lambda r: before[r])[0]
    for row in ws.iter_rows(min_row=2):
        if str(row[head.index("Response Id")].value) == first_ref:
            row[head.index("Status")].value = "Withdrawn"
    ws.append([999, "x", base.semester_name, "new.person@mail.mcgill.ca", "new.person@mail.mcgill.ca\nother.one@mail.mcgill.ca",
               "prof@mcgill.ca", "No", "Accepted", None, None, None])
    ws.tables["Approvals"].ref = f"A1:K{ws.max_row}"
    wb.save(tmp / "a.xlsx")
    notes_inp = load_input(tmp, base, "a.xlsx", "f.xlsx")
    after = {c.ref: c.name for c in notes_inp.combos}
    moved = [r for r in after if r in before and after[r] != before[r]]
    gone_warned = any("No longer accepted" in t and before[first_ref] in t for _, t in notes_inp.notes)
    ok = (not moved and first_ref not in after and after.get("999") == f"Combo {len(before) + 1:02d}" and gone_warned)
    print(f"{'PASS' if ok else 'FAIL'}  combo numbers stay put: withdrawn {before[first_ref]} leaves a gap, the new "
          f"combo is {after.get('999')}")
    failures += not ok

    # Email fixes: a typo in the approvals hides that member's conflicts; fixing it in the store brings them back.
    from store import Store
    (tmp / "scheduler_data.json").unlink(missing_ok=True)
    make(tmp / "a.xlsx", tmp / "f.xlsx", nights, 33, seed=1, sem=base.semester_name)
    clean = load_input(tmp, base, "a.xlsx", "f.xlsx")
    who = next(e for e in sorted(clean.blocked) if any(e in c.members for c in clean.combos) and e.endswith("@mail.mcgill.ca"))
    typo = who.replace("@", "x@")
    wb = load_workbook(tmp / "a.xlsx")
    for row in wb.worksheets[0].iter_rows(min_row=2):
        for c in row:
            if isinstance(c.value, str) and who in c.value:
                c.value = c.value.replace(who, typo)
    wb.save(tmp / "a.xlsx")
    broken = load_input(tmp, base, "a.xlsx", "f.xlsx")
    st = Store(tmp)
    st.set_email(typo, who)
    st.save()
    fixed = load_input(tmp, base, "a.xlsx", "f.xlsx")
    members = lambda inp: {e for c in inp.combos for e in c.members}
    ok = (typo in members(broken) and who not in members(broken) and who in members(fixed)
          and typo not in members(fixed) and {c.name: c.members for c in fixed.combos} == {c.name: c.members for c in clean.combos})
    print(f"{'PASS' if ok else 'FAIL'}  email fix: a typo'd address in the approvals is corrected everywhere again")
    failures += not ok

    # A cap too small to fit every combo must stop with a clear message, not a vague solver failure.
    tight = replace(base, extra_slot_policy="open", max_supervised_nights=8)       # 8 nights x 4 sets < 33 combos
    try:
        run_schedule(inp, tight)
        print("FAIL  max_supervised_nights too small was accepted")
        failures += 1
    except ScheduleError as e:
        ok = "max_supervised_nights" in str(e)
        print(f"{'PASS' if ok else 'FAIL'}  too-small supervision cap is explained")
        failures += not ok
    print("\nAll good." if not failures else f"\n{failures} scenario(s) failed.")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
