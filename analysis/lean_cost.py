"""Refits the cost weights of lean's order model (`src/strategies/lean/order.json`) on the saved server weeks of
lean's current defaults: what each won order paid its driver over its typical fee, against what the desk saw at the
quote. Prints the weights next to the old ones and what both predict for some groups; `--write` saves them to both
copies of order.json. The chance to be late is not refitted.

    uv run --with numpy python -m analysis.lean_cost
"""

from __future__ import annotations

import collections
import glob
import gzip
import json
import math
import sys
from pathlib import Path

import numpy as np

DAY = 1440
LEVEL = 0.92
MODELS = ["src/strategies/lean/order.json", "strategies/lean/order.json"]


def current(params: dict) -> bool:
    """Whether a week was played with the defaults that this fit describes."""
    return (
        bool(params.get("order"))
        and params.get("early") == 0.8
        and params.get("noise") == 0.28
        and not (
            params.get("offers")
            or params.get("capacity")
            or params.get("chainPick")
            or params.get("chainRaise")
            or params.get("maxShare", 1) < 1
        )
    )


def unzip(path: str) -> str:
    with gzip.open(path, "rt") as file:
        return file.read()


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def rows() -> tuple[list[dict], list[float], list[dict]]:
    """One row per delivered order: the features of outlook.ts, its fee over typical, and the order's facts."""
    roads = {(r["from"], r["to"]): r["minutes"] for r in json.loads(Path("sim/data/map.json").read_text())["roads"]}
    xs, ys, facts = [], [], []
    for folder in sorted(glob.glob("data/scrape/runs/L8/*/*")):
        try:
            meta = json.loads(Path(f"{folder}/meta.json").read_text())
        except OSError:
            continue
        if meta.get("policy") != "ts-lean" or not current((meta.get("settings") or {}).get("params") or {}):
            continue
        events = [json.loads(line) for line in unzip(f"{folder}/events.jsonl.gz").splitlines()]
        gigs = {g["id"]: g for g in json.loads(unzip(f"{folder}/snapshot.json.gz"))["gigs"]}
        drivers = json.loads(unzip(f"{folder}/drivers.json.gz"))
        drivers = drivers if isinstance(drivers, list) else drivers.get("drivers", [])
        homes = collections.Counter(d["homePlaceId"] for d in drivers)
        requests, orders, fees, picked, waiting = {}, {}, {}, {}, collections.Counter()
        cancelled = set()
        for e in events:
            kind = e["kind"]
            if kind == "price_request":
                requests[e["request"]["id"]] = e["request"]
            elif kind in ("order_won", "order_changed"):
                orders[e["order"]["id"]] = e["order"]
            elif kind == "order_cancelled":
                cancelled.add(e["orderId"])
            elif kind == "gig_booked":
                fees[e["gigId"]] = e["feeCents"]
            elif kind == "picked_up":
                picked[e["orderId"]] = e["gigId"]
            elif kind == "ledger" and e["line"]["kind"] == "waiting" and e["line"].get("orderId"):
                waiting[e["line"]["orderId"]] -= e["line"]["cents"]
        won, won_on = 0, collections.Counter()
        for rid, request in sorted(requests.items(), key=lambda item: item[1]["arrivedAt"]):
            order = orders.get(rid)
            if not order or rid in cancelled:
                continue
            at = request["arrivedAt"] + 8
            gig = gigs.get(picked.get(rid, ""))
            if gig and gig["id"] in fees:
                cars = {s["orderId"] for s in gig["stops"]}
                typical = sum(requests[c]["referenceFeeCents"] for c in cars if c in requests)
                leg = request["legs"][0]
                a, b = leg["pickup"]["placeId"], leg["delivery"]["placeId"]
                drive = roads.get((a, b), 0) / 60
                ready = leg["pickup"]["window"]["from"]
                to_last = (order["deadline"] - 66 * drive - 30 - at) / 60
                offset, hour, day = ready // DAY - at // DAY, at % DAY / 60, at // DAY
                today, long = int(offset <= 0), clamp(drive - 3, 0, 6) / 6
                size = math.log(max(1, request["referenceFeeCents"]) / 5000)
                xs.append({
                    "log_typical": size, "log_typical_sq": size * size, "pickup_today": today,
                    "pickup_later": int(offset >= 2), "hour": (hour - 13) / 5,
                    "today_late_hour": today * clamp(hour - 12, 0, 6) / 6, "long_drive": long,
                    "very_long_drive": clamp(drive - 5, 0, 4) / 4, "short_drive": int(drive < 0.75),
                    "today_long_drive": today * long, "time_to_last_pickup": math.log(clamp(to_last, 1, 96) / 24),
                    "tight": int(to_last < 8), "room": math.log(clamp((order["deadline"] - ready) / 60, 2, 120) / 24),
                    "monday": int(day == 0), "thursday": int(day == 3), "friday": int(day == 4),
                    "private_pickup": int(leg["pickup"]["privateAddress"]),
                    "private_delivery": int(leg["delivery"]["privateAddress"]), "premium": int(leg["car"]["premium"]),
                    "electric": int(leg["car"]["electric"]), "trade_in": int(len(request["legs"]) > 1),
                    "has_note": int(bool(request.get("note"))), "home_pickup": math.log(1 + homes[a]) / 5,
                    "home_delivery": math.log(1 + homes[b]) / 5,
                    "drivers": math.log(max(1, sum(homes.values())) / 777), "won_so_far": won / 300,
                    "won_today": won_on[day] / 80, "open_gigs": 0,
                })  # fmt: skip
                ys.append(fees[gig["id"]] / typical + waiting[rid] / request["referenceFeeCents"])
                facts.append({"today": bool(today), "day": day, "private": leg["pickup"]["privateAddress"],
                              "chain": len(cars) > 1})  # fmt: skip
            won += 1
            won_on[request["arrivedAt"] // DAY] += 1
    return xs, ys, facts


def main() -> None:
    xs, ys, facts = rows()
    keys = list(xs[0])
    a = np.array([[1.0] + [x[k] for k in keys] for x in xs])
    y = np.array(ys)
    ridge = np.eye(a.shape[1]) * 5
    ridge[0, 0] = 0
    weights = dict(zip(["base", *keys], np.linalg.solve(a.T @ a + ridge, a.T @ y), strict=True))
    old = json.loads(Path(MODELS[0]).read_text())
    was = np.array([old["cost"]["base"] + sum(old["cost"].get(k, 0) * x[k] for k in keys) for x in xs])
    was *= y.mean() / was.mean()
    now = a @ np.array(list(weights.values()))
    print(f"{len(y)} orders, mean cost {y.mean():.3f} x typical")
    for key, value in weights.items():
        print(f"  {key:22s} {value:+.3f}   in order.json {old['cost'].get(key, 0) * y.mean() / old['meanCost']:+.3f}")
    groups = {
        "ready today": [f["today"] for f in facts], "ready later": [not f["today"] for f in facts],
        "friday": [f["day"] == 4 for f in facts], "private pickup": [f["private"] for f in facts],
        "in a chain": [f["chain"] for f in facts],
    }  # fmt: skip
    for name, mask in groups.items():
        m = np.array(mask)
        print(
            f"{name:16s} {m.sum():5d} orders  paid {y[m].mean():.2f}  order.json {was[m].mean():.2f}  fit {now[m].mean():.2f}"
        )
    if "--write" in sys.argv:
        # No premium car and no count of open gigs is in these weeks: both keep their old weight, at the new level.
        for key in ("premium", "open_gigs"):
            weights[key] = old["cost"][key] * y.mean() / old["meanCost"]
        old["cost"] = {key: round(float(weights[key]), 4) for key in old["cost"]}
        # The mean order costs LEVEL of what the week's bookings pay, as with the weights before: at 1 every quote
        # rose 5% and 29 orders a week were lost for the same margin (server, five seeds).
        old["meanCost"] = round(float(y.mean()) / LEVEL, 4)
        for path in MODELS:
            Path(path).write_text(json.dumps(old, indent=2) + "\n")


if __name__ == "__main__":
    main()
