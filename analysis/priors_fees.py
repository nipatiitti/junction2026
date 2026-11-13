"""Exports the priors of the fee models (src/models/fees) from the saved weeks to src/params/fees.json.

    uv run python -m analysis.priors_fees                  # out/spread.sqlite -> src/params/fees.json
    uv run python -m analysis.priors_fees --db other.sqlite --out /tmp/fees.json

Reads the facts tables (analysis/README.md), so build them first: `uv run python -m tools.db && uv run python -m analysis.facts`.
Level 8 only. The hazard comes from the explore weeks (random fees), the rest from dispatch.py's weeks. Every value is a ratio or
a rate: none is keyed to a seed, a dealer, a driver or a place.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import date
from pathlib import Path
from statistics import median

FEE_GRID = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5]  # fee over the typical fee
LEAD_HOURS = [0, 3, 12, 24]  # lower edges of the bands of hours to the last pickup
SHRINK_HOURS = 10.0  # a cell borrows this many open hours from its column's pooled rate
WAKE, SLEEP = 7, 23  # drivers read the app from 07:00 to 23:00
FEW_DRIVERS = 0.5  # "few drivers near the delivery": under this share of the world's median place

# The spells of the explore weeks, whose fee schedules were drawn at random: the only weeks where the fee does not
# follow how hard the gig is (finding 8). dispatch.py's weeks open dear only on hard gigs, so they would read a high
# fee as a slow one.
SPELLS = """
from gig_spells s join week_facts w using (week_id)
where s.level = 8 and w.experiment like 'explore%' and s.source = 'actions' and s.cars = 1 and s.orders = 1
  and s.fee_ratio is not null and s.minutes_to_last_pickup is not null
