"""Server vs simulator on recorded weeks replayed with sim/replay.ts: what happened to each first posting.
uv run --with numpy python sim/cal_replay.py replay.jsonl"""

import json
import sys
from pathlib import Path

import numpy as np

W = [json.loads(line) for line in Path(sys.argv[1]).read_text().splitlines() if line.strip()]
G = [dict(g, policy=w["policy"]) for w in W for g in w["gigs"] if "refused" not in g]
print(
    len(W),
    "weeks,",
    len(G),
    "first postings,",
    sum("refused" in g for w in W for g in w["gigs"]),
    "refused in the simulator",
)


def wk(side, f):
    return np.array([f(w[side]) for w in W], float)


for name, f in (
    ("orders", lambda s: s["counts"]["order_won"]),
    ("bookings", lambda s: s["counts"]["gig_booked"]),
    ("drops", lambda s: s["counts"]["gig_dropped"]),
    ("expired", lambda s: s["counts"]["gig_expired"]),
    ("views", lambda s: s["counts"]["gig_viewed"]),
    ("deadline warnings", lambda s: s["counts"]["deadline_close"]),
    ("on time %", lambda s: 100 * s["score"]["onTimeShare"]),
    ("margin €", lambda s: s["score"]["marginCents"] / 100),
):
    r, s = wk("real", f), wk("sim", f)
    correlation = np.corrcoef(r, s)[0, 1] if r.std() > 0 and s.std() > 0 else float("nan")
    print(f"  per week {name:<18} server {r.mean():8.1f}   simulator {s.mean():8.1f}   correlation {correlation:.2f}")


def bucket(x, cuts):
    return sum(x >= c for c in cuts)


def stat(values, side):
    booked = [g[side].get("booked") for g in values]
    waits = np.array([x["at"] - g["at"] for x, g in zip(booked, values) if x], float)
    fees = np.array([x["fee"] / g["ref"] for x, g in zip(booked, values) if x and g["ref"]])
    n = len(values)
    return (
        f"booked {len(waits) / n:.2f} | <=30m {(waits <= 30).sum() / n:.2f} "
        f"<=3h {(waits <= 180).sum() / n:.2f} | wait p50 {np.median(waits) if len(waits) else -1:4.0f} | "
        f"fee/typical p50 {np.median(fees) if len(fees) else -1:.2f} | "
        f"dropped {np.mean([bool(g[side].get('dropped')) for g in values]):.2f}"
    )


CUTS = [
    ("all", lambda g: ""),
    ("pickup", lambda g: ["today", "+1 day", "+2 or more"][min(2, max(g["from"], g["at"]) // 1440 - g["at"] // 1440)]),
    (
        "opening fee",
        lambda g: ["<0.7x", "0.7-0.85x", "0.85-1x", "1-1.3x", "1.3x+"][
            bucket(g["open0"] / max(g["ref"], 1), [0.7, 0.85, 1, 1.3])
        ],
    ),
    ("posted on", lambda g: ["Mon", "Tue", "Wed", "Thu", "Fri", "later"][min(5, g["at"] // 1440)]),
    ("booked gigs", lambda g: ["<50", "50-150", "150+"][bucket(g["load"]["booked"], [50, 150])]),
    ("cars", lambda g: "1" if g["cars"] == 1 else "2+"),
    ("private", lambda g: "yes" if g["private"] else "no"),
    ("hour", lambda g: ["<12", "12-15", "15+"][bucket(g["at"] % 1440 / 60, [12, 15])]),
]
print(f"{'':<24} {'n':>6}  {'SERVER':<88} SIMULATOR")
for name, key in CUTS:
    for k in sorted({key(g) for g in G}):
        values = [g for g in G if key(g) == k]
        if len(values) >= 50:
            print(f"{f'{name} {k}':<24} {len(values):6d}  {stat(values, 'real'):<88} {stat(values, 'sim')}")
