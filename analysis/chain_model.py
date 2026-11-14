"""Fits lean's chain model (`src/strategies/lean/chain.json`): the chance that a posted chain books within an hour,
from what the planner knows when it posts it. It reads every saved server week of the TypeScript lean that posted
chains with a 2-hour hold, prints how well the model sorts chains of seeds it has not seen, and with `--write`
saves the weights. `score` in `src/strategies/lean/chains.ts` computes the same features.

    uv run --no-project --python 3.13 --with scikit-learn python -m analysis.chain_model
"""

from __future__ import annotations

import collections
import glob
import gzip
import itertools
import json
import math
import sys

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, cross_val_predict

DAY = 1440
MODEL = "src/strategies/lean/chain.json"
LEVELS = [0.78, 0.88, 1, 1.12]  # planner.ts: what `chainSpread` draws from

with open("sim/data/map.json") as _file:
    MAP = json.load(_file)
ROADS = {(r["from"], r["to"]): r["minutes"] for r in MAP["roads"]}
PLACES = {p["id"]: p for p in MAP["places"]}


def minutes(a: str, b: str) -> float:
    return 0 if a == b else ROADS.get((a, b), 9999)


def apart(a: str, b: str) -> float:
    """Kilometres in a straight line, on a flat map at 61 degrees north (chains.ts, `apart`)."""
    p, q = PLACES[a], PLACES[b]
    return math.hypot((p["lon"] - q["lon"]) * 111 * math.cos(math.radians(61)), (p["lat"] - q["lat"]) * 111)


def draw(text: str) -> float:
    """planner.ts, `draw`: FNV-1a, so a chain's drawn fee level can be read back from its orders."""
    h = 0x811C9DC5
    for ch in text:
        h = ((h ^ ord(ch)) * 0x01000193) & 0xFFFFFFFF
    return h / 2**32


def share(homes: collections.Counter, test) -> float:
    """The share of the drivers whose home passes `test`."""
    return sum(n for home, n in homes.items() if test(home)) / sum(homes.values())


def read(path: str):
    """A saved file as JSON; `.gz` files are unpacked."""
    with gzip.open(path, "rt") if path.endswith(".gz") else open(path) as file:
        return json.load(file)


