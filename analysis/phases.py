"""When in the week a change of bidprice earns or loses its money (issue #233).

Reads saved level 8 weeks of the TypeScript `bidprice` and `phased` strategies, and for each prints the margin of the
orders won before and after a split hour, with the orders won, the late ones and the trust the dealers hold at the
split. A `phased` week is the same week as its first params up to its switch (a practice world is deterministic), so
the difference after the switch is what the second params, or the state the first params left, earned.

    uv run python -m analysis.phases                 # every bidprice and phased week of spread-6, 7, 8 and 10
    uv run python -m analysis.phases --split 24      # split at hour 24 instead of 48
    uv run python -m analysis.phases --seeds spread-8

It plays nothing online.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
from pathlib import Path

RUNS = Path("data/scrape/runs/L8")
TRUST_CAP = 25
# The params that tell the configs of #222 and #233 apart; the rest are those of board.json.
FLAGS = ("trustGuard", "trustValue", "trustUntil", "pairs")


def label(settings: dict) -> str | None:
    """A short name for the week's params, or None for a week outside these experiments."""
    params = settings.get("params") or {}
    if params.get("costScale") != 1.2 or params.get("minValueCents") != 60 or not params.get("lateRisk"):
        return None

    def name(p: dict) -> str:
        parts = []
        if p.get("trustGuard", 0) > 0:
            parts.append("guard")
        if p.get("trustValue", 0) > 0:
            parts.append("focus2" if p["trustValue"] > 1 else "focus")
        if p.get("pairs"):
            parts.append("chains")
        return "+".join(parts) or "board"

    if settings.get("strategy") == "bidprice":
        return name(params)
    if settings.get("strategy") != "phased":
        return None
    later = json.loads(Path(params["phaseFile"]).read_text()) if params.get("phaseFile") else {}
    return f"{name(params)} > {name({**params, **later})} @{params.get('phaseHour', 0):g}h"


def week(folder: Path, split: int) -> dict:
    """The week's margin, orders and late orders by whether the order was won before the split minute, and the trust
    counted as the dealers count it (RULES.md): +1 an order on time up to 25, halved by a late one."""
    won: dict[str, tuple[int, str]] = {}
    cents: collections.Counter[str] = collections.Counter()
    late: set[str] = set()
    trust: collections.Counter[str] = collections.Counter()
    requests: collections.Counter[str] = collections.Counter()
    unsettled: dict[str, int] = {}
    settled: set[str] = set()
    at_split: dict[str, int] | None = None
    lost_points = [0, 0]
    other = 0
    with gzip.open(folder / "events.jsonl.gz", "rt") as lines:
        for text in lines:
            event = json.loads(text)
            at = event["at"]
            for order, minute in list(unsettled.items()):
                if minute < at:
                    del unsettled[order]
                    if order not in settled:
                        settled.add(order)
                        dealer = won[order][1]
                        trust[dealer] = min(TRUST_CAP, trust[dealer] + 1)
            if at_split is None and at >= split:
                at_split = dict(trust)
            kind = event["kind"]
            if kind == "price_request":
                requests[event["request"]["dealerId"]] += 1
            elif kind == "order_won":
                won[event["order"]["id"]] = (at, event["order"]["dealerId"])
            elif kind == "ledger":
                line = event["line"]
                order = line.get("orderId")
                if not order or order not in won:
                    other += line["cents"]  # a line of no one order, as the fee of a gig with two orders
                    continue
                cents[order] += line["cents"]
                if line["kind"] == "revenue" and order not in settled:
                    unsettled[order] = at
                elif line["kind"] in ("late_refund", "undelivered_penalty") and order not in settled:
                    unsettled.pop(order, None)
                    settled.add(order)
                    late.add(order)
                    dealer = won[order][1]
                    lost_points[at >= split] += trust[dealer] - trust[dealer] // 2
                    trust[dealer] //= 2
    at_split = at_split or dict(trust)
    ranked = [dealer for dealer, _ in requests.most_common()]
    out = {
        "top": at_split.get(ranked[0], 0),
        "top5": sum(at_split.get(d, 0) for d in ranked[:5]),
        "other": other / 100,
    }
    for part, name in ((False, "before"), (True, "after")):
        ids = [order for order, (minute, _) in won.items() if (minute >= split) == part]
        out[name] = {
            "margin": sum(cents[order] for order in ids) / 100,
            "orders": len(ids),
            "late": sum(order in late for order in ids),
            "lost": lost_points[part],
        }
    return out


