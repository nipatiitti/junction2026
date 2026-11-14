"""The fee schedule of a single-car gig from a dynamic program (`feeTable` of the TypeScript `lean`).

    uv run --with numpy python -m analysis.lean_fee_table            # fit, solve, print (three minutes)
    uv run --with numpy python -m analysis.lean_fee_table --write    # and save src/strategies/lean/feetable.json

It reads the saved lean weeks from a database built by `tools.db` (`--db`, default `out/lean.sqlite`) and the fee
probes under `data/scrape/probe2` and `probe3`. It plays nothing. The model, in the order of the code:

1. **A gig has a threshold.** At the share u of its planning time, w waking minutes after its post, a gig that
   shows the fee f (x typical) has found its driver with the chance
   G = (1 - none(u)) x logistic((ln f - m(u) - pre(w)) / sigma). `none` is the share of gigs that no fee books yet
   (no driver who could take them has looked), m the fee that half of the others need, `pre` what it is higher by
   until the drivers have looked, and sigma how much gigs differ. A gig that is still open at a fee is a hard one:
   its chance to book in the next slice at f' is (G(u', f') - G(u, f)) / (1 - G(u, f)), which is small when G(u, f)
   was high. A fit of "the chance to book at fee f" without this reads the hard gigs that reach a high fee as
   "high fees do not help". One fit for each class of gig (`gig_class`), with a shift for a pickup on a Friday and
   one after the weekend. The probes give the shape: they are the only gigs that opened at other fees.
2. **Two readings.** Every saved gig raises at the same shares of its planning time, so the weeks cannot say
   whether a late booking came from the raise or from the hour. The moving reading lets m and `none` fall all the
   time; the still reading stops them four hours after the post, so every late booking is the raise's. The program
   plays against the mean of the two, and the guard below also holds in the still one.
3. **Drivers who wait.** The chance is measured at checkpoints, not minute by minute: at the end of each fee and at
   the knots. A driver who looked at a lower fee and comes back is then a buyer who takes the gig at the first fee
   over their threshold, and the 15 to 60 minutes they take to come back do not count against the fee. (A hazard
   for each first look was tried and did not fit: 27% of the bookers had looked 45 minutes or more before at the
   same fee, and 25% at a lower one.) With thresholds alone a slow climb from a low fee is the best schedule,
   because every gig then pays just its threshold. That is the trap: the climb teaches drivers to wait. So a
   booking at f on a gig that opened at f0 costs `wait` x (f / f0 - 1) x typical more (drivers learn the booked fee
   over the first fee they saw), each raise `RAISE` x typical, a schedule has `MAX_RAISES` raises at most, and no
   schedule opens under 0.8 x typical, the lowest opening of the saved weeks. `wait` is not in one gig's data: it
   is set so that the model agrees with the one measured fact, the slow climb from 0.68 x typical that made 2,272
   euros a week less than the flat 0.88.
4. **The program.** State: the slice of the planning time and the fee shown. Action: the next fee, never lower.
   It ends in a booking (the fee, the wait charge and the chance of a drop) or at the end of the planning time, at
   the terminal cost: what the gigs that got there paid, plus `LATE` x typical for each late one. Backward
   induction for each opening fee. The guard: a kind's terminal cost goes up until its gigs are open at the end no
   more often than with today's raises.
"""

from __future__ import annotations

