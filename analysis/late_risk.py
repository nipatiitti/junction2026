"""Late-risk table: for every won order in the saved level-8 weeks, features known at quote time (slack between the
win and the latest safe pickup, drivers living near the pickup, evening win) and the outcome (late or never
delivered, order margin). Fits a smoothed late-share table slack bucket x pickup supply x evening, ranks held-out
seeds with it (one seed out at a time), and writes the table fitted on all seeds to src/params/late.json.
Usage: uv run python -m analysis.late_risk [policy prefix ...]  (default: ts-bidprice ts-recall)"""

import gzip
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "data" / "scrape" / "runs"
SEEDS = ["spread-1", "spread-2", "spread-3", "spread-4", "spread-5", "spread-9"]
SLACK_EDGES = [6, 12, 24]  # hours: buckets <6, 6-12, 12-24, >=24
NEAR_KM = 100
FEW = 8  # drivers within NEAR_KM of the pickup at or below which a pickup counts as remote
EVENING = (18, 21)  # win hour range [from, to)
PRIOR_N = 10  # pseudo orders at the base rate per cell


def dist(a, b):
    r = math.pi / 180
    h = (
        math.sin((b["lat"] - a["lat"]) * r / 2) ** 2
        + math.cos(a["lat"] * r) * math.cos(b["lat"] * r) * math.sin((b["lon"] - a["lon"]) * r / 2) ** 2
    )
    return 2 * 6371 * math.asin(math.sqrt(h))


MAP = json.loads((RUNS / "map.json").read_text())
PLACES = {p["id"]: p for p in MAP["places"]}
ROADS = {(r["from"], r["to"]): r["minutes"] for r in MAP["roads"]}


def minutes(a, b):
    return 0 if a == b else ROADS.get((a, b), math.inf)


def drive(legs):
    total, here = 0, None
    for leg in legs:
        if here is not None:
            total += minutes(here, leg["pickup"]["placeId"])
        total += minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"])
        here = leg["delivery"]["placeId"]
    return total


def near(roster):
    homes = defaultdict(int)
    for d in roster:
        homes[d["homePlaceId"]] += 1
    return {
        p: sum(n for h, n in homes.items() if h in PLACES and dist(PLACES[p], PLACES[h]) <= NEAR_KM) for p in PLACES
    }


def cell(slack_h, near_pickup, hour):
    s = sum(slack_h >= e for e in SLACK_EDGES)
    return f"s{s}/{'few' if near_pickup <= FEW else 'many'}/{'eve' if EVENING[0] <= hour < EVENING[1] else 'day'}"


def rows(prefixes):
    out = []
    for seed in SEEDS:
        for world in sorted((RUNS / "L8" / seed).glob("*")):
            meta_p = world / "meta.json"
            if not (world / "events.jsonl.gz").exists() or not meta_p.exists():
                continue
            meta = json.loads(meta_p.read_text())
            if prefixes and not any(str(meta.get("policy", "")).startswith(p) for p in prefixes):
                continue
            roster = json.loads(gzip.open(world / "drivers.json.gz").read())
            nr = near(roster)
            orders, money = {}, defaultdict(int)
            for line in gzip.open(world / "events.jsonl.gz", "rt"):
                if not line.strip():
                    continue
                e = json.loads(line)
                k = e["kind"]
                if k == "order_won":
                    o = e["order"]
                    orders[o["id"]] = {"o": o, "won": e["at"], "left": len(o["legs"]), "done": None}
                elif k == "order_changed" and e.get("order") and e["order"]["id"] in orders:
                    orders[e["order"]["id"]]["o"]["deadline"] = e["order"]["deadline"]
                elif k == "order_cancelled":
                    orders.pop(e.get("orderId"), None)
                elif k == "delivered" and e.get("orderId") in orders:
                    x = orders[e["orderId"]]
                    x["left"] -= 1
                    if x["left"] == 0:
                        x["done"] = e["at"]
                elif k == "ledger" and (e.get("line") or {}).get("orderId"):
                    money[e["line"]["orderId"]] += e["line"]["cents"]
            for oid, x in orders.items():
                o, legs = x["o"], x["o"]["legs"]
                slack = (o["deadline"] - drive(legs) - x["won"]) / 60
                out.append(
                    {
                        "seed": seed,
                        "option": o["option"],
                        "slack": slack,
                        "hour": (x["won"] % 1440) // 60,
                        "nearPickup": nr.get(legs[0]["pickup"]["placeId"], 0),
                        "nearDelivery": nr.get(legs[-1]["delivery"]["placeId"], 0),
                        "premium": any(leg["car"]["premium"] for leg in legs),
                        "private": any(
                            leg["pickup"]["privateAddress"] or leg["delivery"]["privateAddress"] for leg in legs
                        ),
                        "late": x["done"] is None or x["done"] > o["deadline"],
                        "margin": money.get(oid, 0),
                    }
                )
    return out