"""
# Weeks played by dispatch.py at level 8: drops, no-shows, cancellations and lateness at our volume.
RUNS = "w.level = 8 and w.experiment = 'runs' and w.policy = 'dispatch'"


def fee_bin(ratio: float) -> int:
    return min(range(len(FEE_GRID)), key=lambda i: abs(FEE_GRID[i] - ratio))


def lead_bin(minutes: int) -> int:
    """The band of `minutes` to the last pickup; a gig past its last pickup is in the first band."""
    return max((i for i, edge in enumerate(LEAD_HOURS) if minutes >= edge * 60), default=0)


def isotonic(values: list[float], weights: list[float]) -> list[float]:
    """Pool adjacent violators: the closest non-decreasing sequence. A raise never lowers the hazard."""
    blocks: list[list[float]] = []  # [value, weight, count]
    for value, weight in zip(values, weights):
        blocks.append([value, max(weight, 1e-9), 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            v2, w2, n2 = blocks.pop()
            v1, w1, n1 = blocks.pop()
            blocks.append([(v1 * w1 + v2 * w2) / (w1 + w2), w1 + w2, n1 + n2])
    return [round(v, 4) for v, _, n in blocks for _ in range(int(n))]


def hazard(db: sqlite3.Connection) -> dict:
    """Bookings per open daytime hour, by seen, lead band and fee. Weekdays only; nights and weekends are factors."""
    # [seen][lead][fee] -> [bookings, hours]
    cells = [[[[0, 0.0] for _ in FEE_GRID] for _ in LEAD_HOURS] for _ in (0, 1)]
    rows = db.execute(
        f"select order_viewed_before, minutes_to_last_pickup, fee_ratio, day_minutes, booked, end_at {SPELLS}"
        " and s.day < 5"
    ).fetchall()
    for seen, lead, ratio, day_minutes, booked, end_at in rows:
        cell = cells[seen][lead_bin(lead)][fee_bin(ratio)]
        cell[0] += 1 if booked and WAKE <= end_at % 1440 // 60 < SLEEP else 0
        cell[1] += day_minutes / 60
    table = {}
    for seen, name in ((0, "fresh"), (1, "seen")):
        grid = []
        for lead_cells in cells[seen]:
            # A thin cell leans on the rate at its fee over every lead band.
            column = [
                sum(cells[seen][k][f][0] for k in range(len(LEAD_HOURS)))
                / max(1.0, sum(cells[seen][k][f][1] for k in range(len(LEAD_HOURS))))
                for f in range(len(FEE_GRID))
            ]
            rates = [(c[0] + SHRINK_HOURS * column[f]) / (c[1] + SHRINK_HOURS) for f, c in enumerate(lead_cells)]
            grid.append(isotonic(rates, [c[1] + SHRINK_HOURS for c in lead_cells]))
        table[name] = grid
        table[f"{name}Hours"] = [[round(c[1]) for c in lead_cells] for lead_cells in cells[seen]]
    return table


def lookup(table: dict, seen: int, minutes: int, ratio: float) -> float:
    return table["seen" if seen else "fresh"][lead_bin(minutes)][fee_bin(ratio)]


def factors(db: sqlite3.Connection, table: dict) -> dict:
    """Night and weekend: bookings seen over bookings the weekday daytime table expects for the same open hours."""
    night_b = night_e = weekend_b = weekend_e = 0.0
    rows = db.execute(
        f"select order_viewed_before, minutes_to_last_pickup, fee_ratio, minutes, day_minutes, booked, end_at, s.day"
        f" {SPELLS}"
    ).fetchall()
    for seen, lead, ratio, minutes, day_minutes, booked, end_at, day in rows:
        rate = lookup(table, seen, lead, ratio) / 60
        at_night = booked and not WAKE <= end_at % 1440 // 60 < SLEEP
        if day < 5:
            night_b += 1 if at_night else 0
            night_e += rate * (minutes - day_minutes)
        else:
            weekend_b += 1 if booked and not at_night else 0
            weekend_e += rate * day_minutes
    return {
        "night": round(night_b / max(night_e, 1e-9), 3),
        "weekend": round(weekend_b / max(weekend_e, 1e-9), 3),
    }


def extras(db: sqlite3.Connection) -> dict:
    """Booked fee over typical with a feature, over the same without it: single-order gigs of dispatch.py's weeks."""
    medians = {
        week: median(
            near for (near,) in db.execute("select drivers_near from town_days where week_id = ? and day = 0", (week,))
        )
        for (week,) in db.execute(f"select week_id from week_facts w where {RUNS}")
    }
    rows = db.execute(
        f"""select g.week_id, g.fee_ratio, g.private_pickup, g.private_delivery, g.cars = 2, g.premium,
                   o.deadline / 1440 >= 5, g.posted_day = 4, q.drivers_near_delivery
            from gig_facts g join week_facts w using (week_id)
            join order_facts o on o.week_id = g.week_id and o.order_id = g.order_id
            join (select distinct week_id, request_id, drivers_near_delivery from quote_facts) q
              on q.week_id = g.week_id and q.request_id = g.order_id
            where {RUNS} and g.orders = 1 and g.fee_ratio is not null and g.outcome = 'done'"""
    ).fetchall()
    # Each gig: its fee ratio and its seven feature flags, in the order of `names`.
    gigs = [
        (fee, [bool(flag) for flag in flags] + [near is not None and near < FEW_DRIVERS * medians[week]])
        for week, fee, *flags, near in rows
    ]
    names = [
        "privatePickup",
        "privateDelivery",
        "tradeIn",
        "premium",
        "weekendDelivery",
        "postedFriday",
        "fewDriversNear",
    ]
    out = {}
    for k, name in enumerate(names):
        with_ = [fee for fee, flags in gigs if flags[k]]
        without = [fee for fee, flags in gigs if not flags[k]]
        measured = (sum(with_) / len(with_)) / (sum(without) / len(without)) if with_ and without else 1.0
        out[name] = {"start": 1, "measured": round(measured, 3), "gigs": len(with_)}
    return out