import argparse
import builtins
import collections
import functools
import itertools
import json
import math
import pickle
import sqlite3
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "strategies" / "lean" / "feetable.json"
D, H = 1440, 60
WAKE, SLEEP = 7 * H, 21 * H
SLICE = 15
PLAN_AHEAD = 28 * H
# Today's raises (DEFAULTS of index.ts), for the comparison and the on-time guard.
TODAY = {"open": 0.88, "early": 0.8, "raises": [[0.3, 1.05], [0.55, 1.25], [0.8, 1.55]]}
# Assumed, not measured.
RAISE = 0.01  # a raise, × typical
MAX_RAISES = 4
GUARD = 0.002  # a kind may be open at the end this much more often than with today's raises
LATE = 1.5  # a late car, x typical: the refund is 0.7 x typical, the rest the dealer's trust and the 90% rule
DROP_COST = 0.3  # a drop, × typical: the gig starts again from its booked fee with less time
FLAT_LOSS = 1063 / 350 / 64.6  # what a flat 0.80 lost a gig against a flat 0.88, x typical
CLIMB_LOSS = 2272 / 350 / 64.6  # the slow climb's measured loss a gig, × typical (350 orders, typical €64.6)
FEES = [round(0.6 + 0.05 * i, 2) for i in range(29)]  # 0.6 to 2.0
OPEN_LOW, OPEN_HIGH = 0.8, 1.3  # the opening fees the program may choose: no saved week opened under 0.8
K = 12  # slices of the planning time in the program
KNOTS = [0.0, 0.3, 0.65, 1.0]
NONE = [0.0, 0.5, 1.0]  # the knots of the share of gigs that no fee books yet
STILL_FROM = 840  # in the still reading, m stops falling this many waking minutes after the post
PROBE_FEES = [0.5, 0.6, 0.7, 0.8, 0.88, 1.0, 1.2, 1.5]
SIGMA, MAX_FALL, PRIOR = 0.22, 1.0, 200  # the prior on sigma and on the fall of m, as strong as this many gigs
PROBE_WEIGHT = 3  # a probed order counts as this many gigs: only the probes show other opening fees
PRE = [15, 60, 240, 840, 1680, 3360]  # waking minutes after the post: m is higher until the drivers have looked
EARLY = 60  # a gig for a later day shows its early fee this long (fees.ts)
SHORT = 6 * H
CLASSES = "ABCDEF"


