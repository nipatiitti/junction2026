"""Fits the lane fees of `LaneFee` on the saved weeks: the typical fee of each lane, without the noise of one request.

    uv run python -m tools.db                   # the saved weeks -> out/spread.sqlite
    uv run python -m strategies.lane_fee.fit    # writes strategies/lane_fee/lanes.json and prints the fit

A lane is a pickup place and a delivery place. Every price request of every saved week counts once for the lane of its
first car, whatever the system that played the week did: the requests of a seed are the same in every week of it.
lanes.json holds, for each lane, the mean of the log typical fee and the number of requests, and a straight line of
the typical fee against the road minutes for a lane with no request. README.md next to this file says what the fit
shows.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).with_name("lanes.json")


def requests(db: sqlite3.Connection, levels: list[int]) -> list[tuple[str, str, int, int]]:
    """(pickup, delivery, road minutes, typical fee) of the first car of each distinct request."""
    marks = ",".join("?" * len(levels))
    seen: set[tuple[str, int]] = set()
    rows = []
    for week, seed, level in db.execute(f"select id, seed, level from weeks where level in ({marks})", levels):
        if (seed, level) in seen:
            continue  # the same requests as an earlier week of the seed
        seen.add((seed, level))
        rows += db.execute(
            "select l.pickup_place, l.delivery_place, l.minutes, r.reference_fee_cents from requests r "
            "join legs l on l.week_id = r.week_id and l.request_id = r.id and l.leg = 0 where r.week_id = ?",
            (week,),
        ).fetchall()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Fits the typical fee of each lane on the saved weeks.")
    parser.add_argument("--db", default="out/spread.sqlite")
    parser.add_argument("--levels", default="7,8", help="the levels whose requests count, comma-separated")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    rows = requests(sqlite3.connect(args.db), [int(level) for level in args.levels.split(",")])
    lanes: dict[tuple[str, str], list[float]] = defaultdict(list)
    minutes: dict[tuple[str, str], int] = {}
    for pickup, delivery, drive, typical in rows:
        lanes[pickup, delivery].append(math.log(typical))
        minutes[pickup, delivery] = drive
    means = {lane: statistics.fmean(logs) for lane, logs in lanes.items()}
    # The line for a lane without requests: the typical fee against the road minutes, over the lanes' means.
    xs = [minutes[lane] for lane in means]
    ys = [math.exp(mean) for mean in means.values()]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    base = my - slope * mx
    noise = statistics.pstdev([value - means[lane] for lane, logs in lanes.items() if len(logs) >= 6 for value in logs])
    spread = statistics.pstdev(
        [means[lane] - math.log(base + slope * minutes[lane]) for lane, logs in lanes.items() if len(logs) >= 6]
    )
    print(f"{len(rows)} requests on {len(lanes)} lanes")
    print(f"A request's typical fee around its lane's: log sd {noise:.3f}")
    print(f"A lane's typical fee around {base / 100:.2f} + {slope / 100:.4f} x road minutes: log sd {spread:.3f}")
    out = {
        "requests": len(rows),
        "noise": round(noise, 4),
        "spread": round(spread, 4),
        "base": round(base, 1),
        "per_minute": round(slope, 3),
        "lanes": {f"{a}>{b}": [round(means[a, b], 4), len(lanes[a, b])] for a, b in sorted(lanes)},
    }
    Path(args.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
