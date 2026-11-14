"""Fits the lane priors of `PriorPricing` on the saved weeks: how much more, or less, than the world's level a dealer
accepts for a car from each pickup place and to each delivery place.

    uv run python -m tools.db                     # the saved weeks -> out/spread.sqlite
    uv run python -m strategies.lane_prior.fit    # writes strategies/lane_prior/priors.json and prints the fit

Every quote of every saved level 8 week is one row: the price over the list price, whether it won, and the dealer's
trust then, counted from the account as pricing counts it. The model is a logistic curve on the log price,

    P(win) = 1 / (1 + exp(-slope x (level[week, day] + pickup[place] + delivery[place] + log(1 + trust) - log(price))))

with one level for each day of each week, so the world's price level, its day factors and the price war stay out of
the places' offsets. The offsets are shrunk towards zero (a ridge penalty) and centred, so they move no price on
average. README.md next to this file explains how pricing uses them and what `--split` shows.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

DAY = 24 * 60
TRUST_CAP = 25
SKIP = ("passive", "starter", "ts-starter")  # they quote nothing, or the list price only
DECLINE = 3.0  # a quote above this multiple of the list price is a decline, not a price
OUT = Path(__file__).with_name("priors.json")


def rows(db: sqlite3.Connection, level: int) -> list[tuple]:
    """One row for each priced quote: (week, day, pickup, delivery, log price over list less log trust, won, seed)."""
    marks = ",".join("?" * len(SKIP))
    out = []
    for week, seed in db.execute(
        f"select id, seed from weeks where level = ? and policy not in ({marks})", [level, *SKIP]
    ):
        dealer_of = dict(db.execute("select id, dealer_id from orders where week_id = ?", (week,)))
        lines = db.execute(
            "select at, kind, order_id from ledger where week_id = ? and order_id is not null "
            "and kind in ('revenue', 'late_refund', 'undelivered_penalty') order by at, seq",
            (week,),
        ).fetchall()
        places = {
            r[0]: r[1:]
            for r in db.execute(
                "select request_id, pickup_place, delivery_place from legs where week_id = ? and leg = 0", (week,)
            )
        }
        quotes: dict[str, tuple[float, int]] = {}
        for request_id, listed, quote, taken in db.execute(
            "select request_id, list_price_cents, quote_cents, taken from options where week_id = ? and quote_cents is not null",
            (week,),
        ):
            if quote <= DECLINE * listed and (request_id not in quotes or taken):
                quotes[request_id] = (math.log(quote / listed), int(bool(taken)))
        trust: dict[str, int] = defaultdict(int)
        unsettled: dict[str, int] = {}
        late: set[str] = set()
        i = 0
        for request_id, dealer, arrived in db.execute(
            "select id, dealer_id, arrived_at from requests where week_id = ? order by arrived_at", (week,)
        ):
            while i < len(lines) and lines[i][0] < arrived:  # the account up to this request, as pricing reads it
                at, kind, order_id = lines[i]
                i += 1
                for other, since in list(unsettled.items()):
                    if since < at:
                        del unsettled[other]
                        trust[dealer_of.get(other, "")] = min(TRUST_CAP, trust[dealer_of.get(other, "")] + 1)
                if kind == "revenue":
                    unsettled[order_id] = at
                elif order_id not in late:
                    late.add(order_id)
                    unsettled.pop(order_id, None)
                    trust[dealer_of.get(order_id, "")] //= 2
            if request_id in quotes and request_id in places:
                counted = trust[dealer] + sum(
                    1 for o, since in unsettled.items() if dealer_of.get(o) == dealer and since < arrived
                )
                x, won = quotes[request_id]
                pickup, delivery = places[request_id]
                out.append(
                    (week, arrived // DAY, pickup, delivery, x - math.log(1 + min(TRUST_CAP, counted) / 100), won, seed)
                )
    return out


def fit(data: list[tuple], ridge: float, rounds: int = 60) -> dict:
    """The slope and the offsets, by damped Newton steps on each group of terms in turn."""
    level: dict[tuple, float] = defaultdict(lambda: math.log(1.4))
    pickup: dict[str, float] = defaultdict(float)
    delivery: dict[str, float] = defaultdict(float)
    slope = 8.0
    for _ in range(rounds):
        grad: dict[tuple, float] = defaultdict(float)
        curve: dict[tuple, float] = defaultdict(float)
        slope_grad = slope_curve = 0.0
        for week, day, a, b, x, won, _ in data:
            s = level[week, day] + pickup[a] + delivery[b] - x
            p = 1 / (1 + math.exp(-max(-30.0, min(30.0, slope * s))))
            g, h = (won - p) * slope, p * (1 - p) * slope * slope
            for key in (("level", week, day), ("pickup", a), ("delivery", b)):
                grad[key] += g
                curve[key] += h
            slope_grad += (won - p) * s
            slope_curve += p * (1 - p) * s * s
        for key, g in grad.items():
            if key[0] == "level":
                level[key[1:]] += 0.5 * g / (curve[key] + 1e-6)
            else:
                terms = pickup if key[0] == "pickup" else delivery
                terms[key[1]] += 0.5 * (g - ridge * terms[key[1]]) / (curve[key] + ridge)
        slope = max(1.0, slope + 0.5 * slope_grad / (slope_curve + 1e-6))
    for terms in (pickup, delivery):  # centred, so the offsets move no price on average
        mean = sum(terms.values()) / max(1, len(terms))
        for key in terms:
            terms[key] -= mean
    return {"slope": slope, "pickup": dict(pickup), "delivery": dict(delivery)}


def correlation(a: dict[str, float], b: dict[str, float]) -> float:
    keys = sorted(set(a) & set(b))
    if len(keys) < 3:
        return float("nan")
    ma, mb = sum(a[k] for k in keys) / len(keys), sum(b[k] for k in keys) / len(keys)
    cov = sum((a[k] - ma) * (b[k] - mb) for k in keys)
    return cov / math.sqrt(sum((a[k] - ma) ** 2 for k in keys) * sum((b[k] - mb) ** 2 for k in keys) or 1.0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fits the lane priors on the saved weeks.")
    parser.add_argument("--db", default="out/spread.sqlite")
    parser.add_argument("--level", type=int, default=8)
    parser.add_argument("--ridge", type=float, default=400.0, help="the penalty that shrinks the offsets to zero")
    parser.add_argument("--split", action="store_true", help="fit two halves of the seeds apart and compare them")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    data = rows(sqlite3.connect(args.db), args.level)
    seeds = sorted({r[6] for r in data})
    print(
        f"{len(data)} quotes of {len({r[0] for r in data})} weeks on {len(seeds)} seeds, {sum(r[5] for r in data)} won"
    )
    if args.split:
        halves = [fit([r for r in data if (seeds.index(r[6]) % 2 == half)], args.ridge) for half in (0, 1)]
        for side in ("pickup", "delivery"):
            print(f"{side}: correlation of the two halves' offsets {correlation(halves[0][side], halves[1][side]):.2f}")
        return
    result = fit(data, args.ridge)
    counts: dict[tuple, int] = defaultdict(int)
    for _, _, a, b, *_ in data:
        counts["pickup", a] += 1
        counts["delivery", b] += 1
    print(
        f"slope {result['slope']:.1f}: a price 1% higher loses about {result['slope'] / 4:.1f} points of win share at 50%"
    )
    for side in ("pickup", "delivery"):
        print(
            side
            + ": "
            + ", ".join(
                f"{k} {v:+.3f} ({counts[side, k]})" for k, v in sorted(result[side].items(), key=lambda kv: kv[1])
            )
        )
    out = {
        "weeks": len({r[0] for r in data}),
        "quotes": len(data),
        "slope": round(result["slope"], 2),
        "pickup": {k: round(v, 4) for k, v in sorted(result["pickup"].items())},
        "delivery": {k: round(v, 4) for k, v in sorted(result["delivery"].items())},
    }
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
