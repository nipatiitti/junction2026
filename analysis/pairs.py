"""How many of our won orders could one driver have carried in one gig of two cars?

Standard library only. Run with:
    uv run --no-project --python 3.13 python analysis/pairs.py

Reads the saved ts-bidprice weeks of spread-6, -7, -8 and -10 at level 8 and, for each world, counts greedy pairs of
one-car orders (an order is used once):
  round_trip: A from X to Y, then B from within d km of Y to within d km of X;
  chain:      B's pickup within d km of A's delivery, any destination;
  same_yard:  A and B picked up at the same place on the same day, deliveries within d km of each other. One driver
              drives one car, so the gig is pick A, deliver A, drive back to the yard, pick B, deliver B.
Timing (all from the map's road minutes, opening hours ignored): the driver starts A inside its pickup window, delivers
it by its deadline, drives to B's pickup, waits at most MAX_WAIT minutes for B's window to open, and delivers B by its
deadline. RULES "Gigs": a gig with more than one car may plan at most 12 hours of driving, the drive between the cars
included. Pair kinds are counted independently (each kind's greedy matching on its own); `any` matches all kinds
together, round trips first. `+lost` adds the requests we lost or declined as possible second cars for won orders
left unpaired.
"""

import gzip
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "data/scrape/runs/L8"
SEEDS = ("spread-6", "spread-7", "spread-8", "spread-10")
DISTANCES = (15, 40)
MAX_WAIT = 180
MAX_DRIVE = 720


def load_map():
    m = json.loads((ROOT / "data/scrape/runs/map.json").read_text())
    km = {(r["from"], r["to"]): r["km"] for r in m["roads"]}
    mins = {(r["from"], r["to"]): r["minutes"] for r in m["roads"]}
    return km, mins


KM, MINS = load_map()


def near(a, b, d):
    return a == b or KM.get((a, b), math.inf) <= d


def gap(a, b):
    return 0 if a == b else MINS.get((a, b), math.inf)


def leg_of(legs, deadline):
    if len(legs) != 1:
        return None
    leg = legs[0]
    p, q = leg["pickup"], leg["delivery"]
    return {
        "from": p["placeId"],
        "to": q["placeId"],
        "pf": p["window"]["from"],
        "pt": p["window"]["to"],
        "dt": min(q["window"]["to"], deadline),
    }


def feasible(a, b):
    """A then B by one driver: returns planned driving minutes or None."""
    ma, mb, g = gap(a["from"], a["to"]), gap(b["from"], b["to"]), gap(a["to"], b["from"])
    if ma + g + mb > MAX_DRIVE:
        return None
    # start A as late as its window allows so the driver waits least for B
    s = min(a["pt"], a["dt"] - ma, b["pt"] - ma - g, b["dt"] - mb - ma - g)
    if s < a["pf"]:
        return None
    arrive = s + ma + g
    if b["pf"] - arrive > MAX_WAIT:
        return None
    return ma + g + mb


def kind_ok(kind, a, b, d):
    if kind == "round_trip":
        return a["to"] != a["from"] and near(a["to"], b["from"], d) and near(b["to"], a["from"], d)
    if kind == "chain":
        return near(a["to"], b["from"], d)
    if kind == "same_yard":
        return a["from"] == b["from"] and near(a["to"], b["to"], d) and abs(a["pf"] - b["pf"]) < 1440
    raise ValueError(kind)


def candidates(won, kind, d, others=None):
    out = []
    pool = others if others is not None else won
    for i, a in enumerate(won):
        for j, b in enumerate(pool):
            if others is None and i == j:
                continue
            if kind_ok(kind, a, b, d) and (drive := feasible(a, b)) is not None:
                out.append((KM.get((a["to"], b["from"]), 0) if a["to"] != b["from"] else 0, drive, i, j))
            if others is not None and kind_ok(kind, b, a, d) and (drive := feasible(b, a)) is not None:
                out.append((KM.get((b["to"], a["from"]), 0) if b["to"] != a["from"] else 0, drive, i, j))
    out.sort()
    return out


def greedy(cands, used_a, used_b, same_pool):
    pairs = []
    for _, _, i, j in cands:
        if i in used_a or (j in used_a if same_pool else j in used_b):
            continue
        used_a.add(i)
        (used_a if same_pool else used_b).add(j)
        pairs.append((i, j))
    return pairs