def fit(rs):
    base = sum(r["late"] for r in rs) / max(1, len(rs))
    n, late = defaultdict(int), defaultdict(int)
    for r in rs:
        c = cell(r["slack"], r["nearPickup"], r["hour"])
        n[c] += 1
        late[c] += r["late"]
    return base, {c: (late[c] + PRIOR_N * base) / (n[c] + PRIOR_N) for c in n}, n


def risk(table, base, r):
    return table[1].get(cell(r["slack"], r["nearPickup"], r["hour"]), base) if isinstance(table, tuple) else 0


def main():
    prefixes = sys.argv[1:] or ["ts-bidprice", "ts-recall"]
    rs = rows(prefixes)
    print(f"{len(rs)} won orders, policies {prefixes}")
    for seed in SEEDS:
        test = [r for r in rs if r["seed"] == seed]
        train = [r for r in rs if r["seed"] != seed]
        if not test or not train:
            continue
        base, table, _ = fit(train)
        test.sort(key=lambda r: -table.get(cell(r["slack"], r["nearPickup"], r["hour"]), base))
        rate = sum(r["late"] for r in test) / len(test)
        parts = [f"{seed}: n={len(test)} base {rate:.1%}"]
        for q in (0.1, 0.2):
            top = test[: max(1, int(len(test) * q))]
            parts.append(
                f"top{int(q * 100)}% late {sum(r['late'] for r in top) / len(top):.1%}"
                f" margin {sum(r['margin'] for r in top) / len(top) / 100:.1f}EUR"
            )
        parts.append(f"all margin {sum(r['margin'] for r in test) / len(test) / 100:.1f}EUR")
        print("  " + ", ".join(parts))
    base, table, n = fit(rs)
    print(f"table on all seeds (base {base:.1%}):")
    for c in sorted(table, key=lambda c: -table[c]):
        print(f"  {c}: p={table[c]:.2f} n={n[c]}")
    for t in (0.1, 0.15, 0.2, 0.4, 0.6):
        hit = [r for r in rs if table.get(cell(r["slack"], r["nearPickup"], r["hour"]), base) >= t]
        if hit:
            print(
                f"  lateRiskMax {t}: declines {len(hit) / len(rs):.1%} of orders, late {sum(r['late'] for r in hit) / len(hit):.1%},"
                f" mean margin {sum(r['margin'] for r in hit) / len(hit) / 100:.1f}EUR"
            )
    out = {
        "slackEdgesHours": SLACK_EDGES,
        "nearKm": NEAR_KM,
        "fewDrivers": FEW,
        "eveningHours": list(EVENING),
        "base": round(base, 4),
        "cells": {c: round(p, 4) for c, p in sorted(table.items())},
    }
    (ROOT / "src" / "params" / "late.json").write_text(json.dumps(out, indent=2) + "\n")


if __name__ == "__main__":
    main()
