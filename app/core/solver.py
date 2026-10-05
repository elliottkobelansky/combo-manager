"""Optimisation. Stage 1: combos -> nights (CP-SAT). Stage 2: order the sets within each night."""
from collections import defaultdict
from typing import Dict, List

from ortools.sat.python import cp_model

from .model import Night, Settings

# Soft-goal weights (bigger = more important), in priority order. Hard-coded on purpose; tune here if needed.
W_UNFILLED = 1000   # per empty set. In open mode this means: every combo gets its shows
W_FIRST_YEAR = 800  # per show a first-year combo plays before first_year_earliest_date (only if there's no other way)
W_SPREAD = 600      # per unit of (max - min) shows per combo, per venue and overall: equal show counts
W_SUP_DAY = 400     # per supervised night that isn't on a "Supervision preferred" show day (ShowDays sheet)
W_SHARED = 200      # per student who plays twice in one night (two of their combos on the same night)
W_SPACING = 80      # max cost of one pair of a combo's shows (same-day). The cost falls off quadratically and
                    # reaches 0 at min_days_between_shows.
W_VENUES = 150     # per combo with no show at a venue it could play at: 1 Upstairs + 1 Clara beats Upstairs twice
W_SUPERVISED = 100  # per supervised night: as few nights needing a professor as possible (within the cap)
W_PRIMARY = 15      # auto mode: extras should go to required venues (e.g. Tuesday) before optional ones


def pair_cost(gap_days, ideal_days):
    """3 days apart costs much more than 14; at ideal_days or beyond it costs nothing."""
    return round(W_SPACING * ((ideal_days - gap_days) / ideal_days) ** 2)


def venue_minimums(settings: Settings) -> Dict[str, int]:
    out = {}
    for sd in settings.show_days:
        out[sd.venue] = max(out.get(sd.venue, 0), sd.min_per_combo)
    return out


def precheck(combos, allowed, nights, show_min) -> List[str]:
    """Plain-language explanations for the most common reasons no schedule can exist."""
    problems = []
    by_venue = defaultdict(list)
    for n in nights:
        by_venue[n.venue].append(n)
    for venue, vn in by_venue.items():
        need = show_min.get(venue, 0)
        sets = sum(n.n_slots for n in vn)
        if need and len(combos) * need > sets:
            problems.append(f"{venue}: {len(combos)} combos x {need} required show(s) is more than the {sets} sets available.")
        for c in combos.values():
            usable = sum(1 for n in vn if n.date in allowed[c.id])
            if usable < need:
                problems.append(f"{c.name} has {usable} usable {venue} night(s) but needs {need}.")
    return problems


def precheck_total(combos, allowed, settings: Settings) -> List[str]:
    """A combo whose members' conflicts leave fewer usable nights than min_shows_per_combo."""
    need = settings.min_shows_per_combo
    if not need:
        return []
    return [f"{c.name} has {len(allowed[c.id])} usable night(s) in total but needs {need} (min_shows_per_combo)."
            for c in combos.values() if len(allowed[c.id]) < need]


def precheck_supervision(combos, nights, settings: Settings) -> List[str]:
    """Too few supervised nights allowed to fit every combo (each night holds at most its number of sets)."""
    cap = settings.max_supervised_nights
    if not settings.every_combo_supervised or not cap:
        return []
    room = sum(sorted((n.n_slots for n in nights), reverse=True)[:cap])
    if room < len(combos):
        return [f"max_supervised_nights is {cap}, but {cap} nights hold at most {room} combos and there are "
                f"{len(combos)}. Raise max_supervised_nights (or set every_combo_supervised to No)."]
    return []


def policy_open(settings: Settings) -> bool:
    return settings.extra_slot_policy == "open"