def load_world(folder):
    won, requests, fee_by_gig, order_by_gig = {}, {}, {}, {}
    with gzip.open(folder / "events.jsonl.gz", "rt") as f:
        for line in f:
            e = json.loads(line)
            k = e["kind"]
            if k == "price_request":
                requests[e["request"]["id"]] = e["request"]
            elif k == "order_won":
                won[e["order"]["id"]] = e["order"]
            elif k == "gig_booked":
                fee_by_gig[e["gigId"]] = e["feeCents"]
            elif k == "picked_up":
                order_by_gig[e["gigId"]] = e["orderId"]
    reveal = json.loads(gzip.open(folder / "reveal.json.gz").read())
    lost_ids = {r["request"]["id"] for r in reveal["requests"] if r.get("outcome") != "won"}
    fees = {}
    for g, o in order_by_gig.items():
        fees[o] = fees.get(o, 0) + fee_by_gig.get(g, 0)
    legs = []
    for oid, o in won.items():
        leg = leg_of(o["legs"], o["deadline"])
        if leg:
            req = requests.get(oid, {})
            leg.update(id=oid, typical=req.get("referenceFeeCents", 0), fee=fees.get(oid, 0))
            legs.append(leg)
    lost = []
    for rid in lost_ids:
        r = requests.get(rid)
        if not r:
            continue
        leg = leg_of(r["legs"], max(o["deadline"] for o in r["options"]))
        if leg:
            leg.update(id=rid, typical=r["referenceFeeCents"])
            lost.append(leg)
    return len(won), legs, lost


def analyse(folder):
    n_orders, legs, lost = load_world(folder)
    row = {"world": folder.name, "orders": n_orders, "oneCar": len(legs)}
    for d in DISTANCES:
        for kind in ("round_trip", "chain", "same_yard"):
            row[f"{kind}@{d}"] = len(greedy(candidates(legs, kind, d), set(), set(), True))
        used = set()
        paired = []
        for kind in ("round_trip", "chain", "same_yard"):
            paired += greedy(candidates(legs, kind, d), used, set(), True)
        row[f"any@{d}"] = len(paired)
        row[f"typicalInPairs@{d}"] = sum(legs[i]["typical"] + legs[j]["typical"] for i, j in paired)
        row[f"feesInPairs@{d}"] = sum(legs[i]["fee"] + legs[j]["fee"] for i, j in paired)
        rest = [x for k, x in enumerate(legs) if k not in used]
        extra_used, lost_used = set(), set()
        extra = []
        for kind in ("round_trip", "chain"):
            extra += greedy(candidates(rest, kind, d, lost), extra_used, lost_used, False)
        row[f"+lost@{d}"] = len(extra)
    return row


def main():
    rows = []
    for seed in SEEDS:
        for folder in sorted((RUNS / seed).iterdir()):
            meta = folder / "meta.json"
            if not meta.exists() or json.loads(meta.read_text()).get("policy") != "ts-bidprice":
                continue
            if not (folder / "reveal.json.gz").exists():
                continue
            row = analyse(folder)
            row["seed"] = seed
            rows.append(row)
    keys = ["orders", "oneCar"] + [
        f"{k}@{d}" for d in DISTANCES for k in ("round_trip", "chain", "same_yard", "any", "+lost")
    ]
    print("seed       worlds " + " ".join(f"{k:>14}" for k in keys))
    for seed in SEEDS:
        sr = [r for r in rows if r["seed"] == seed]
        if not sr:
            continue
        avg = {k: sum(r[k] for r in sr) / len(sr) for k in keys}
        print(f"{seed:10} {len(sr):6} " + " ".join(f"{avg[k]:14.1f}" for k in keys))
    print()
    for d in DISTANCES:
        orders = sum(r["orders"] for r in rows) / len(rows)
        pairs = sum(r[f"any@{d}"] for r in rows) / len(rows)
        typ = sum(r[f"typicalInPairs@{d}"] for r in rows) / len(rows) / 100
        fees = sum(r[f"feesInPairs@{d}"] for r in rows) / len(rows) / 100
        extra = sum(r[f"+lost@{d}"] for r in rows) / len(rows)
        print(
            f"d={d} km: {pairs:.1f} pairs/week = {2 * pairs:.1f} orders in pairs, "
            f"{2 * pairs / orders:.1%} of {orders:.0f} orders; typical fees in pairs EUR {typ:.0f}, "
            f"paid EUR {fees:.0f}; +{extra:.1f} pairs with a lost/declined request"
        )
    out = ROOT / "out/pairs.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