def rates(db: sqlite3.Connection) -> dict:
    bookings, drops, no_shows, won, cancelled = db.execute(
        f"select sum(bookings), sum(drops), sum(no_shows), sum(won), sum(cancelled) from week_facts w where {RUNS}"
    ).fetchone()
    return {
        "drop": round(drops / bookings, 4),
        "noShow": round(no_shows / bookings, 4),
        "cancel": round(cancelled / won, 4),
    }


def lateness(db: sqlite3.Connection) -> dict:
    """What a late order costs against an on-time one, as shares of its price, and the fee it ends up paying."""
    rows = db.execute(
        f"""select late_bucket, count(*), avg(-(o.late_refund_cents + o.undelivered_penalty_cents) * 1.0 / price_cents),
                   avg(paid_ratio)
            from order_facts o join week_facts w using (week_id)
            where {RUNS} and o.counted = 1 and late_bucket != 'on_time' group by 1"""
    ).fetchall()
    late = sum(n for _, n, _, _ in rows)
    # An undelivered car also never earns its price: one more price lost.
    share = sum(n * (cost + (1 if bucket == "undelivered" else 0)) for bucket, n, cost, _ in rows) / late
    paid = [(n, ratio) for _, n, _, ratio in rows if ratio is not None]
    on_time, counted = db.execute(f"select sum(on_time), sum(counted) from week_facts w where {RUNS}").fetchone()
    return {
        "costShare": round(share, 3),
        "feeRatio": round(sum(n * r for n, r in paid) / sum(n for n, _ in paid), 3),
        "lateShare": round(1 - on_time / counted, 4),
        "orders": late,
    }


def probe(db: sqlite3.Connection) -> dict:
    flips = sorted(r for (r,) in db.execute("select flip_ratio from fee_probes where flip_ratio is not null"))
    if not flips:
        return {"probes": 0}
    at = lambda q: round(flips[min(len(flips) - 1, int(q * len(flips)))], 3)
    return {"probes": len(flips), "p10": at(0.1), "p50": at(0.5), "p90": at(0.9)}


def compact(text: str) -> str:
    """Puts each list of numbers on one line, as Biome formats JSON."""
    return re.sub(
        r"\[\s*([-\d.,\s]+?)\s*\]", lambda m: "[" + ", ".join(m.group(1).replace(",", " ").split()) + "]", text
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", default="out/spread.sqlite")
    parser.add_argument("--out", default="src/params/fees.json")
    args = parser.parse_args()
    db = sqlite3.connect(args.db)
    table = hazard(db)
    weeks = db.execute(f"select count(*) from week_facts w where {RUNS}").fetchone()[0]
    priors = {
        "about": f"Fee model priors from {args.db} on {date.today()}: uv run python -m analysis.priors_fees",
        "weeks": weeks,
        "hazard": {
            "feeGrid": FEE_GRID,
            "leadHours": LEAD_HOURS,
            "fresh": table["fresh"],
            "seen": table["seen"],
            "openHours": {"fresh": table["freshHours"], "seen": table["seenHours"]},
            **factors(db, table),
        },
        "extras": extras(db),
        "rates": rates(db),
        "late": lateness(db),
        # RULES.md: the share of the price a late order gives back, by how late; an undelivered car loses its price
        # and pays twice it.
        "refunds": {"twoHours": 0.1, "oneDay": 0.25, "twoBusinessDays": 0.5, "beyond": 1.0, "undelivered": 3.0},
        "probe": probe(db),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(compact(json.dumps(priors, indent=2)) + "\n")
    print(f"wrote {args.out}: {weeks} dispatch.py weeks")
    print(json.dumps({k: priors[k] for k in ("extras", "rates", "late", "probe")}, indent=1))
    print("night", priors["hazard"]["night"], "weekend", priors["hazard"]["weekend"])
    for name in ("fresh", "seen"):
        for lead, row in zip(LEAD_HOURS, table[name]):
            print(f"{name:5} {lead:>2}h", " ".join(f"{v:5.2f}" for v in row))


if __name__ == "__main__":
    main()
