"""The bench behind the results in ../README.md: plays practice weeks with versions of the fee schedule on top of
this checkout's dispatch.py, sums each week's ledger (driver fees, refunds and penalties) beside the score, and adds
one JSON line per week to bench.jsonl. Every week is saved with record.Recorder, as dispatch.py saves its own.

    uv run python strategies/fees/results/bench.py VERSION[,VERSION...] [--seeds spread-1..5] [--level 8] [--jobs 5]
    uv run python strategies/fees/results/bench.py --table          # the README's table, from bench.jsonl

A version is a name in VERSIONS: `starter` plays the starter's rising and steep fees, the others play
strategies/fees with some of the constants of schedule.py changed. The weeks of one call play at once, up to
--jobs of them, each in its own process: the call is one online run, whatever --jobs.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESULTS = Path(__file__).resolve().parent / "bench.jsonl"
HOUR, DAY = 60, 24 * 60
# The kit's client reads SPREAD_URL and SPREAD_KEY. Behind the cloud session's proxy, which adds the team key, the key
# may be a placeholder.
os.environ.setdefault("SPREAD_URL", "https://spread.bahnexpress.com")
if os.environ.get("HTTPS_PROXY"):
    os.environ.setdefault("SPREAD_KEY", "placeholder-replaced-by-proxy")
NEVER = (30 * DAY, 30 * DAY)  # EARLY_RAISES that never come before the even times: the raises of v1 and v2

# The constants of schedule.py as merged in #15. Each version changes some of them.
PR15 = {
    "OPEN_BASE": 1.0,
    "OPEN_SCARCE": 0.3,
    "OPEN_EVENING": 0.1,
    "OPEN_SATURDAY": 0.15,
    "OPEN_LONG": 0.05,
    "OPEN_FLOOR": 1.0,
    "TOP": 2.0,
    "LATE_SHARE": 0.5,
    "RAISE_SHARES": (1 / 3, 2 / 3),
    "MARGIN_MIN": 3 * HOUR,
    "MARGIN_MAX": 6 * HOUR,
}
NO_PREMIUMS = {"OPEN_SCARCE": 0.0, "OPEN_EVENING": 0.0, "OPEN_SATURDAY": 0.0, "OPEN_LONG": 0.0}
V4 = {**PR15, "OPEN_FLOOR": 1.1, "MARGIN_MIN": 4 * HOUR, "LATE_SHARE": 0.75}
V8 = {**PR15, **NO_PREMIUMS, "MARGIN_MIN": 5 * HOUR, "LATE_SHARE": 0.75, "RAISE_SHARES": (0.1, 0.3)}
V9 = {**V8, "OPEN_BASE": 0.9, "OPEN_FLOOR": 0.9}
V13 = {**V9, "TOP": 2.5, "LATE_SHARE": 1.0}

# Each version: the constants of strategies/fees/schedule.py that it sets, or None for the starter's fees.
VERSIONS: dict[str, dict | None] = {
    "starter": None,
    "v1": {**PR15, "EARLY_RAISES": NEVER},
    "v2": {**V4, "EARLY_RAISES": NEVER},
    "v3": PR15,  # schedule.py as merged in #15
    "v4": V4,
    "v5": {**V4, "TOP": 2.5, "LATE_SHARE": 1.0},
    # Opening at the typical fee, without the premiums: the top fee of v4.
    "v6": {**V4, **NO_PREMIUMS, "OPEN_FLOOR": 1.0},
    # v6 with small early raises, about as far as the starter's: 1.1 and 1.3 times the typical fee.
    "v7": {**V4, **NO_PREMIUMS, "OPEN_FLOOR": 1.0, "RAISE_SHARES": (0.1, 0.3)},
    # v7 with the top fee due 5 hours or more before the last pickup.
    "v8": V8,
    # v8 opening at 0.9 times the typical fee: about the typical fee after an hour, 1.23 times after three.
    "v9": V9,
    # v8 with the premium where few drivers live near the pickup.
    "v10": {**V8, "OPEN_SCARCE": 0.3},
    # v9 with the premium where few drivers live near the pickup.
    "v11": {**V9, "OPEN_SCARCE": 0.3},
    # v9 spending what it saves on a top fee due 6 to 8 hours before the last pickup.
    "v12": {**V9, "MARGIN_MIN": 6 * HOUR, "MARGIN_MAX": 8 * HOUR},
    # v9 spending what it saves on the starter's top of 2.5 times the typical fee, under twice the price.
    "v13": V13,
    # v8 opening at 0.95 times the typical fee.
    "v14": {**V8, "OPEN_BASE": 0.95, "OPEN_FLOOR": 0.95},
    # v13 opening at 0.85 times the typical fee.
    "v15": {**V13, "OPEN_BASE": 0.85, "OPEN_FLOOR": 0.85},
    # v13 with the top fee of v12, due 6 to 8 hours before the last pickup: schedule.py since #62.
    "v16": {**V13, "MARGIN_MIN": 6 * HOUR, "MARGIN_MAX": 8 * HOUR},
}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()


def seeds_of(text: str) -> list[str]:
    """`spread-1..5` or `spread-1..spread-5` is a range; commas separate seeds."""
    seeds = []
    for part in text.split(","):
        if ".." in part:
            first, last = part.split("..")
            stem, start = first.rsplit("-", 1)
            seeds += [f"{stem}-{n}" for n in range(int(start), int(last.rsplit("-", 1)[-1]) + 1)]
        else:
            seeds.append(part)
    return seeds


def starter_fees(dispatch) -> None:
    """Puts the starter's fees back in dispatch.py: the typical fee plus 10% an hour up to 1.5 times, and from the
    deadline warning 1.5 times plus a quarter every half hour up to 2.5 times. No repricing after a drop."""
    Desk, raise_fees = dispatch.Desk, dispatch.Desk.raise_fees

    def rising(now: int, fee: float, level: int) -> list:
        return [
            {"at": now + k * HOUR, "feeCents": max(1, int(fee * (1 + k / 10) + 0.5))}
            for k in range(1 if level == 1 else 6)
        ]

    def steep(now: int, fee: float, level: int) -> list:
        return [
            {"at": now + k * 30, "feeCents": max(1, int(fee * (1.5 + k / 4) + 0.5))}
            for k in range(1 if level == 1 else 5)
        ]

    def urgent_raise(self, order_id: str) -> None:
        self.__dict__.setdefault("urgent", set()).add(order_id)
        raise_fees(self, order_id)

    def fees_for(self, order, cars: int) -> list:
        fee = self.requests[order["id"]]["referenceFeeCents"] * cars / len(order["legs"])
        urgent = order["id"] in self.__dict__.get("urgent", ())
        return (steep if urgent else rising)(self.now, fee, self.level)

    Desk.raise_fees, Desk.fees_for, Desk.dropped = urgent_raise, fees_for, lambda self, gig_id: None
    # A bundle of several orders' cars (strategies/bundling) goes at the rising fees of its typical fee.
    dispatch.fees_plan = lambda now, gig, level: rising(now, gig.typical, level)


def play(version: str, level: int, seed: str) -> dict:
    """Plays one week with the version, saves it, and sums its ledger."""
    sys.path.insert(0, str(ROOT))
    from spread.client import SpreadError

    import dispatch
    from record import Recorder
    from strategies.fees import schedule

    changes = VERSIONS[version]
    if changes is None:
        starter_fees(dispatch)
    for name, value in (changes or {}).items():
        assert hasattr(schedule, name), name
        setattr(schedule, name, value)
    client = dispatch.ProxyClient()
    while True:  # the team's 8 practice slots are shared: wait for one
        try:
            world = client.create(level=level, seed=seed)
            break
        except SpreadError as error:
            if error.status != 409:
                raise
            time.sleep(15)
    try:
        recorder = Recorder(world, level, seed, "practice")
        with contextlib.redirect_stdout(io.StringIO()):
            dispatch.play_practice(world, level)
    except BaseException:
        world.delete()
        raise
    score, events = world.score(), world.events()
    reveal = recorder.reveal() or {}
    with contextlib.redirect_stdout(sys.stderr):
        recorder.save()
    money, delivered, drops = Counter(), 0, 0
    for event in events:
        if event["kind"] == "ledger":
            money[event["line"]["kind"]] += event["line"]["cents"]
        delivered += event["kind"] == "delivered"
        drops += event["kind"] == "gig_dropped"
    # What drivers learn: per order, the booked fee over the first fee that a driver viewed.
    gig_order = {g["id"]: g["stops"][0]["orderId"] for g in world.snapshot()["gigs"]}
    first_view: dict = {}
    for view in sorted(reveal.get("views", []), key=lambda v: v["at"]):
        first_view.setdefault(gig_order.get(view["gigId"]), view["feeCents"])
    learned = sorted(
        e["feeCents"] / first_view.pop(gig_order[e["gigId"]])
        for e in events
        if e["kind"] == "gig_booked" and "feeCents" in e and gig_order.get(e["gigId"]) in first_view
    )
    return {
        "version": version,
        "main": git("merge-base", "HEAD", "origin/main")[:7],  # the latest main in this checkout
        "seed": seed,
        "world": world.id,
        "margin": score["marginCents"] / 100,
        "orders": score["wonOrders"],
        "onTime": round(score["onTimeShare"], 4),
        "undelivered": round(score["undeliveredShare"], 4),
        "fees": -money["driver_fee"] / 100,
        "feesPerDelivered": round(-money["driver_fee"] / 100 / max(1, delivered), 2),
        "refunds": -money["late_refund"] / 100,
        "penalties": -money["undelivered_penalty"] / 100,
        "revenue": money["revenue"] / 100,
        "cars": delivered,
        "drops": drops,
        "learnedRaise": round(learned[len(learned) // 2], 3) if learned else None,
    }


def bench(versions: list[str], seeds: list[str], level: int, jobs: int) -> None:
    """Plays each version on each seed, each week in its own process, and adds each week to bench.jsonl."""
    lock = threading.Lock()

    def one(version: str, seed: str) -> None:
        cmd = [sys.executable, __file__, "--one", version, seed, "--level", str(level)]
        done = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, text=True, check=False)
        if done.returncode != 0 or not done.stdout.strip():
            print(f"{version} {seed}: failed ({done.returncode})", file=sys.stderr, flush=True)
            return
        line = done.stdout.strip().splitlines()[-1]
        with lock:
            with RESULTS.open("a") as out:
                out.write(line + "\n")
            print(line, flush=True)

    with ThreadPoolExecutor(jobs) as pool:
        for future in [pool.submit(one, v, s) for v in versions for s in seeds]:
            future.result()


def table() -> str:
    """One line per version and set of seeds, over the main it ran on: the README's table."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for line in RESULTS.read_text().splitlines():
        row = json.loads(line)
        groups[(row.get("main", "#15"), row["version"])].append(row)
    lines = ["| Main | Version | Seeds | Margin | On time | Fees per delivered car | Refunds and penalties per car |"]
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for (main, version), rows in groups.items():
        cars, orders = sum(r["cars"] for r in rows), sum(r["orders"] for r in rows)
        on_time = sum(r["onTime"] * r["orders"] for r in rows) / orders
        seeds = ", ".join(r["seed"].removeprefix("spread-") for r in rows)
        lines.append(
            f"| {main} | `{version}` | {seeds} | €{sum(r['margin'] for r in rows):,.0f} | {on_time:.1%} "
            f"| €{sum(r['fees'] for r in rows) / cars:.2f} "
            f"| €{sum(r['refunds'] + r['penalties'] for r in rows) / cars:.2f} |"
        )
    return "\n".join(lines).replace("€-", "−€")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("versions", nargs="?", help="comma-separated names from VERSIONS")
    parser.add_argument("--seeds", default="spread-1..5")
    parser.add_argument("--level", type=int, default=8)
    parser.add_argument("--jobs", type=int, default=5, help="weeks at once, 1 to 8 (default 5)")
    parser.add_argument("--table", action="store_true", help="print the table of bench.jsonl and stop")
    parser.add_argument("--one", nargs=2, metavar=("VERSION", "SEED"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.table:
        print(table())
    elif args.one:
        print(json.dumps(play(args.one[0], args.level, args.one[1])), flush=True)
    else:
        versions = args.versions.split(",")
        unknown = [v for v in versions if v not in VERSIONS]
        if unknown:
            parser.error(f"unknown versions {unknown}; known: {', '.join(VERSIONS)}")
        bench(versions, seeds_of(args.seeds), args.level, max(1, min(8, args.jobs)))


if __name__ == "__main__":
    main()