def chains(folder: str, params: dict) -> list[dict]:
    """One row for each chain that the week posted: the model's features and whether it booked within an hour."""
    drivers = read(folder + "/drivers.json.gz")
    snapshot = read(folder + "/snapshot.json.gz")
    with gzip.open(folder + "/events.jsonl.gz", "rt") as file:
        events = [json.loads(line) for line in file]
    homes = collections.Counter(d["homePlaceId"] for d in drivers)
    orders = {o["id"]: o for o in snapshot["orders"]}
    typical = {e["request"]["id"]: e["request"]["referenceFeeCents"] for e in events if e["kind"] == "price_request"}
    booked: dict[str, dict] = {}
    bookings: list[int] = []
    views = collections.defaultdict(list)
    for e in events:
        if e["kind"] == "gig_booked":
            booked.setdefault(e["gigId"], e)
            bookings.append(e["at"])
        elif e["kind"] == "gig_viewed":
            views[e["gigId"]].append(e["at"])
    earlier = collections.defaultdict(list)  # order id -> the gigs it was in before
    rows = []
    for gig in sorted(snapshot["gigs"], key=lambda g: g["postedAt"]):
        cars = list(dict.fromkeys(s["orderId"] for s in gig["stops"] if s["kind"] == "pickup"))
        if len(cars) >= 2 and all(c in orders and c in typical for c in cars):
            legs = [orders[c]["legs"][0] for c in cars]
            at = gig["postedAt"]
            first, last = legs[0]["pickup"]["placeId"], legs[-1]["delivery"]["placeId"]
            wheel = sum(minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) for leg in legs)
            hops = sum(minutes(a["delivery"]["placeId"], b["pickup"]["placeId"]) for a, b in itertools.pairwise(legs))
            hours = (wheel + hops) / 60
            if not 0.2 < hours <= 8.2:
                for c in cars:
                    earlier[c].append(gig["id"])
                continue
            window = gig["stops"][0].get("window") or legs[0]["pickup"]["window"]
            start = (max(at + 120, window["from"]) % DAY) / 60
            level = (LEVELS[int(draw(" ".join(cars)) * 4)] if params.get("chainSpread") else 1) * params.get(
                "chainOpen", 1
            )
            fee = gig["schedule"][0]["feeCents"] / level  # the opening fee at level 1, in cents
            load = min(sum(1 for b in bookings if b < at) / len(drivers), 0.6)
            fresh = [not any(v < at for g in earlier[c] for v in views[g]) for c in cars]
            book = booked.get(gig["id"])
            rows.append(
                {
                    "y": int(bool(book) and book["at"] - at <= 60),
                    "drive": hours,
                    "long": max(0, hours - 5),
                    "cars": len(cars),
                    "empty": hops / 60 / hours,
                    "home": min(minutes(last, first), 360) / 60,
                    "pay": math.log(fee / hours / 1900),
                    "level": math.log(level),
                    "s180": share(homes, lambda h, a=first, b=last: minutes(h, a) + minutes(b, h) <= 180),
                    "s60": share(homes, lambda h, a=first, b=last: minutes(h, a) + minutes(b, h) <= 60),
                    "last30": share(homes, lambda h, b=last: apart(h, b) <= 30),
                    "first30": share(homes, lambda h, a=first: apart(h, a) <= 30),
                    "load": load,
                    "loadDrive": load * hours,
                    "monday": int(at // DAY == 0),
                    "fresh": sum(fresh) / len(cars),
                    "late": int(start >= 12),
                    "night": int(start < 7),
                    "drivers": len(drivers) / 900,
                }
            )
        for c in cars:
            earlier[c].append(gig["id"])
    return rows


def main() -> None:
    rows, seeds, weeks = [], [], 0
    for meta in sorted(glob.glob("data/scrape/runs/L8/*/*/meta.json")):
        week = read(meta)
        params = week.get("settings", {}).get("params", {})
        # Weeks that priced chains by an earlier model would teach the model its own choices.
        if week.get("policy") != "ts-lean" or not params.get("chains") or params.get("holdHours") != 2:
            continue
        if params.get("chainModel"):
            continue
        try:
            found = chains(meta.rsplit("/", 1)[0], params)
        except Exception:  # noqa: BLE001, S112  a week that cannot be read is left out
            continue
        weeks += 1
        rows += found
        seeds += [week["seed"]] * len(found)
    keys = [k for k in rows[0] if k != "y"]
    x = np.array([[r[k] for k in keys] for r in rows])
    y = np.array([r["y"] for r in rows])
    mean, spread = x.mean(0), x.std(0) + 1e-9
    model = LogisticRegression(C=1, max_iter=2000)
    held = cross_val_predict(
        model, (x - mean) / spread, y, groups=np.array(seeds), cv=GroupKFold(5), method="predict_proba"
    )[:, 1]
    print(f"{len(rows)} chains of {weeks} weeks, {y.mean():.0%} booked within an hour.")
    print(
        f"On seeds the fit did not see: AUC {roc_auc_score(y, held):.3f}. By fifth of the chains, predicted and booked:"
    )
    fifth = np.digitize(held, np.quantile(held, [0.2, 0.4, 0.6, 0.8]))
    for i in range(5):
        print(f"  {held[fifth == i].mean():.2f}  {y[fifth == i].mean():.2f}")
    model.fit((x - mean) / spread, y)
    weights = model.coef_[0] / spread
    intercept = model.intercept_[0] - (model.coef_[0] * mean / spread).sum()
    print("Weights (for one standard deviation, and as saved):")
    for k, std, raw in sorted(zip(keys, model.coef_[0], weights), key=lambda t: -abs(t[1])):
        print(f"  {k:10} {std:+.2f}  {raw:+.4f}")
    if "--write" in sys.argv:
        saved = {
            "intercept": round(float(intercept), 4),
            "weights": {k: round(float(w), 4) for k, w in zip(keys, weights)},
        }
        with open(MODEL, "w") as out:
            json.dump(saved, out, indent=2)
            out.write("\n")
        print(f"Wrote {MODEL}.")


if __name__ == "__main__":
    main()