def solve_combos(combos, allowed, nights, show_min, settings: Settings):
    model = cp_model.CpModel()
    cids = sorted(combos)
    nmap = {n.date: n for n in nights}

    p = {}
    for c in cids:
        for n in nights:
            if n.date in allowed[c]:
                p[c, n.date] = model.NewBoolVar(f"p_{c}_{n.date.isoformat()}")
    by_night, by_combo, by_cv = defaultdict(list), defaultdict(list), defaultdict(list)
    for (c, d), var in p.items():
        by_night[d].append(var)
        by_combo[c].append(var)
        by_cv[c, nmap[d].venue].append(var)

    # at most n_slots combos per night; count empty sets
    unfilled = []
    for n in nights:
        vs = by_night[n.date]
        if vs:
            model.Add(sum(vs) <= n.n_slots)
        unfilled.append(n.n_slots - sum(vs))

    cap = settings.max_shows_per_combo
    min_total = settings.min_shows_per_combo
    for c in cids:
        if cap and by_combo[c]:
            model.Add(sum(by_combo[c]) <= cap)
        if min_total:
            model.Add(sum(by_combo[c]) >= min_total)
        if min_total and (policy_open(settings) or combos[c].first_year):
            # open mode: exactly the minimum (at least the venue minimums); extras stay open for volunteers.
            # Fill-every-set mode: first-year combos still get no extras.
            model.Add(sum(by_combo[c]) <= max(min_total, sum(show_min.values())))

    venues = sorted({n.venue for n in nights})
    spread = []
    for v in venues:
        hi, lo = model.NewIntVar(0, 100, f"hi_{v}"), model.NewIntVar(0, 100, f"lo_{v}")
        for c in cids:
            vs = by_cv[c, v]
            cnt = sum(vs)
            if show_min.get(v, 0) and vs:
                model.Add(cnt >= show_min[v])
            model.Add(hi >= cnt)
            model.Add(lo <= cnt)
        spread.append(hi - lo)

    t_hi, t_lo = model.NewIntVar(0, 200, "t_hi"), model.NewIntVar(0, 200, "t_lo")
    for c in cids:
        model.Add(t_hi >= sum(by_combo[c]))
        model.Add(t_lo <= sum(by_combo[c]))
    spread.append(t_hi - t_lo)

    # every combo plays at each venue it can (soft, so a combo that can't make any Clara night plays Upstairs twice)
    no_show_at = []
    if len(venues) > 1:
        for c in cids:
            for v in venues:
                if by_cv[c, v]:
                    m = model.NewBoolVar(f"nov_{c}_{v}")
                    model.Add(sum(by_cv[c, v]) + m >= 1)
                    no_show_at.append(m)

    primary_v = [v for v in venues if show_min.get(v, 0) > 0]
    secondary_v = [v for v in venues if show_min.get(v, 0) == 0]
    primary_terms = []
    if primary_v and secondary_v:
        for c in cids:
            e = model.NewIntVar(0, 100, f"e_{c}")
            model.Add(e >= sum(sum(by_cv[c, v]) for v in secondary_v) - sum(sum(by_cv[c, v]) for v in primary_v))
            primary_terms.append(e)

    # supervision: the solver picks nights a professor attends; every combo plays at least one of them
    sup = {}
    if settings.every_combo_supervised:
        for n in nights:
            sup[n.date] = model.NewBoolVar(f"sup_{n.date.isoformat()}")
            # a professor never comes for a night with open sets: a supervised night is full
            model.Add(sum(by_night[n.date]) == n.n_slots).OnlyEnforceIf(sup[n.date])
        for c in cids:
            covered = []
            for (cc, d), var in p.items():
                if cc == c:
                    z = model.NewBoolVar(f"z_{c}_{d.isoformat()}")
                    model.Add(z <= var)
                    model.Add(z <= sup[d])
                    covered.append(z)
            model.Add(sum(covered) >= 1)
        if settings.max_supervised_nights:
            model.Add(sum(sup.values()) <= settings.max_supervised_nights)
        # Not a new rule, just a fact that helps the solver prove it's done: the fullest nights still hold only so
        # many combos, so at least this many supervised nights are needed.
        need, room = 0, 0
        for k in sorted((n.n_slots for n in nights), reverse=True):
            if room >= len(cids):
                break
            need, room = need + 1, room + k
        model.Add(sum(sup.values()) >= need)

    # first-year combos avoid nights before the cutoff
    early = []
    cutoff = settings.first_year_earliest_date
    if cutoff:
        early = [(var, d, c) for (c, d), var in p.items() if combos[c].first_year and d < cutoff]

    # combos sharing a member avoid playing the same night (cost per shared student)
    shared, shared_cost = [], []
    for i, a in enumerate(cids):
        for b in cids[i + 1:]:
            both = combos[a].members & combos[b].members
            if both:
                for n in nights:
                    if (a, n.date) in p and (b, n.date) in p:
                        y = model.NewBoolVar(f"y_{a}_{b}_{n.date.isoformat()}")
                        model.Add(y >= p[a, n.date] + p[b, n.date] - 1)
                        shared.append((y, n.date, a, b))
                        shared_cost.append(W_SHARED * len(both))

    # spacing between one combo's shows: closer pairs cost more, so shows are spread as far apart as possible
    spacing, spacing_cost = [], []
    md = settings.min_days_between_shows
    if md:
        for c in cids:
            for i, n1 in enumerate(nights):
                for n2 in nights[i + 1:]:
                    if (n2.date - n1.date).days >= md:
                        break
                    if (c, n1.date) in p and (c, n2.date) in p:
                        q = model.NewBoolVar(f"q_{c}_{n1.date.isoformat()}_{n2.date.isoformat()}")
                        model.Add(q >= p[c, n1.date] + p[c, n2.date] - 1)
                        spacing.append(q)
                        spacing_cost.append(pair_cost((n2.date - n1.date).days, md))

    model.Minimize(W_UNFILLED * sum(unfilled) + W_SPREAD * sum(spread)
                   + W_PRIMARY * sum(primary_terms) + W_VENUES * sum(no_show_at)
                   + sum(w * q for w, q in zip(spacing_cost, spacing))
                   + sum(w * y for w, (y, *_) in zip(shared_cost, shared))
                   + W_FIRST_YEAR * sum(var for var, *_ in early)
                   + W_SUPERVISED * sum(sup.values())
                   + W_SUP_DAY * sum(var for d, var in sup.items() if not nmap[d].supervision_preferred
                                     and any(n.supervision_preferred for n in nights)))
    solver = cp_model.CpSolver()
    # Same input -> same output: interleaved search is deterministic, and the limit is measured in
    # deterministic work units (roughly seconds) rather than wall-clock time, which varies run to run.
    solver.parameters.max_deterministic_time = float(settings.solver_time_limit_sec)
    solver.parameters.num_workers = 8
    solver.parameters.interleave_search = True
    solver.parameters.random_seed = 1
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, solver.StatusName(status)

    chosen = defaultdict(list)
    for (c, d), var in p.items():
        if solver.Value(var):
            chosen[d].append(c)
    stats = dict(status=solver.StatusName(status), objective=solver.ObjectiveValue(),
                 bound=solver.BestObjectiveBound(), spacing_violations=sum(solver.Value(q) for q in spacing),
                 shared_nights=[(d, a, b) for y, d, a, b in shared if solver.Value(y)],
                 early_first_year=[(d, c) for var, d, c in early if solver.Value(var)],
                 supervised={d for d, var in sup.items() if solver.Value(var)})
    return chosen, stats