def awake(a: float, b: float) -> float:
    return sum(max(0, min(b, d * D + SLEEP) - max(a, d * D + WAKE)) for d in range(int(a // D), int(b // D) + 1))


def plan_by(now: int, last: int) -> int:
    evening = (last // D) * D - (D - SLEEP)
    if last % D >= 16 * H:
        return last - 5 * H
    return evening if awake(now, evening) >= H else last - 3 * H


def week_class(last: int) -> int:
    day = last // D
    return 0 if day < 4 else 1 if day == 4 else 2


# ------------------------------------------------------------------------------------------------- the saved weeks


def load(db: Path) -> list[dict]:
    """The first gig of every one-car order: its schedule, first booking and what the order paid."""
    cache = Path(tempfile.gettempdir()) / f"lean_fee_table-{db.stem}-{db.stat().st_size}.pkl"
    if cache.exists() and cache.stat().st_mtime > db.stat().st_mtime:
        return pickle.loads(cache.read_bytes())
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out = []
    for (w,) in c.execute("select id from weeks where level=8").fetchall():
        typ = dict(c.execute("select id,reference_fee_cents from requests where week_id=? and legs=1", (w,)))
        last = {
            i: (lp, late)
            for i, lp, late in c.execute("select id,last_pickup_at,late_minutes from orders where week_id=?", (w,))
        }
        first: dict[str, tuple] = {}
        paid: dict[str, int] = collections.Counter()
        for gid, oid, cars, p, sch, status, fee in c.execute(
            "select id,order_id,cars,posted_at,schedule,status,fee_cents from gigs where week_id=? order by posted_at",
            (w,),
        ):
            first.setdefault(oid, (gid, cars, p, sch))
            if status == "done" and cars == 1:
                paid[oid] += fee
        gigs = {g: (o, p, sch) for o, (g, cars, p, sch) in first.items() if cars == 1 and o in typ and o in last}
        book: dict[str, tuple] = {}
        for g, at, data in c.execute(
            "select gig_id,at,data from events where week_id=? and kind='gig_booked' order by seq", (w,)
        ):
            if g in gigs and g not in book:
                book[g] = (at, json.loads(data)["feeCents"])
        expired = {}
        for g, at in c.execute(
            "select gig_id,at from events where week_id=? and kind='gig_expired' order by seq", (w,)
        ):
            expired.setdefault(g, at)
        for g, (o, p, sch) in gigs.items():
            steps = json.loads(sch)
            if steps[0]["at"] != p:
                continue  # repriced: the first schedule is gone
            out.append(
                {
                    "typ": typ[o],
                    "last": last[o][0],
                    "late": (last[o][1] or 0) > 0,
                    "p": p,
                    "sch": steps,
                    "book": book.get(g),
                    "exp": expired.get(g),
                    "paid": paid.get(o, 0),
                }
            )
    cache.write_bytes(pickle.dumps(out))
    return out


def gig_class(now: int, last: int) -> tuple[str, float, float]:
    """The class of a gig, its planning time (28 waking hours at most) and the waking minutes it holds before it.
    A: collected today, under six hours to plan. B: today, more. C: planned by 21:00 the evening before, posted
    that day. D: posted the day before, planned on the day. E: posted earlier. F: posted over 28 waking hours
    before the end of its planning time, so it holds its opening fee first."""
    plan = plan_by(now, last)
    left = awake(now, plan)
    time = min(left, PLAN_AHEAD)
    lead = last // D - now // D
    if left > PLAN_AHEAD:
        return "F", time, left - time
    if lead <= 0:
        return ("A" if time < SHORT else "B"), time, 0
    if lead == 1:
        return ("C" if plan < (last // D) * D else "D"), time, 0
    return "E", time, 0


def rows(gigs: list[dict]):
    """Checkpoints of each gig while it is open: the end of each fee, each knot, and its booking or its end."""
    cols = collections.defaultdict(list)
    term = []
    for gi, g in enumerate(gigs):
        p, last = g["p"], g["last"]
        plan = plan_by(p, last)
        if awake(p, plan) < 60:
            continue
        cls, time, hold = gig_class(p, last)
        stop = min(plan, g["exp"] or 10**9, last - 90)
        b = g["book"]
        hit = b is not None and b[0] <= stop
        end = b[0] if hit else stop
        n = int(awake(p, end) // SLICE) + 1
        t, fees = p, []
        for i in range(n):
            if t % D >= SLEEP:
                t = (t // D + 1) * D + WAKE
            elif t % D < WAKE:
                t = (t // D) * D + WAKE
            fees.append(max(s["feeCents"] for s in g["sch"] if s["at"] <= max(p, min(t + SLICE - 1, end))))
            t += SLICE
        if hit:
            fees[-1] = b[1]
        since = 99
        for i in range(n):
            if i > 0 and fees[i] > fees[i - 1]:
                since = 0
            u = min(1.0, max(0.0, ((i + 1) * SLICE - hold) / time))
            u_next = min(1.0, max(0.0, ((i + 2) * SLICE - hold) / time))
            knot = (any(u < k <= u_next for k in KNOTS) and since >= 3) or (i + 1) * SLICE in PRE
            if i == n - 1 or fees[i + 1] > fees[i] or knot:
                cols["g"].append(gi)
                cols["u"].append(u)
                cols["w"].append((i + 1) * SLICE)
                cols["time"].append(time)
                cols["hold"].append(hold)
                cols["r"].append(math.log(fees[i] / g["typ"]))
                cols["ev"].append(1 if hit and i == n - 1 else 0)
                cols["cls"].append(CLASSES.index(cls))
                cols["wk"].append(week_class(last))
            since += 1
        if not hit and stop == plan:
            term.append((g["paid"] / g["typ"], g["late"]))
    data = {k: np.array(v) for k, v in cols.items()}
    data["first"] = np.concatenate([[True], data["g"][1:] != data["g"][:-1]])
    return data, term


# --------------------------------------------------------------------------------------------------------- the fit


def unpack(x, still: bool = False) -> dict:
    """m at the knots (falling), what it is higher by in the first minutes, the share of gigs that no fee books
    yet at its knots (falling), sigma, the shifts of m for a Friday pickup and one after the weekend, and the shift
    of the probed weeks, whose desk never raised a fee."""
    n = len(KNOTS)
    k = n + len(PRE) - 1
    # The still reading: nothing gets easier after the first four hours, so a late booking is the raise's.
    live = 0.0 if still else 1.0
    m = x[0] - live * np.concatenate([[0], np.cumsum(np.exp(x[1:n]))])
    pre = np.concatenate(
        [np.cumsum((np.exp(x[n:k]) * np.where(np.array(PRE[:-1]) >= STILL_FROM, live, 1.0))[::-1])[::-1], [0]]
    )
    none = 1 / (1 + np.exp(-(x[k] - live * np.concatenate([[0], np.cumsum(np.exp(x[k + 1 : k + 3]))]))))
    return {
        "m": [float(v) for v in m],
        "pre": [float(v) for v in pre],
        "none": [float(v) for v in none],
        "sigma": math.exp(x[k + 3]),
        "week": [0.0, float(x[k + 4]), float(x[k + 5])],
        "probe": float(x[k + 6]),
    }


def found(q: dict, u, w, r, wk, shift=0.0):
    """G: the chance that a gig has its driver by the share u of its planning time, w waking minutes after its
    post, at the fee exp(r): the share of gigs that a fee can book by then, x the share of those whose threshold
    is under the fee."""
    z = (r - np.interp(u, KNOTS, q["m"]) - np.interp(w, PRE, q["pre"]) - np.asarray(q["week"])[wk] - shift) / q["sigma"]
    return (1 - np.interp(u, NONE, q["none"])) / (1 + np.exp(-np.clip(z, -40, 40)))


def probes() -> dict:
    """The fee probes (sim/README.md): for each probed order, whether a flat fee booked it within three hours, at
    each of PROBE_FEES. The trials of one order are forks of one gig, so its lowest booking fee is its threshold."""
    cols = collections.defaultdict(list)
    for file in sorted((ROOT / "data" / "scrape").glob("probe[23]/fee/L8/*/probes.jsonl")):
        for line in file.read_text().splitlines():
            try:
                q = json.loads(line)
            except json.JSONDecodeError:
                continue
            if q.get("kind") != "fee" or len(q.get("lane") or []) != 1 or q.get("premium") or not q.get("trials"):
                continue
            at, last = q["at"], q["lastPickupAt"]
            if awake(at, plan_by(at, last)) < 60:
                continue
            cls, time, hold = gig_class(at, last)
            w = awake(at, at + q["windowMinutes"])
            flip = min(
                [t["feeCents"] / q["referenceFeeCents"] for t in q["trials"] if t["minutes"] is not None],
                default=math.inf,
            )
            for fee in PROBE_FEES:
                cols["cls"].append(CLASSES.index(cls))
                cols["wk"].append(week_class(last))
                cols["u"].append(min(1.0, max(0.0, (w - hold) / time)))
                cols["w"].append(w)
                cols["r"].append(math.log(fee))
                cols["hit"].append(flip <= fee)
    return {k: np.array(v) for k, v in cols.items()}


def hazards(x, data, still=False):
    return np.clip(hazards_of(unpack(x, still), data), 1e-9, 1 - 1e-9)


def loglik(x, data, pr, still=False) -> float:
    """With a weak prior on the weekday and probe shifts (sd 0.3), for the classes that have no such gigs."""
    h = hazards(x, data, still)
    ll = (
        float(np.where(data["ev"] == 1, np.log(h), np.log(1 - h)).sum())
        - 0.5 * float(x[-3] ** 2 + x[-2] ** 2 + x[-1] ** 2) / 0.09
    )
    # Gigs differ as the probes say (sigma 0.15 to 0.25 where both fit), and m falls by MAX_FALL at most.
    q = unpack(x, still)
    ll -= 0.5 * ((math.log(q["sigma"]) - math.log(SIGMA)) / 0.25) ** 2 * PRIOR
    ll -= PRIOR * 50 * (max(0.0, q["m"][0] - q["m"][-1] - MAX_FALL) ** 2 + max(0.0, q["pre"][0] - MAX_FALL) ** 2)
    if len(pr["r"]):
        g = np.clip(found(q, pr["u"], pr["w"], pr["r"], pr["wk"], q["probe"]), 1e-9, 1 - 1e-9)
        ll += PROBE_WEIGHT / len(PROBE_FEES) * float(np.where(pr["hit"], np.log(g), np.log(1 - g)).sum())
    return ll


def nelder_mead(f, x0, iters=6000, step=0.3):
    n = len(x0)
    pts = [np.array(x0, dtype=float)] + [np.array(x0, dtype=float) + step * np.eye(n)[i] for i in range(n)]
    vals = [f(p) for p in pts]
    for _ in range(iters):
        order = np.argsort(vals)
        pts, vals = [pts[i] for i in order], [vals[i] for i in order]
        if abs(vals[-1] - vals[0]) < 1e-3:
            break
        centre = np.mean(pts[:-1], axis=0)
        refl = centre + (centre - pts[-1])
        fr = f(refl)
        if fr < vals[0]:
            exp = centre + 2 * (centre - pts[-1])
            fe = f(exp)
            pts[-1], vals[-1] = (exp, fe) if fe < fr else (refl, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = refl, fr
        else:
            con = centre + 0.5 * (pts[-1] - centre)
            fc = f(con)
            if fc < vals[-1]:
                pts[-1], vals[-1] = con, fc
            else:
                pts = [pts[0]] + [pts[0] + 0.5 * (p - pts[0]) for p in pts[1:]]
                vals = [vals[0]] + [f(p) for p in pts[1:]]
    best = int(np.argmin(vals))
    return pts[best], vals[best]


def fit(data, pr, still=False) -> dict:
    start = (
        [0.0] + [-2.5] * (len(KNOTS) - 1) + [-2.0] * (len(PRE) - 1) + [-1.0, -2.0, -2.0, math.log(0.25), 0.1, 0.1, 0.0]
    )
    x, _ = nelder_mead(lambda x: -loglik(x, data, pr, still), start)
    for _ in range(4):
        x, _ = nelder_mead(lambda x: -loglik(x, data, pr, still), x, step=0.15)
    return unpack(x, still)


# ----------------------------------------------------------------------------------------------------- the program


class Cost:
    def __init__(self, wait: float, terminal_paid: float, late_share: float, extra: float = 0.0):
        self.wait, self.terminal_paid = wait, terminal_paid
        self.terminal = terminal_paid + LATE * late_share + extra

    def booking(self, j: int, j0: int) -> float:
        """A booking at the fee j of a gig that opened at j0: the fee, the wait charge and the chance of a drop
        (15% of the bookings at 0.8 x typical were dropped, 11% at 1.0, 5% from 1.2)."""
        fee = FEES[j]
        drop = min(0.3, max(0.04, 0.15 + 0.2 * (0.8 - fee) if fee < 1 else 0.11 - 0.3 * (fee - 1)))
        return fee + self.wait * (fee / FEES[j0] - 1) + drop * DROP_COST


class Kind:
    """One class of gig on one kind of pickup day: its slices, and G at the end of each slice for each fee. A gig
    for a later day (classes C to F) has a first slice of its own, the hour of its early fee; class F then holds
    its opening fee until its planning time starts."""

    def __init__(self, qs: list[dict], name: str, wk: int, time: float, hold: float):
        ends: list[tuple[float, float]] = []  # the waking minutes after the post and the share at which a slice ends
        self.share: list[float | None] = []  # the share at which a slice starts; None for the early and the opening fee
        if name >= "C":
            ends.append((EARLY, min(1.0, max(0.0, (EARLY - hold) / time))))
            self.share.append(None)
        if name == "F":
            ends.append((hold, 0.0))
            self.share.append(None)
        for k in range(K):
            end = hold + (k + 1) / K * time
            if end > EARLY or name < "C":
                ends.append((end, (k + 1) / K))
                self.share.append(k / K if len(ends) > (1 if name < "C" else 2) else None)
        self.n = len(ends)
        self.early = name >= "C"
        r = np.log(np.array(FEES))
        each = [
            np.array(
                [found(q, np.full(len(FEES), u), np.full(len(FEES), w), r, np.full(len(FEES), wk)) for w, u in ends]
            )
            for q in qs
        ]
        # The program plays against the mean of the two readings; the guard looks at the still one.
        self.g, self.still = np.mean(each, axis=0), each[-1]

    def path(self, fee) -> list[int]:
        """The fee index of each slice, for a schedule given as a function of (share or None, slice)."""
        return [nearest(fee(share, i)) for i, share in enumerate(self.share)]

    def today(self) -> list[int]:
        """Today's raises on this kind's slices."""

        def fee(share, i):
            if share is None:
                return TODAY["early"] if self.early and i == 0 else TODAY["open"]
            return max([TODAY["open"]] + [to for at, to in TODAY["raises"] if share + 0.5 / K >= at])

        return self.path(fee)

    def climb(self) -> list[int]:
        """The slow climb of the first weeks: 0.68 x typical for half of the time, then up to 1.3 by four fifths."""
        return self.path(lambda share, i: 0.68 + (1.3 - 0.68) * min(1, max(0, ((share or 0) + 0.5 / K - 0.5) / 0.3)))

    def flat(self, level: float) -> list[int]:
        return [nearest(level)] * self.n

    def entry(self, path: list[int]) -> list:
        """[the early fee or 0, the opening fee, [share of the planning time, fee] for each raise]."""
        first = 1 if self.early else 0
        early = FEES[path[0]] if self.early and path[0] < path[1] else 0
        return [early, FEES[path[first]]] + [
            [round(self.share[i], 4), FEES[path[i]]] for i in range(first + 1, self.n) if path[i] > path[i - 1]
        ]

    def evaluate(self, path: list[int], cost: Cost, still: bool = False) -> dict:
        """What a schedule (the fee index of each slice) is expected to cost, and how often it is still open."""
        done, total, fee, wait = 0.0, 0.0, 0.0, 0.0
        g = self.still if still else self.g
        for k, j in enumerate(path):
            p = max(0.0, float(g[k, j]) - done)
            total += p * cost.booking(j, path[0])
            fee += p * FEES[j]
            wait += p * (FEES[j] / FEES[path[0]] - 1)
            done += p
        raises = sum(1 for a, b in itertools.pairwise(path) if b > a)
        return {
            "cost": total + (1 - done) * cost.terminal + raises * RAISE,
            "open": 1 - done,
            "wait": wait,
            "paid": fee,
            "booked": fee / max(1e-9, done),
        }

    def solve(self, cost: Cost, raise_cost: float) -> list[int]:
        """Backward induction over (slice, fee shown) for each opening fee; the cheapest path."""
        nj = len(FEES)
        best = None
        for j0 in (j for j in range(nj) if OPEN_LOW <= FEES[j] <= OPEN_HIGH):
            book = np.array([cost.booking(j, j0) for j in range(nj)])
            value = np.full(nj, cost.terminal)  # by the fee shown in the slice before
            choice = np.zeros((self.n, nj), dtype=int)
            for k in range(self.n - 1, 0, -1):
                new = np.empty(nj)
                for j in range(nj):
                    was = self.g[k - 1, j]
                    p = np.maximum(self.g[k, j:] - was, 0) / max(1e-12, 1 - was)
                    options = p * book[j:] + (1 - p) * value[j:] + raise_cost * (np.arange(j, nj) > j)
                    choice[k, j] = j + int(np.argmin(options))
                    new[j] = options.min()
                value = new
            p0 = float(self.g[0, j0])
            total = p0 * book[j0] + (1 - p0) * value[j0]
            if best is None or total < best[0]:
                path = [j0]
                for k in range(1, self.n):
                    path.append(int(choice[k, path[-1]]))
                best = (total, path)
        return best[1]


def nearest(fee: float) -> int:
    return min(range(len(FEES)), key=lambda j: abs(FEES[j] - fee))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", type=Path, default=ROOT / "out" / "lean.sqlite")
    ap.add_argument("--write", action="store_true", help=f"save {OUT.relative_to(ROOT)}")
    ap.add_argument("--wait", type=float, help="the wait charge x typical, instead of the calibrated one")
    args = ap.parse_args()
    print = functools.partial(builtins.print, flush=True)

    data, term = rows(load(args.db))
    gigs = int(data["first"].sum())
    print(
        f"{gigs} first gigs of one-car orders, {int(data['ev'].sum())} booked in their planning time, {len(data['g'])} checkpoints"
    )
    paid = float(np.mean([t[0] for t in term if t[0] > 0]))
    late = float(np.mean([t[1] or t[0] == 0 for t in term]))
    print(
        f"{len(term)} gigs reached the end of their planning time open: they paid {paid:.2f} x typical, {100 * late:.0f}% late or not driven"
    )

    pr = probes()
    print(f"{len(pr['r']) // len(PROBE_FEES)} probed orders")
    models, kinds, weight = {}, {}, {}
    for c, name in enumerate(CLASSES):
        part = {k: v[data["cls"] == c] for k, v in data.items()}
        pp = {k: v[pr["cls"] == c] for k, v in pr.items()}
        time = float(np.median(part["time"][part["first"]]))
        hold = float(np.median(part["hold"][part["first"]]))
        level = np.digitize(np.exp(part["r"]), [0.84, 0.95, 1.15, 1.4, 1.8])
        print(f"class {name}: {int(part['first'].sum())} gigs, {time / 60:.1f} h to plan after {hold / 60:.1f} h")
        models[name] = [fit(part, pp), fit(part, pp, True)]
        for label, q in zip(("moving", "still "), models[name]):
            h = hazards_of(q, part)
            check = " ".join(f"{int(part['ev'][level == b].sum())}/{h[level == b].sum():.0f}" for b in range(6))
            print(
                f"   {label}: m {[round(v, 2) for v in q['m']]} first minutes {[round(v, 2) for v in q['pre'][:-1]]} no fee books {[round(v, 2) for v in q['none']]} "
                f"sigma {q['sigma']:.2f} probes {q['probe']:+.2f} Friday {q['week'][1]:+.2f} after the weekend {q['week'][2]:+.2f}; booked/expected at <0.84, 0.88, 1.05, 1.25, 1.55, 2.0: {check}"
            )
            if len(pp["r"]):
                g = found(q, pp["u"], pp["w"], pp["r"], pp["wk"], q["probe"])
                print(
                    "      probes, booked within 3 h / the model: "
                    + " ".join(
                        f"{fee}: {pp['hit'][pp['r'] == math.log(fee)].mean():.2f}/{g[pp['r'] == math.log(fee)].mean():.2f}"
                        for fee in PROBE_FEES
                    )
                )
        for wk in range(3):
            kinds[(name, wk)] = Kind(models[name], name, wk, time, hold)
            weight[(name, wk)] = int((part["first"] & (part["wk"] == wk)).sum())
    total = sum(weight.values())
    mean = lambda f: sum(weight[k] * f(k) for k in kinds) / total

    def gap(a, b, field, cost):
        value = lambda k, x: kinds[k].evaluate(getattr(kinds[k], x[0])(*x[1:]), cost)[field]
        return mean(lambda k: value(k, a) - value(k, b))

    # The wait charge is not in one gig's data. It is set so that the model agrees with the one measured fact: the
    # slow climb from 0.68 x typical made CLIMB_LOSS less a gig than the flat 0.88.
    free = Cost(0, paid, late)
    print(
        f"a check: the model says a flat 0.80 costs {gap(('flat', 0.8), ('flat', 0.88), 'cost', free):+.3f} x typical a gig against a flat 0.88, "
        f"with {100 * gap(('flat', 0.8), ('flat', 0.88), 'open', free):+.1f}% of the gigs open at the end; five server seeds said {FLAT_LOSS:+.3f}"
    )
    gain = -gap(("climb",), ("flat", 0.88), "cost", free)
    more = gap(("climb",), ("flat", 0.88), "wait", free)
    wait = args.wait if args.wait is not None else max(0.0, (gain + CLIMB_LOSS) / max(1e-9, more))
    print(
        f"without a wait charge the model says the slow climb saves {gain:.3f} x typical a gig; it lost {CLIMB_LOSS:.3f}. "
        f"Its bookings are {more:.3f} further over the first fee, so the wait charge is {wait:.2f} x typical"
    )
    paid_open = paid

    # Each kind's terminal cost goes up until it is open at the end no more often than with today's raises.
    base = Cost(wait, paid, late)
    table, report, terminals = {}, {}, {}
    for key, kind in kinds.items():
        old, old_still = kind.evaluate(kind.today(), base), kind.evaluate(kind.today(), base, True)
        for extra in (0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0):
            cost, raise_cost = Cost(wait, paid, late, extra), RAISE
            while True:
                path = kind.solve(cost, raise_cost)
                if sum(1 for a, b in itertools.pairwise(path) if b > a) <= MAX_RAISES:
                    break
                raise_cost *= 2
            new = kind.evaluate(path, base)
            if (
                new["open"] <= old["open"] + GUARD
                and kind.evaluate(path, base, True)["open"] <= old_still["open"] + GUARD
            ):
                break
        table[key], report[key], terminals[key] = kind.entry(path), (new, old), cost.terminal
    print(
        f"open at the end: {100 * mean(lambda k: report[k][0]['open']):.2f}% with the table, {100 * mean(lambda k: report[k][1]['open']):.2f}% with today's raises"
    )
    for i, label in ((0, "the table"), (1, "today's raises")):
        fees = mean(lambda k, i=i: report[k][i]["paid"] + report[k][i]["open"] * paid_open)
        over = mean(lambda k, i=i: report[k][i]["wait"])
        charged = mean(lambda k, i=i: report[k][i]["cost"])
        print(
            f"{label}: {fees:.3f} x typical a gig in fees ({paid_open:.2f} for a gig open at the end), {over:.3f} over the opening fee, "
            f"{charged:.3f} with the wait, drop and late charges"
        )
    for key in sorted(kinds):
        new, old = report[key]
        print(
            f"  {key[0]}{key[1]} ({weight[key]:5d} gigs): {table[key]}  fees {new['paid'] + new['open'] * paid_open:.3f} vs {old['paid'] + old['open'] * paid_open:.3f}, open at the end {100 * new['open']:.1f}% vs {100 * old['open']:.1f}%, terminal {terminals[key]:.2f}"
        )
    if args.write:
        doc = {
            "about": "Written by analysis/lean_fee_table.py: the planned raises of a single-car gig, by its class (gig_class there, classOf in feetable.ts) and its pickup day (0 Monday to Thursday, 1 Friday, 2 after the weekend). Each entry: the early fee (0 for none), the opening fee, then [share of the planning time, fee] for each raise; fees x typical.",
            "model": {
                "wait": round(wait, 3),
                "terminal": round(base.terminal, 3),
                "raise": RAISE,
                "late": LATE,
                "drop": DROP_COST,
                "classes": {
                    name: [
                        {k: ([round(u, 3) for u in v] if isinstance(v, list) else round(v, 3)) for k, v in q.items()}
                        for q in qs
                    ]
                    for name, qs in models.items()
                },
            },
            "table": {f"{name}{wk}": table[(name, wk)] for name, wk in sorted(kinds)},
        }
        text = json.dumps(doc, separators=(",", ":"))
        OUT.write_text(
            text.replace('"table":{', '"table":{\n').replace('],"', '],\n"').replace('"model":', '\n"model":') + "\n"
        )
        print(
            f"wrote {OUT.relative_to(ROOT)}: {len(table)} kinds. Format it: pnpm exec biome format --write {OUT.relative_to(ROOT)}"
        )


def hazards_of(q: dict, data):
    p = found(q, data["u"], data["w"], data["r"], data["wk"])
    before = np.where(data["first"], 0, np.concatenate([[0], p[:-1]]))
    return (np.maximum(p, before) - before) / np.maximum(1 - before, 1e-12)


if __name__ == "__main__":
    main()
