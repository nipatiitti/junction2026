"""Fit city/hour follow-on demand for informed_chain from saved weeks, without ever playing online.

Each civilian place / day / hour has one observed arrival intensity, measured in return-leg opportunities per week.
The data is one full dispatch week per seed; playing the same quota stream six ways would otherwise count its requests
six times. A mean of 0.5 means one compatible car every two weeks, and 12 means once every 36 minutes in that cell.

    uv run python -m strategies.informed_chain.priors_fit --db out/spread.sqlite

It writes priors.json next to the strategy; no server access takes place.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("out/spread.sqlite"))
    parser.add_argument("--level", type=int, default=8)
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("priors.json"))
    args = parser.parse_args()
    db = sqlite3.connect(args.db)
    weeks = [
        r[0]
        for r in db.execute(
            "select min(id) from weeks where level=? and policy='dispatch' group by seed", (args.level,)
        )
    ]
    if not weeks:
        raise SystemExit("no saved dispatch weeks at this level; build out/spread.sqlite with tools.db first")
    counts: dict[str, dict[str, dict[int, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for week_id in weeks:
        for arrived_at, place in db.execute(
            "select r.arrived_at, l.delivery_place"
            " from requests r join legs l on l.week_id=r.week_id and l.request_id=r.id and l.leg=0"
            " where r.week_id=?",
            (week_id,),
        ):
            day, hour = arrived_at // 1440, arrived_at % 1440 // 60
            counts[place][str(day % 7)][hour] += 1
    doc = {
        "source": "one full dispatch practice week per seed from out/spread.sqlite; one dispatched order's delivery and future pickup may coincide here",
        "level": args.level,
        "weeks": len(weeks),
        "units": "car arrivals per week, not probability; `expected = rate * wait_hours / 60`",
        "rates": {p: dict(days) for p, days in counts.items()},
    }
    args.out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {args.out}: {len(counts)} places over {len(weeks)} saved weeks")


if __name__ == "__main__":
    main()