def total(r: dict) -> float:
    return r["before"]["margin"] + r["after"]["margin"] + r["other"]


def row(name: str, by: dict[str, dict], base: dict[str, dict]) -> str:
    """One config's line: its means over its seeds, and its differences to board over the seeds both have."""
    shared = [seed for seed in by if seed in base]

    def mean(get) -> float:
        return sum(get(r) for r in by.values()) / max(1, len(by))

    def delta(get) -> float:
        return sum(get(by[seed]) - get(base[seed]) for seed in shared) / max(1, len(shared))

    def part(name: str) -> str:
        return (
            f" {mean(lambda r: r[name]['margin']):>8.0f} {delta(lambda r: r[name]['margin']):>+6.0f}"
            f" {mean(lambda r: r[name]['orders']):>6.0f} {mean(lambda r: r[name]['late']):>5.1f} |"
        )

    return (
        f"{name:34} {len(by):>2} {mean(total):>8.0f} {delta(total):>+9.0f} |{part('before')}{part('after')}"
        f" {mean(lambda r: r['top']):>8.1f} {mean(lambda r: r['top5']):>9.1f} {mean(lambda r: r['after']['lost']):>10.1f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--seeds", default="spread-6,spread-7,spread-8,spread-10")
    parser.add_argument("--split", type=float, default=48, help="the split, in hours from Monday 00:00")
    args = parser.parse_args()
    seeds = args.seeds.split(",")
    split = int(args.split * 60)
    # The latest saved week of each config and seed.
    weeks: dict[str, dict[str, tuple[str, Path]]] = collections.defaultdict(dict)
    for seed in seeds:
        for meta_file in sorted((RUNS / seed).glob("*/meta.json")):
            meta = json.loads(meta_file.read_text())
            if meta.get("kind") != "practice" or not str(meta.get("policy", "")).startswith("ts-"):
                continue
            name = label(meta.get("settings") or {})
            if name is None:
                continue
            stamp = meta.get("playedAt") or meta.get("savedAt") or str(meta_file.stat().st_mtime)
            if seed not in weeks[name] or stamp >= weeks[name][seed][0]:
                weeks[name][seed] = (stamp, meta_file.parent)
    rows = {name: {seed: week(folder, split) for seed, (_, folder) in by.items()} for name, by in weeks.items()}
    base = rows.get("board", {})
    hour = f"{args.split:g}h"
    print(f"Mean over the seeds each config has; margin of the orders won before and after hour {args.split:g}.")
    print(
        f"{'config':34} {'n':>2} {'total':>8} {'vs board':>9} | {'before':>8} {'d':>6} {'orders':>6} {'late':>5} |"
        f" {'after':>8} {'d':>6} {'orders':>6} {'late':>5} | {'top@' + hour:>8} {'top5@' + hour:>9} {'lost after':>10}"
    )
    for name in sorted(rows, key=lambda n: (n != "board", n)):
        print(row(name, rows[name], base))
    print("\nBy seed: total margin, and after-split margin against board.")
    for name in sorted(rows, key=lambda n: (n != "board", n)):
        cells = []
        for seed in seeds:
            r = rows[name].get(seed)
            if not r:
                cells.append(f"{'':>16}")
                continue
            d = r["after"]["margin"] - base[seed]["after"]["margin"] if seed in base else 0
            cells.append(f"{total(r):>8.0f} ({d:>+5.0f})")
        print(f"{name:34} " + " ".join(cells))


if __name__ == "__main__":
    main()
