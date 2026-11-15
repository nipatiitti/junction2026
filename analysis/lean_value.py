"""Fits lean's value table (`src/strategies/lean/value.json`, read by `value.ts` when the param `value` is not 0):
what one more order takes from the rest of the week, by the state the desk sees at the quote.

The state is (minute of the week, orders won so far per driver, late share so far). The charge of an order is
V(state) - V(state with the order), with the week's later wins held as lean plays them. It has two parts:

1. Crowding. Within a seed and a day, each order per driver won before a car is booked raises that car's fee and
   its refunds (`slopes`). So one more order costs every car that is booked after it. The cost to go of a state is
   the sum of those slopes over the cars still to be booked, fitted backwards from the end of the week: at each
   2-hour step, the cost of the step plus the fitted value of the next state, as a line in the load (`to_go`).
2. The 90% rule. A week under 90% on time scores nothing, so an order that moves the final late share moves the
   chance to lose the week's margin. The final late share is fitted as lognormal around what the day, the late
   share so far and the load say (`cliff`); the charge is the week's margin x the density at 10% x what the order
   adds to the late share: its own chance to be late (by day and option) and the late cars it causes, less the
   share it dilutes.

The crowding part is scaled (`level`) so that its mean over the saved requests is the mean of today's charge
(`taxLoad` x load x cost): the table moves the charge between orders, not the volume of the week.

    uv run python -m tools.db --db out/lean.sqlite $(cat out/lean_folders.txt)   # the saved lean weeks
    uv run python -m analysis.lean_value            # prints the fit
    uv run python -m analysis.lean_value --write    # and saves value.json; then `pnpm format`
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import sqlite3
import statistics
from pathlib import Path

DAY = 1440
SLOT = 120
QUOTE_SLOTS = 5 * DAY // SLOT  # requests arrive from Monday to Friday
ALL_SLOTS = 9 * DAY // SLOT  # cars are booked until the second Tuesday
LOAD_STEP = 0.05
LOADS = 25  # 0 to 1.2 orders per driver
LATE_STEP = 0.01
LATES = 21  # 0 to 20% late
LATE_PRIOR = 20  # index.ts: the late share starts as if 20 orders had arrived on time
KINDS = ("same_day", "next_day", "within_3_days")
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "later")
# Today's charge (index.ts): taxLoad x load x cost, with the load as `load()` computes it.
TAX_LOAD = 0.47
MEAN_COST_CENTS = 2870 / 0.47
WEEK_REQUESTS = 1033
LOAD_START = 0.5
LOAD_PRIOR = 150
MODEL = Path("src/strategies/lean/value.json")


def read(db: sqlite3.Connection) -> list[dict]:
    """The saved lean weeks: their orders with what each paid, when it was won and when it was booked."""
    weeks = []
    query = "select id, seed, margin_cents, (select count(*) from drivers d where d.week_id = weeks.id) from weeks"
    for week_id, seed, margin, drivers in db.execute(f"{query} where policy like '%lean%' and level = 8"):
        if not drivers:
            continue
        booked: dict[str, int] = {}
        times = dict(
            db.execute(
                "select gig_id, max(at) from events where week_id = ? and kind = 'gig_booked' group by 1", (week_id,)
            )
        )
        for gig_id, stops in db.execute("select id, stops from gigs where week_id = ? and status = 'done'", (week_id,)):
            for stop in json.loads(stops or "[]"):
                if gig_id in times:
                    booked[stop["orderId"]] = max(booked.get(stop["orderId"], 0), times[gig_id])
        money: dict[str, dict[str, int]] = collections.defaultdict(lambda: collections.defaultdict(int))
        late_at: dict[str, int] = {}
        done_at: list[int] = []
        for at, kind, cents, order_id in db.execute(
            "select at, kind, cents, order_id from ledger where week_id = ?", (week_id,)
        ):
            if not order_id:
                continue
            money[order_id][kind] -= cents
            if kind in ("late_refund", "undelivered_penalty"):
                late_at[order_id] = min(late_at.get(order_id, at), at)
            if kind == "revenue":
                done_at.append(at)
        orders = []
        for order_id, option, status, late_minutes, last_pickup, arrived, typical in db.execute(
            """select o.id, o.option, o.status, o.late_minutes, o.last_pickup_at, r.arrived_at, r.reference_fee_cents
            from orders o join requests r on r.week_id = o.week_id and r.id = o.id where o.week_id = ?
            order by r.arrived_at""",
            (week_id,),
        ):
            paid = money[order_id]
            orders.append(
                {
                    "won": arrived,
                    "booked": booked.get(order_id, last_pickup or arrived),
                    "kind": option,
                    "cancelled": status == "cancelled",
                    "typical": typical,
                    "fee": paid["driver_fee"],
                    "refund": paid["late_refund"] + paid["undelivered_penalty"],
                    "late": 1 if (late_minutes or 0) > 0 or status not in ("delivered", "cancelled") else 0,
                }
            )
        requests = [
            (at, typical)
            for at, typical in db.execute(
                "select arrived_at, reference_fee_cents from requests where week_id = ? order by arrived_at", (week_id,)
            )
        ]
        weeks.append(
            {
                "seed": seed,
                "margin": margin,
                "drivers": drivers,
                "orders": orders,
                "requests": requests,
                "late_at": sorted(late_at.values()),
                "done_at": sorted(done_at),
            }
        )
    return weeks


def count_before(times: list[int], at: int) -> int:
    """How many of the sorted `times` are before `at`."""
    low, high = 0, len(times)
    while low < high:
        mid = (low + high) // 2
        if times[mid] < at:
            low = mid + 1
        else:
            high = mid
    return low


def line(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """The least-squares line through the points: its value at x = 0 and its slope (0 when x does not vary)."""
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx < 1e-9 * len(xs):
        return my, 0.0
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - slope * mx, slope


def slopes(weeks: list[dict]) -> tuple[dict[str, list[float]], float]:
    """What an order per driver won before a car is booked adds to that car, by the day it is booked: its fee over
    typical, its refund in cents and its chance to be late. Within a seed and a day, across that seed's weeks; each
    day's slope is shrunk to the slope of all days by how sure it is. Also returns the mean typical fee."""
    cells: dict[tuple[str, int], list[tuple[float, dict[str, float]]]] = collections.defaultdict(list)
    typicals = []
    for week in weeks:
        won = [o["won"] for o in week["orders"]]
        by_day: dict[int, list[dict]] = collections.defaultdict(list)
        for order in week["orders"]:
            if order["cancelled"]:
                continue
            order["load"] = count_before(won, order["booked"]) / week["drivers"]
            by_day[min(5, order["booked"] // DAY)].append(order)
            typicals.append(order["typical"])
        for day, group in by_day.items():
            if len(group) < 5:
                continue
            outcome = {
                "fee": sum(o["fee"] for o in group) / sum(o["typical"] for o in group),
                "refund": statistics.fmean(o["refund"] for o in group),
                "late": statistics.fmean(o["late"] for o in group),
            }
            cells[(week["seed"], day)].append((statistics.fmean(o["load"] for o in group), outcome))
    fitted: dict[str, list[float]] = {}
    for key in ("fee", "refund", "late"):
        # Each day's points, with the mean of their seed and day taken out.
        points: dict[int, list[tuple[float, float]]] = collections.defaultdict(list)
        for (_, day), cell in cells.items():
            if len(cell) < 3:
                continue
            mx = statistics.fmean(x for x, _ in cell)
            my = statistics.fmean(y[key] for _, y in cell)
            points[day] += [(x - mx, y[key] - my) for x, y in cell]
        everything = [p for day in points.values() for p in day]
        pooled = sum(x * y for x, y in everything) / sum(x * x for x, _ in everything)
        raw, errors = {}, {}
        for day, pts in points.items():
            sxx = sum(x * x for x, _ in pts)
            raw[day] = sum(x * y for x, y in pts) / sxx
            rest = sum((y - raw[day] * x) ** 2 for x, y in pts) / max(1, len(pts) - 1)
            errors[day] = rest / sxx
        # How much the days truly differ: the spread of their slopes less their noise.
        spread = max(1e-12, statistics.pvariance(raw.values()) - statistics.fmean(errors.values()))
        fitted[key] = []
        for day in range(6):
            if day not in raw:
                fitted[key].append(pooled)
                continue
            weight = spread / (spread + errors[day])
            # No day's slope is under zero: Monday's fee slope is negative, on loads that differ by 0.01 only.
            fitted[key].append(max(0.0, weight * raw[day] + (1 - weight) * pooled))
        print(f"{key:>7}: all days {pooled:8.3f}; by day booked, raw (± error) -> used")
        for day in range(6):
            if day in raw:
                print(
                    f"         {DAYS[day]:>5} {raw[day]:8.3f} ± {math.sqrt(errors[day]):6.3f} -> {fitted[key][day]:8.3f}"
                )
    return fitted, statistics.fmean(typicals)


def to_go(weeks: list[dict], per_car: list[float]) -> list[list[float]]:
    """The cost to go by 2-hour step and load: the sum of `per_car` (by the day a car is booked) over the cars
    booked from that step on, for one order more. Fitted backwards: at each step, a line in the load through
    (the cost of the step + the fitted value of the next state) of every week. Inside the loads seen at that step."""
    steps, loads = [], []
    for week in weeks:
        cost = [0.0] * ALL_SLOTS
        for order in week["orders"]:
            if not order["cancelled"]:
                slot = min(ALL_SLOTS - 1, order["booked"] // SLOT)
                cost[slot] += per_car[min(5, slot * SLOT // DAY)] / week["drivers"]
        won = [o["won"] for o in week["orders"]]
        steps.append(cost)
        loads.append([count_before(won, slot * SLOT) / week["drivers"] for slot in range(ALL_SLOTS + 1)])
    value = [0.0] * len(weeks)  # the fitted value of each week's next state
    table: list[list[float]] = [[] for _ in range(QUOTE_SLOTS + 1)]
    for slot in range(ALL_SLOTS - 1, -1, -1):
        xs = [load[slot] for load in loads]
        ys = [steps[w][slot] + value[w] for w in range(len(weeks))]
        base, slope = line(xs, ys)
        low, high = min(xs), max(xs)
        value = [base + slope * x for x in xs]
        if slot <= QUOTE_SLOTS:
            inside = [min(high, max(low, i * LOAD_STEP)) for i in range(LOADS)]
            table[slot] = [max(0.0, base + slope * load) for load in inside]
    return table


def solve(rows: list[list[float]], ys: list[float]) -> list[float]:
    """Least squares with a little ridge, by the normal equations."""
    size = len(rows[0])
    a = [
        [sum(r[i] * r[j] for r in rows) + (1e-6 * len(rows) if i == j and i > 0 else 0) for j in range(size)]
        for i in range(size)
    ]
    b = [sum(r[i] * y for r, y in zip(rows, ys)) for i in range(size)]
    for i in range(size):
        pivot = max(range(i, size), key=lambda k: abs(a[k][i]))
        a[i], a[pivot], b[i], b[pivot] = a[pivot], a[i], b[pivot], b[i]
        for k in range(i + 1, size):
            factor = a[k][i] / a[i][i]
            b[k] -= factor * b[i]
            for j in range(i, size):
                a[k][j] -= factor * a[i][j]
    out = [0.0] * size
    for i in range(size - 1, -1, -1):
        out[i] = (b[i] - sum(a[i][j] * out[j] for j in range(i + 1, size))) / a[i][i]
    return out


def cliff(weeks: list[dict]) -> tuple[list[list[float]], list[list[float]]]:
    """By day and late share so far: the final late share to expect, and what one late order more costs in cents
    through the 90% rule (the mean week's margin x the density of the final late share at 10%, over the week's
    orders). The log of the final late share is a line in the log of the late share so far and the load, with
    normal noise, fitted on every 2-hour step of the day. Late shares over the highest seen on that day read as it."""
    margin = statistics.fmean(w["margin"] for w in weeks)
    count = statistics.fmean(sum(1 for o in w["orders"] if not o["cancelled"]) for w in weeks)
    expect, price = [], []
    for day in range(5):
        rows, ys, loads, top = [], [], [], 0.0
        for week in weeks:
            kept = [o for o in week["orders"] if not o["cancelled"]]
            final = math.log(max(0.005, sum(o["late"] for o in kept) / len(kept)))
            won = [o["won"] for o in week["orders"]]
            for slot in range(day * DAY // SLOT, (day + 1) * DAY // SLOT):
                at = slot * SLOT
                share = count_before(week["late_at"], at) / (count_before(week["done_at"], at) + LATE_PRIOR)
                load = count_before(won, at) / week["drivers"]
                top = max(top, share)
                rows.append([1.0, math.log(share + 0.02), load])
                ys.append(final)
                loads.append(load)
        weights = solve(rows, ys)
        noise = math.sqrt(statistics.fmean((y - sum(w * x for w, x in zip(weights, r))) ** 2 for r, y in zip(rows, ys)))
        load = statistics.fmean(loads)
        expect.append([])
        price.append([])
        for i in range(LATES):
            mean = weights[0] + weights[1] * math.log(min(top, i * LATE_STEP) + 0.02) + weights[2] * load
            z = (math.log(0.10) - mean) / noise
            density = math.exp(-z * z / 2) / math.sqrt(2 * math.pi) / (noise * 0.10)
            expect[-1].append(math.exp(mean))
            price[-1].append(margin * density / count)
        print(
            f"  {DAYS[day]}: log final late share = {weights[0]:.2f} + {weights[1]:.2f} log(share so far + 0.02) + {weights[2]:.2f} load, noise {noise:.2f}; late share so far up to {100 * top:.1f}%"
        )
    return expect, price


def late_by_kind(weeks: list[dict]) -> dict[str, list[float]]:
    """The share of late orders by option and by the day the order was won."""
    seen: dict[tuple[str, int], list[int]] = collections.defaultdict(list)
    for week in weeks:
        for order in week["orders"]:
            if not order["cancelled"]:
                seen[(order["kind"], min(4, order["won"] // DAY))].append(order["late"])
    everything = statistics.fmean(late for group in seen.values() for late in group)
    # As if each cell had seen 50 orders at the mean of all.
    return {
        kind: [(sum(seen[(kind, day)]) + 50 * everything) / (len(seen[(kind, day)]) + 50) for day in range(5)]
        for kind in KINDS
    }


def between(table: list[list[float]], row: float, column: float) -> float:
    """The table between its rows and columns, as value.ts reads it."""
    r = min(len(table) - 1, max(0.0, row))
    c = min(len(table[0]) - 1, max(0.0, column))
    r0, c0 = min(len(table) - 2, int(r)), min(len(table[0]) - 2, int(c))
    fr, fc = r - r0, c - c0
    top = table[r0][c0] * (1 - fc) + table[r0][c0 + 1] * fc
    bottom = table[r0 + 1][c0] * (1 - fc) + table[r0 + 1][c0 + 1] * fc
    return top * (1 - fr) + bottom * fr


def level(weeks: list[dict], charge: list[list[float]], typical: float) -> float:
    """The scale that gives the crowding charge the mean of today's charge over the saved requests."""
    today = table = 0.0
    for week in weeks:
        won = [o["won"] for o in week["orders"]]
        drivers = week["drivers"]
        start = LOAD_START * drivers / WEEK_REQUESTS
        for seen, (at, request_typical) in enumerate(week["requests"]):
            size = request_typical / typical
            wins = count_before(won, at)
            load = (wins + LOAD_PRIOR * start) / (seen + LOAD_PRIOR) * WEEK_REQUESTS / drivers
            today += TAX_LOAD * load * MEAN_COST_CENTS * size
            table += between(charge, at / SLOT, wins / drivers / LOAD_STEP) * size
    return today / table


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Fits lean's value table on the saved lean weeks.")
    parser.add_argument("--db", type=Path, default=Path("out/lean.sqlite"), help="default out/lean.sqlite")
    parser.add_argument("--write", action="store_true", help=f"save the table to {MODEL}")
    args = parser.parse_args(argv)
    weeks = read(sqlite3.connect(f"file:{args.db}?mode=ro", uri=True))
    print(f"{len(weeks)} lean weeks of {len({w['seed'] for w in weeks})} seeds\n")
    per_load, typical = slopes(weeks)
    # What an order per driver more costs one car that is booked afterwards, in cents, by the day it is booked.
    per_car = [typical * per_load["fee"][day] + per_load["refund"][day] for day in range(6)]
    print("\ncents per car booked afterwards, for one order per driver more:", [round(c) for c in per_car])
    charge = to_go(weeks, per_car)
    spill = to_go(weeks, per_load["late"])
    print("\nthe 90% rule")
    expect, price = cliff(weeks)
    late = late_by_kind(weeks)
    scale = level(weeks, charge, typical)
    print(f"\nlevel {scale:.3f}: the crowding charge as fitted is {1 / scale:.2f} of today's mean charge")

    print(
        "\ncrowding charge in euros (x level), at 08:00, for an order of the mean typical fee, by orders per driver so far"
    )
    shown = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    print("       " + "".join(f"{load:8.1f}" for load in shown))
    for day in range(5):
        slot = (day * DAY + 480) // SLOT
        cells = "".join(f"{scale * between(charge, slot, load / LOAD_STEP) / 100:8.1f}" for load in shown)
        print(
            f"  {DAYS[day]:>5}{cells}   (causes {between(spill, slot, 0.1 * (day + 1) / LOAD_STEP):.3f} late cars at the usual load)"
        )
    print("\n90% rule: euros for a late order more, by late share so far")
    shares = [0, 2, 4, 6, 8, 10, 12]
    print("       " + "".join(f"{share:7d}%" for share in shares))
    for day in range(5):
        print(f"  {DAYS[day]:>5}" + "".join(f"{price[day][share] / 100:8.1f}" for share in shares))
    print("  final late share expected (%)")
    for day in range(5):
        print(f"  {DAYS[day]:>5}" + "".join(f"{100 * expect[day][share]:8.1f}" for share in shares))
    print("\nlate share by option and day won (%)")
    for kind in KINDS:
        print(f"  {kind:>14}" + "".join(f"{100 * share:6.1f}" for share in late[kind]))

    if args.write:
        model = {
            "about": "analysis/lean_value.py: what one more order takes from the rest of the week. Cents.",
            "weeks": len(weeks),
            "slotMinutes": SLOT,
            "loadStep": LOAD_STEP,
            "lateStep": LATE_STEP,
            "typicalCents": round(typical),
            "level": round(scale, 4),
            "charge": [[round(c, 1) for c in row] for row in charge],
            "spill": [[round(c, 4) for c in row] for row in spill],
            "cliff": [[round(c, 1) for c in row] for row in price],
            "share": [[round(c, 4) for c in row] for row in expect],
            "late": {kind: [round(c, 4) for c in late[kind]] for kind in KINDS},
        }
        MODEL.write_text(json.dumps(model, indent=2) + "\n")
        print(f"\nwrote {MODEL}")


if __name__ == "__main__":
    main()
