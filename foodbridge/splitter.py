"""AI split planner: decides how ONE big donation is shared across SEVERAL receivers.

It's a small optimisation model solved with Google OR-Tools CP-SAT (open source).
If OR-Tools isn't installed, a greedy planner gives a reasonable answer instead,
so the demo never breaks.

What the model decides, for each eligible receiver r:
    x[r] = how many portions r gets          (0 .. room left at r)
    y[r] = 1 if r gets anything (= one volunteer trip)

Hard rules (constraints):
    * total given out  <= portions still open
    * if r is used, it gets at least MIN_SHARE portions (or all its room, if smaller),
      so we never send a volunteer 15 km for 2 plates
    * at most MAX_SPLITS receivers per donation (each one costs a volunteer trip)
    Veg / non-veg, distance and "can we get there before it spoils" are checked in
    app.py before a receiver even becomes a candidate.

What it tries to do (objective, in order of importance):
    1. get as many portions eaten as possible
    2. favour receivers who haven't had food today (fairness)
    3. use fewer, closer trips
"""
from dataclasses import dataclass

MIN_SHARE = 5
MAX_SPLITS = 4
MAX_CANDIDATES = 15          # keep the model tiny so it solves in milliseconds


@dataclass
class Candidate:
    id: int
    name: str
    distance_km: float
    room: int           # portions this receiver can still take right now
    need: float         # 0..1, 1 = no food received today
    got_today: int = 0


def portion_value(c):
    """Score for each portion that goes to c. Always big, so feeding people comes first."""
    return 1000 + int(200 * c.need) - int(10 * c.distance_km)


def trip_cost(c):
    """Penalty for using c at all (one more volunteer trip). Smaller than any useful share."""
    return 300 + int(20 * c.distance_km)


def plan_split(remaining, candidates):
    """Return (shares, method). shares is a list of (Candidate, portions), biggest first."""
    cands = [c for c in candidates if c.room > 0]
    if remaining <= 0 or not cands:
        return [], "none"
    cands = sorted(cands, key=lambda c: c.distance_km)[:MAX_CANDIDATES]
    try:
        shares, method = _cpsat(remaining, cands), "OR-Tools CP-SAT"
    except ImportError:
        shares, method = _greedy(remaining, cands), "greedy fallback"
    shares.sort(key=lambda s: (-s[1], s[0].distance_km))
    return shares, method


def _cpsat(remaining, cands):
    from ortools.sat.python import cp_model

    m = cp_model.CpModel()
    x, y = {}, {}
    for c in cands:
        ub = min(c.room, remaining)
        lb = min(MIN_SHARE, ub)
        x[c.id] = m.NewIntVar(0, ub, f"x_{c.id}")
        y[c.id] = m.NewBoolVar(f"y_{c.id}")
        m.Add(x[c.id] <= ub * y[c.id])
        m.Add(x[c.id] >= lb * y[c.id])
    m.Add(sum(x.values()) <= remaining)
    m.Add(sum(y.values()) <= MAX_SPLITS)
    m.Maximize(sum(portion_value(c) * x[c.id] - trip_cost(c) * y[c.id] for c in cands))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 2.0
    solver.parameters.num_workers = 1        # deterministic: same input -> same plan
    status = solver.Solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return []
    return [(c, solver.Value(x[c.id])) for c in cands if solver.Value(x[c.id]) > 0]


def _greedy(remaining, cands):
    shares = []
    for c in sorted(cands, key=portion_value, reverse=True):
        if remaining <= 0 or len(shares) >= MAX_SPLITS:
            break
        give = min(c.room, remaining)
        shares.append((c, give))
        remaining -= give
    return shares
