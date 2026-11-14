"""The supply and demand functions of `lean`, fitted on saved server weeks of the same seeds at different volumes.

Reads the weeks of `data/scrape/runs/L8/<prefix>*` that `lean` played with `noise` 0.11 and a fixed `tax` (so only
the volume differs between the weeks of a seed), and fits, with one level per seed:

- the fee paid × typical, the refunds per order and the late share against the load (orders won per driver);
- the price × list against the share of the requests won (the demand's logistic scale).

It prints what one more order costs the other orders, as euros per unit of load and as a share of the mean order's
cost: the `taxLoad` of `src/strategies/lean/index.ts`. Plays nothing.

    uv run python -m analysis.supply_curve
"""

import argparse
import collections
import glob
import gzip
import json
import math
import os
import statistics as st


def week(folder: str) -> dict | None:
    """One saved week as the numbers the fit needs, or None when it is not a `lean` week of the experiment."""
    with open(f"{folder}/meta.json") as file:
        meta = json.load(file)
    params = (meta.get("settings") or {}).get("params") or {}
    if meta.get("policy") != "ts-lean" or params.get("noise") != 0.11:
        return None
    if params.get("taxEuros") or params.get("taxLoad"):
        return None
    with gzip.open(f"{folder}/events.jsonl.gz", "rt") as file:
        events = [json.loads(line) for line in file]
    with gzip.open(f"{folder}/drivers.json.gz") as file:
        drivers = json.load(file)
    typical, lists, won, requests = {}, {}, {}, 0
    for event in events:
        if event["kind"] == "price_request":
            request = event["request"]
            requests += 1
            typical[request["id"]] = request["referenceFeeCents"]
            lists[request["id"]] = {o["kind"]: o["listPriceCents"] for o in request["options"]}
        elif event["kind"] == "order_won":
            won[event["order"]["id"]] = event["order"]
    cars, fee = collections.defaultdict(set), {}
    for event in events:
        if event["kind"] == "picked_up":
            cars[event["gigId"]].add(event["orderId"])
        elif event["kind"] == "gig_booked":
            fee[event["gigId"]] = event["feeCents"]
    refunds = [e["line"] for e in events if e["kind"] == "ledger" and e["line"]["kind"] == "late_refund"]
    paid = sum(fee[gig] for gig in cars)
    moved = sum(typical[order] for orders in cars.values() for order in orders)
    return {
        "seed": meta["seed"],
        "tax": params.get("tax", 0),
        "load": len(won) / len(drivers if isinstance(drivers, list) else drivers["drivers"]),
        "share": len(won) / requests,
        "fee": paid / moved,
        "typical": moved / sum(len(orders) for orders in cars.values()) / 100,
        "late": len({line["orderId"] for line in refunds}) / len(won),
        "refund": -sum(line["cents"] for line in refunds) / 100 / len(won),
        "price": st.mean(order["priceCents"] / lists[id][order["option"]] for id, order in won.items()),
    }


def slope(weeks: list[dict], y, x) -> tuple[float, float, float]:
    """The slope of y on x with one level per seed, its standard error and the share of the variance explained."""
    by_seed = collections.defaultdict(list)
    for w in weeks:
        by_seed[w["seed"]].append(w)
    xs, ys = [], []
    for group in by_seed.values():
        if len(group) < 2:
            continue
        mx, my = st.mean(x(w) for w in group), st.mean(y(w) for w in group)
        xs += [x(w) - mx for w in group]
        ys += [y(w) - my for w in group]
    sxx = sum(a * a for a in xs)
    b = sum(a * c for a, c in zip(xs, ys)) / sxx
    rest = sum((c - b * a) ** 2 for a, c in zip(xs, ys))
    freedom = len(xs) - len(by_seed) - 1
    return b, math.sqrt(rest / freedom / sxx), 1 - rest / sum(c * c for c in ys)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", default="data/scrape/runs/L8", help="the folder of the saved weeks")
    parser.add_argument("--prefix", default="supply-", help="the seeds of the experiment start with this")
    args = parser.parse_args()
    folders = [os.path.dirname(m) for m in glob.glob(f"{args.runs}/{args.prefix}*/*/meta.json")]
    weeks = [w for w in map(week, sorted(folders)) if w]
    seeds = {w["seed"] for w in weeks}
    print(
        f"{len(weeks)} weeks of {len(seeds)} seeds, load {min(w['load'] for w in weeks):.2f} to "
        f"{max(w['load'] for w in weeks):.2f} orders per driver"
    )
    load = lambda w: w["load"]
    fee = slope(weeks, lambda w: w["fee"], load)
    refund = slope(weeks, lambda w: w["refund"], load)
    late = slope(weeks, lambda w: w["late"], load)
    scale = slope(weeks, lambda w: math.log(w["price"]), lambda w: math.log(w["share"] / (1 - w["share"])))
    print(f"fee paid x typical, per order per driver:   {fee[0]:+.3f} ± {fee[1]:.3f} (R2 {fee[2]:.2f})")
    print(f"refunds per order, per order per driver:    {refund[0]:+.2f} ± {refund[1]:.2f} euros (R2 {refund[2]:.2f})")
    print(f"late share, per order per driver:           {late[0]:+.3f} ± {late[1]:.3f} (R2 {late[2]:.2f})")
    print(f"demand's logistic scale in log price:       {-scale[0]:.3f} ± {scale[1]:.3f} (R2 {scale[2]:.2f})")
    typical = st.mean(w["typical"] for w in weeks)
    cost = st.mean(w["typical"] * w["fee"] for w in weeks)
    euros = typical * fee[0] + refund[0]
    print(f"mean typical fee {typical:.1f} euros, mean cost {cost:.1f} euros an order")
    print(f"one more order costs the others {euros:.1f} euros x orders per driver: taxLoad {euros / cost:.2f}")


if __name__ == "__main__":
    main()
