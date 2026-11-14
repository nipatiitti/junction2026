"""Builds the dejavu memory: per seed, request id -> option -> [highest trust-free win, lowest trust-free loss].

Usage: uv run python src/strategies/dejavu/build_table.py spread-1 [spread-9 ...]
Reads out/spread.sqlite (build it with `uv run python -m tools.db`), writes table-<seed>.json next to this file.
"""

import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE.parents[2] / "out" / "spread.sqlite"
if not DB.exists():
    DB = Path("/home/nipatiitti/projects/hackathons/junction2026/out/spread.sqlite")


def build(seed: str) -> dict:
    c = sqlite3.connect(DB)
    weeks = [r[0] for r in c.execute("select id from weeks where seed=? and level=8", (seed,))]
    q = ",".join("?" * len(weeks))
    won_req = {
        (w, r)
        for w, r in c.execute(
            f"select week_id, request_id from quote_facts where outcome='won' and week_id in ({q})", weeks
        )
    }
    table: dict = {}
    rows = c.execute(
        f"select week_id, request_id, option, ratio, outcome, dealer_trust, list_price_cents from quote_facts "
        f"where week_id in ({q}) and ratio is not null",
        weeks,
    )
    lists: dict = {}
    for w, rid, opt, ratio, outcome, trust, lp in rows:
        lists.setdefault(rid, {})[opt] = lp
        free = ratio / (1 + (trust or 0) / 100)
        rec = table.setdefault(rid, {}).setdefault(opt, [0.0, 99.0])
        if outcome == "won":
            rec[0] = max(rec[0], free)
        elif outcome == "lost" and (w, rid) not in won_req:
            rec[1] = min(rec[1], free)
    # Cost and lateness of each request when we took it: cost = revenue - margin, as a share of list.
    cost: dict = {}
    for oid, rev, margin, ontime, lp in c.execute(
        f"select order_id, revenue_cents, margin_cents, on_time, list_price_cents from order_facts "
        f"where week_id in ({q}) and counted=1",
        weeks,
    ):
        e = cost.setdefault(oid, [0.0, 0, 0])
        e[0] += (rev - margin) / max(1, lp)
        e[1] += 0 if ontime else 1
        e[2] += 1
    out = {}
    for rid, opts in table.items():
        o = {k: [round(v[0], 3), round(v[1], 3)] for k, v in opts.items()}
        e = cost.get(rid)
        if e:
            o["_c"] = [round(e[0] / e[2], 3), round(e[1] / e[2], 2), e[2]]
        out[rid] = o
    sig = {r: lists[r] for r in sorted(lists)[:10]}
    return {"seed": seed, "weeks": len(weeks), "sig": sig, "req": out}


if __name__ == "__main__":
    for seed in sys.argv[1:] or ["spread-1"]:
        data = build(seed)
        (HERE / f"table-{seed}.json").write_text(json.dumps(data, separators=(",", ":")))
        print(seed, data["weeks"], "weeks", len(data["req"]), "requests")
