"""Measures the driver cost of the saved weeks by lead time, the table that `LeadCostAdmission` reads.

    uv run python -m tools.db                    # the saved weeks -> out/spread.sqlite
    uv run python -m strategies.lead_cost.fit    # prints the table; --policy to choose whose weeks

For each delivered order that went alone (no bundle), the cost is every account line of the order but its revenue:
driver fees, failed visits, waiting, release fees and late refunds. The table gives that cost over the request's
typical fee, by the hours from the first post to the order's `lastPickupAt` and to the car's ready time, and what a
private address adds. README.md next to this file explains how admission uses it.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict

HOUR = 60
POLICIES = "ceiling,scarcity-ceiling,scarcity-cost,delivery-urgency,price-ladder"
LAST_PICKUP = (8, 14, 24, 36, 60)  # the upper ends of the classes, in hours; the last class is open
READY = (3, 8)


def band(hours: float, ends: tuple[int, ...]) -> int:
    return next((i for i, end in enumerate(ends) if hours < end), len(ends))


def orders(db: sqlite3.Connection, policies: list[str], level: int) -> list[dict]:
    """One row for each delivered order that had no bundle: its cost, typical fee, lead times and addresses."""
    marks = ",".join("?" * len(policies))
    weeks = [
        w for (w,) in db.execute(f"select id from weeks where level = ? and policy in ({marks})", [level, *policies])
    ]
    rows = []
    for week in weeks:
        typical = dict(db.execute("select id, reference_fee_cents from requests where week_id = ?", (week,)))
        first = {
            r[0]: r[1:]
            for r in db.execute(
                "select request_id, pickup_from, pickup_private, delivery_private from legs where week_id = ? and leg = 0",
                (week,),
            )
        }
        cost: dict[str, int] = defaultdict(int)
        for order_id, cents in db.execute(
            "select order_id, cents from ledger where week_id = ? and order_id is not null and kind != 'revenue'",
            (week,),
        ):
            cost[order_id] -= cents
        posted: dict[str, int] = {}
        bundled: set[str] = set()
        for stops, at in db.execute("select stops, posted_at from gigs where week_id = ? order by posted_at", (week,)):
            ids = list(dict.fromkeys(stop["orderId"] for stop in json.loads(stops)))
            for order_id in ids:
                posted.setdefault(order_id, at)
            if len(ids) > 1:
                bundled.update(ids)
        for order_id, price, last_pickup_at in db.execute(
            "select id, price_cents, last_pickup_at from orders where week_id = ? and status = 'delivered'", (week,)
        ):
            if order_id in bundled or order_id not in posted or order_id not in first or not typical.get(order_id):
                continue
            ready, pickup_private, delivery_private = first[order_id]
            rows.append(
                {
                    "cost": cost[order_id],
                    "typical": typical[order_id],
                    "price": price,
                    "last": (last_pickup_at - posted[order_id]) / HOUR,
                    "ready": (ready - posted[order_id]) / HOUR,
                    "address": "pickup" if pickup_private else "delivery" if delivery_private else "dealer",
                }
            )
    return rows


def ratio(rows: list[dict]) -> float:
    return sum(r["cost"] for r in rows) / sum(r["typical"] for r in rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="The driver cost of the saved weeks, by lead time.")
    parser.add_argument("--db", default="out/spread.sqlite")
    parser.add_argument("--policy", default=POLICIES, help="the policies whose weeks count, comma-separated")
    parser.add_argument("--level", type=int, default=8)
    args = parser.parse_args()
    rows = orders(sqlite3.connect(args.db), args.policy.split(","), args.level)
    print(f"{len(rows)} orders, cost over the typical fee {ratio(rows):.2f}")
    cells: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for r in (r for r in rows if r["address"] == "dealer"):
        cells[band(r["last"], LAST_PICKUP), band(r["ready"], READY)].append(r)
    lasts = [f"<{e}h" for e in LAST_PICKUP] + [f"{LAST_PICKUP[-1]}h+"]
    readies = [f"ready <{e}h" for e in READY] + [f"ready {READY[-1]}h+"]
    print("Dealer sites: cost over the typical fee (orders), by hours to the last pickup and to the ready time")
    print(f"{'':>8}" + "".join(f"{name:>20}" for name in readies))
    for i, name in enumerate(lasts):
        line = f"{name:>8}"
        for j in range(len(readies)):
            cell = cells.get((i, j), [])
            line += f"{f'{ratio(cell):.2f} ({len(cell)})' if len(cell) >= 5 else '-':>20}"
        print(line)
    print("A private address: its cost over a dealer site's in the same cell, by hours to the ready time")
    for address in ("pickup", "delivery"):
        line = f"{address:>8}"
        for j in range(len(readies)):
            own = [r for r in rows if r["address"] == address and band(r["ready"], READY) == j]
            expected = sum(
                r["typical"] * ratio(cells[band(r["last"], LAST_PICKUP), j])
                for r in own
                if cells.get((band(r["last"], LAST_PICKUP), j))
            )
            line += f"{f'{sum(r["cost"] for r in own) / expected:.2f} ({len(own)})' if expected and len(own) >= 5 else '-':>20}"
        print(line)


if __name__ == "__main__":
    main()
