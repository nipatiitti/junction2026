"""Server vs simulator on the same seeds and the same prober settings.
uv run --with numpy python sim/cal_cmp.py <real dir> <sim dir> seed [seed ...]"""

import json
import sys
from pathlib import Path

import numpy as np

real, sim, seeds = sys.argv[1], sys.argv[2], sys.argv[3:]


def load(root):
    rows = []
    metas = []
    for seed in seeds:
        folder = Path(root) / "fee" / "L8" / seed
        try:
            rows += [dict(json.loads(line), seed=seed) for line in (folder / "probes.jsonl").read_text().splitlines()]
            metas.append(json.loads((folder / "meta.json").read_text()))
        except OSError, ValueError:
            print("missing", folder / "probes.jsonl")
    return rows, metas


def bucket(x, cuts):
    return sum(x >= c for c in cuts)


CUTS = [
    ("all", lambda r: ""),
    (
        "pickup",
        lambda r: ["today", "+1 day", "+2 or more"][min(2, max(r["readyAt"], r["at"]) // 1440 - r["at"] // 1440)],
    ),
    ("won on", lambda r: ["Mon", "Tue", "Wed", "Thu", "Fri"][min(4, r["at"] // 1440)]),
    (
        "booked gigs",
        lambda r: ["<50", "50-150", "150-300", "300+"][bucket(r["load"]["booked"], [50, 150, 300])],
    ),
    ("typical fee", lambda r: ["<€40", "€40-90", "€90+"][bucket(r["referenceFeeCents"], [4000, 9000])]),
    ("hour", lambda r: ["<12", "12-15", "15+"][bucket((r["at"] % 1440) / 60, [12, 15])]),
    ("private", lambda r: "yes" if any(any(p) for p in r["private"]) else "no"),
]


def stat(values):
    if len(values) < 10:
        return f"{len(values):4d}  -"
    flips = [r["flip"] for r in values if r["flip"]]
    low = [next(t["minutes"] for t in r["trials"] if t["high"]) for r in values if r["flip"]]
    views = [t["views"] for r in values for t in r["trials"] if not t.get("refused") and t["x"] <= 1.8]
    none = np.mean([r["ends"] == "above" for r in values])
    flip_summary = " ".join(f"{x:.2f}" for x in np.percentile(flips, [10, 50, 90]))
    return (
        f"{len(values):4d} none {none:.2f} | flip {flip_summary} | "
        f"wait {np.median(low):3.0f} | views {np.median(views):2.0f}"
    )


R, RM = load(real)
S, SM = load(sim)
for name, metas in (("server", RM), ("sim", SM)):
    results = " | ".join(
        f"{m['seed']} {m['score']['wonOrders']} orders {100 * m['score']['onTimeShare']:.0f}% "
        f"€{m['score']['marginCents'] / 100:.0f}"
        for m in metas
    )
    print(f"{name:<7}", results)
print(f"{'':<22} {'SERVER  (n, none<=1.8x, flip p10 p50 p90, min to book, views)':<62} SIMULATOR")
for name, key in CUTS:
    for k in sorted({key(r) for r in R}):
        server = stat([r for r in R if key(r) == k])
        simulated = stat([r for r in S if key(r) == k])
        print(f"{f'{name} {k}':<22} {server:<62} {simulated}")
