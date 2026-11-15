"""Server vs simulator: how the week's result moves when the policy changes (prober --mode branch).
uv run python sim/cal_branch.py <real dir> <sim dir> seed [seed ...]"""

import collections
import json
import sys
from pathlib import Path


def load(root, seed):
    folder = Path(root) / "branch" / "L8" / seed
    meta = json.loads((folder / "meta.json").read_text())
    rows = [json.loads(line) for line in (folder / "probes.jsonl").read_text().splitlines()]
    return meta["score"], rows


def name(variant):
    if "qScale" in variant:
        return f"quotes x{variant['qScale']:.1f}"
    if "fOpen" in variant:
        return f"opening fee {variant['fOpen'] - 0.9:+.2f}"
    return "town"


def effect(values):
    if not values:
        return "-"
    orders, margin, on_time = (sum(x[j] for x in values) / len(values) for j in range(3))
    return f"{orders:+5.0f} orders {margin:+7.0f}€ {on_time:+5.1f}pp (n={len(values)})"


agg = collections.defaultdict(lambda: [[], []])
for seed in sys.argv[3:]:
    (rm, rr), (sm, sr) = load(sys.argv[1], seed), load(sys.argv[2], seed)
    print(
        f"{seed} base: SERVER {rm['wonOrders']} orders {100 * rm['onTimeShare']:.0f}% "
        f"€{rm['marginCents'] / 100:.0f} | SIM {sm['wonOrders']} orders {100 * sm['onTimeShare']:.0f}% "
        f"€{sm['marginCents'] / 100:.0f}"
    )
    for i, (rows, base) in enumerate(((rr, rm), (sr, sm))):
        for row in rows:
            score = row["score"]
            agg[name(row["variant"])][i].append(
                (
                    score["wonOrders"] - base["wonOrders"],
                    (score["marginCents"] - base["marginCents"]) / 100,
                    100 * (score["onTimeShare"] - base["onTimeShare"]),
                )
            )
print(f"{'mean effect':<20} {'SERVER (orders, margin, on-time points)':<44} SIMULATOR")
for key in sorted(agg):
    print(f"{key:<20} {effect(agg[key][0]):<44} {effect(agg[key][1])}")
