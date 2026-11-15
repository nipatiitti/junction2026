"""Summary of fee probes and week outcomes in a prober output folder, to compare the server with the simulator.
uv run --with numpy python sim/cal_fee.py data/scrape/probe2 [seed ...]"""

import collections
import json
import sys
from pathlib import Path

import numpy as np

root, seeds = Path(sys.argv[1]), set(sys.argv[2:])
rows = []
metas = []
for path in sorted((root / "fee" / "L8").glob("*/probes.jsonl")):
    seed = path.parent.name
    if seeds and seed not in seeds:
        continue
    rows += [dict(json.loads(line), seed=seed) for line in path.read_text().splitlines()]
    try:
        metas.append(json.loads((path.parent / "meta.json").read_text()))
    except (OSError, ValueError) as error:
        print(f"No readable week meta for {seed}: {error}")
for m in metas:
    print(
        f"  {m['seed']}: {m['score']['wonOrders']} orders, {100 * m['score']['onTimeShare']:.0f}% on time, "
        f"margin €{m['score']['marginCents'] / 100:.0f}"
    )


def q(values, percentiles=(10, 25, 50, 75, 90)):
    return " ".join(f"{x:.2f}" for x in np.percentile(values, percentiles)) if len(values) else "-"


def block(name, rs):
    if len(rs) < 8:
        return
    flips = [r["flip"] for r in rs if r["flip"]]
    above = np.mean([r["ends"] == "above" for r in rs])
    below = np.mean([r["ends"] == "below" for r in rs])
    lowm = [next(t["minutes"] for t in r["trials"] if t["high"]) for r in rs if r["flip"]]
    views = [t["views"] for r in rs for t in r["trials"] if not t.get("refused")]
    print(
        f"{name:<22} n={len(rs):4d} flip p10/25/50/75/90: {q(flips)} | "
        f"none<=1.8x {above:.2f} all>=0.45x {below:.2f} | "
        f"min to book at lowest fee p50 {np.median(lowm) if lowm else -1:3.0f} "
        f"p90 {np.percentile(lowm, 90) if lowm else -1:3.0f} | "
        f"views p50 {np.median(views):2.0f} p90 {np.percentile(views, 90):3.0f}"
    )


block("all", rows)
block("same_day", [r for r in rows if r["option"] == "same_day"])
block("next_day+", [r for r in rows if r["option"] != "same_day"])
for a, b in ((0, 2), (2, 6), (6, 24), (24, 999)):
    block(f"lead {a}-{b}h", [r for r in rows if a <= (max(r["readyAt"], r["at"]) - r["at"]) / 60 < b])
for a, b in ((0, 60), (60, 180), (180, 9999)):
    block(f"drive {a}-{b}min", [r for r in rows if a <= r["referenceFeeCents"] / 38.7 - 40 < b])
for a, b in ((0, 5), (5, 15), (15, 999)):
    block(f"open gigs {a}-{b}", [r for r in rows if a <= r["load"]["open"] < b])
for a, b in ((9, 12), (12, 15), (15, 21)):
    block(f"hour {a}-{b}", [r for r in rows if a <= (r["at"] % 1440) // 60 < b])
big = collections.Counter(r["lane"][0][0] for r in rows).most_common(3)
for town, _ in big:
    block("from " + town, [r for r in rows if r["lane"][0][0] == town])
block("private", [r for r in rows if any(any(p) for p in r["private"])])
