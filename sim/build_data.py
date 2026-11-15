"""Builds one data pack per recorded seed: everything the server fixes per seed, whatever the policy does.
uv run python sim/build_data.py   ->  sim/data/L<level>/<seed>.json.gz and sim/data/map.json
Reads the saved weeks under data/scrape/ (runs, passive, starter, probe2) and, when present, out/scrape/explore-*."""

import collections
import glob
import gzip
import json
import os
import shutil
from multiprocessing import Pool
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "sim", "data")
CAP = 14  # worlds read per seed
MARKET_PATH = Path(ROOT) / "sim" / "market.json"
MARKET = json.loads(MARKET_PATH.read_text())["market"] if MARKET_PATH.exists() else {}


def opener(path):
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)


def first(*paths):
    for path in paths:
        if os.path.exists(path):
            return path
    return None


def read_reveal(folder):
    path = first(folder + "/reveal.json.gz", folder + "/reveal.json")
    if not path:
        return None
    try:
        with opener(path) as stream:
            return json.load(stream)
    except OSError, ValueError:
        return None


def one(args):
    (level, seed), dirs = args
    pack = {
        "seed": seed,
        "level": level,
        "requests": None,
        "drivers": None,
        "truths": {},
        "cancels": {},
        "changes": {},
        "forecasts": None,
        "won": {},
    }
    for folder in dirs[:CAP]:
        rv = read_reveal(folder)
        if not isinstance(rv, dict) or "requests" not in rv:
            continue
        if pack["requests"] is None:
            pack["requests"] = [x["request"] for x in rv["requests"]]
        for order in rv["orders"]:
            pack["truths"].setdefault(
                order["orderId"],
                [{k: v for k, v in leg.items() if k not in ("pickedUpAt", "deliveredAt")} for leg in order["legs"]],
            )
        dp = first(folder + "/drivers.json.gz", folder + "/drivers.json")
        if dp and pack["drivers"] is None:
            with opener(dp) as stream:
                pack["drivers"] = [
                    {k: x[k] for k in ("id", "homePlaceId", "rating", "licence", "completedGigs")}
                    for x in json.load(stream)
                ]
        ep = first(folder + "/events.jsonl.gz")
        if not ep:
            continue
        forecasts = []
        with opener(ep) as stream:
            for line in stream:
                if '"order_won"' in line:
                    order = json.loads(line)["order"]
                    pack["won"].setdefault(order["id"], {}).setdefault(
                        order["option"],
                        {
                            "deadline": order["deadline"],
                            "lastPickupAt": order["lastPickupAt"],
                            "windows": [[leg["pickup"]["window"], leg["delivery"]["window"]] for leg in order["legs"]],
                        },
                    )
                elif '"order_cancelled"' in line:
                    event = json.loads(line)
                    pack["cancels"].setdefault(event["orderId"], event["at"])
                elif '"order_changed"' in line:
                    event = json.loads(line)
                    if event.get("message"):
                        changes = pack["changes"].setdefault(event["order"]["id"], [])
                        if not any(c["at"] == event["at"] for c in changes):
                            changes.append(
                                {
                                    "at": event["at"],
                                    "message": event["message"],
                                    "deadline": event["order"]["deadline"],
                                    "places": [
                                        [leg["pickup"]["placeId"], leg["delivery"]["placeId"]]
                                        for leg in event["order"]["legs"]
                                    ],
                                }
                            )
                elif '"forecast"' in line:
                    forecasts.append(json.loads(line))
        if pack["forecasts"] is None:
            pack["forecasts"] = forecasts
    if not pack["requests"] or not pack["drivers"]:
        return None
    pack["forecasts"] = pack["forecasts"] or []
    pack["market"] = MARKET.get(
        seed
    )  # the server's price level per weekday, recovered from recorded quotes (sim/market.json)
    os.makedirs(f"{OUT}/L{level}", exist_ok=True)
    with gzip.open(f"{OUT}/L{level}/{seed}.json.gz", "wt") as stream:
        json.dump(pack, stream, separators=(",", ":"))
    return (
        level,
        seed,
        len(pack["requests"]),
        len(pack["truths"]),
        len(pack["cancels"]),
        len(pack["changes"]),
    )


if __name__ == "__main__":
    groups = collections.defaultdict(list)
    sources = [ROOT + "/data/scrape/" + s for s in ("runs", "passive", "starter", "probe2")] + sorted(
        glob.glob(ROOT + "/out/scrape/explore-*")
    )
    metas = (m for source in sources for m in glob.glob(source + "/**/meta.json", recursive=True))
    for meta_path in metas:
        meta = json.loads(Path(meta_path).read_text())
        if meta.get("level") != 8 or meta.get("kind") == "board" or "/board/" in meta_path:
            continue
        groups[(meta["level"], meta["seed"])].append(os.path.dirname(meta_path))
    for key in groups:
        groups[key].sort(key=lambda p: -os.path.getsize(first(p + "/reveal.json.gz", p + "/reveal.json") or p))
    with Pool(14) as pool:
        results = [r for r in pool.imap_unordered(one, groups.items(), chunksize=2) if r]
    n = len(results)
    print(
        n,
        "packs",
        f"truth coverage of requests: {sum(r[3] for r in results) / sum(r[2] for r in results):.2f}",
        f"cancels/seed {sum(r[4] for r in results) / n:.1f} changes/seed {sum(r[5] for r in results) / n:.1f}",
    )
    shutil.copy(first(ROOT + "/data/scrape/runs/map.json", ROOT + "/data/scrape/passive/map.json"), OUT + "/map.json")