def order_sets(chosen, nights: List[Night], combos):
    """Within a night, combos that tended to go late so far go earlier tonight (and vice versa).
    Two combos sharing a member play back-to-back, so that student only has one stretch on stage."""
    pos_sum, pos_n = defaultdict(float), defaultdict(int)
    lineup = {}
    for n in nights:
        cs = chosen.get(n.date, [])

        def lateness(c):
            return pos_sum[c] / pos_n[c] if pos_n[c] else 0.5
        todo, ordered = sorted(cs, key=lambda c: (-lateness(c), c)), []
        while todo:
            prev = combos[ordered[-1]].members if ordered else frozenset()
            nxt = next((c for c in todo if combos[c].members & prev), todo[0])
            todo.remove(nxt)
            ordered.append(nxt)
        lineup[n.date] = ordered
        for k, c in enumerate(ordered):
            pos_sum[c] += k / (n.n_slots - 1) if n.n_slots > 1 else 0.5
            pos_n[c] += 1
    return lineup


def open_set_options(lineup, nights, combos, allowed):
    """For each empty set: combos that could take it. '*' = shares a member with a combo already playing."""
    shows = defaultdict(int)
    for cs in lineup.values():
        for c in cs:
            shows[c] += 1
    rows = []
    for n in nights:
        playing = lineup.get(n.date, [])
        for k in range(len(playing) + 1, n.n_slots + 1):
            elig = []
            for cid, c in sorted(combos.items(), key=lambda kv: kv[1].name):
                if cid in playing or n.date not in allowed[cid]:
                    continue
                tag = ", 1st yr" if c.first_year else ""
                if any(combos[o].members & c.members for o in playing):
                    tag += ", *"
                elig.append(f"{c.name} ({shows[cid]}{tag})")
            rows.append((n, k, elig))
    return rows
