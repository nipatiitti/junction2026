#!/usr/bin/env python3
"""Builds one flat file of every recorded price quote from saved weeks of Spread (level 8).

    python3 build_quotes.py ROOT [ROOT ...] [--out quotes.csv.gz] [--map map.json] [--limit N] [--jobs 16]

One row per (week, request, option that was quoted). Decline quotes (price >= 5 x list) are skipped, and so are
requests that were never decided. Standard library only. Reads only; writes the output file.

Dealer state is taken in event order (seq) at the request's price_request event:
  dealer_on_time  the trust count of the rules: +1 (cap 25) for each order whose every leg was delivered by the
                  order's deadline (the latest order_changed deadline known when the last leg arrived); an order
                  completed late halves the count, rounded down
  dealer_late     orders completed late so far
  dealer_won/lost that dealer's requests already decided (order_won / order_lost events) before this arrival
  dealer_on_time_ledger, dealer_late_ledger
                  the same two counts by the world's own account, as analysis/facts.py does: an order completes at
                  its revenue line and is late when it has a late_refund line. The world also counts an order late
                  when it misses a note's deadline or a customer's slot, which the order's deadline does not show.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import sys
import time
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
DAY = 1440
DECLINE_RATIO = 5.0
TRUST_CAP = 25
COLUMNS = [
    "seed", "world_id", "policy", "request_id", "option", "dealer_id", "arrived_at", "day", "minute_of_day",
    "pickup_place", "delivery_place", "km", "drive_minutes", "legs", "private_pickup", "private_delivery",
    "premium", "electric", "has_note", "batch_size", "options_offered", "list_price_cents",
    "reference_fee_cents", "hours_to_deadline", "n_drivers", "dealer_on_time", "dealer_late", "dealer_won",
    "dealer_lost", "quote_cents", "ratio", "n_options_quoted", "min_ratio_quoted", "outcome",
    "dealer_on_time_ledger", "dealer_late_ledger",
]  # fmt: skip

ROADS: dict = {}


def read_json(path: Path):
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(path.read_text())


def init(map_path: str) -> None:
    global ROADS
    world = read_json(Path(map_path))
    ROADS = {(r["from"], r["to"]): (r["km"], r["minutes"]) for r in world["roads"]}


def dealer_states(events_path: Path) -> tuple[dict, dict]:
    """One pass over the events in seq order. Returns the dealer state at each price_request, by request id,
    and the (at, state) history per dealer for requests that have no price_request event."""
    dealer_of, deadline, n_legs, done = {}, {}, {}, {}
    finished = set()
    # on_time (trust), late, won, lost, then on_time and late by the ledger
    state = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
    at_arrival = {}
    decided = set()
    events = []
    with gzip.open(events_path, "rt", encoding="utf-8") as f:
        for line in f:
            if '"gig_viewed"' not in line:  # the bulk of a week, never needed here
                events.append(json.loads(line))
    refunded = {e["line"]["orderId"] for e in events if e["kind"] == "ledger" and e["line"]["kind"] == "late_refund"}
    paid = set()
    for e in events:
        kind = e["kind"]
        if kind == "price_request":
            r = e["request"]
            dealer_of[r["id"]] = r["dealerId"]
            at_arrival.setdefault(r["id"], tuple(state[r["dealerId"]]))
        elif kind in ("order_won", "order_changed"):
            o = e["order"]
            oid = o["id"]
            dealer_of.setdefault(oid, o["dealerId"])
            deadline[oid] = o["deadline"]
            n_legs[oid] = len(o["legs"])
            if kind == "order_won" and oid not in decided:
                decided.add(oid)
                state[o["dealerId"]][2] += 1
        elif kind == "order_lost":
            rid = e["requestId"]
            if rid not in decided and rid in dealer_of:
                decided.add(rid)
                state[dealer_of[rid]][3] += 1
        elif kind == "delivered":
            oid = e["orderId"]
            if oid in finished or oid not in deadline:
                continue
            legs = done.setdefault(oid, {})
            legs[e["leg"]] = e["at"]
            if len(legs) >= n_legs[oid]:
                finished.add(oid)
                s = state[dealer_of[oid]]
                if max(legs.values()) <= deadline[oid]:
                    s[0] = min(TRUST_CAP, s[0] + 1)
                else:
                    s[0] //= 2
                    s[1] += 1
        elif kind == "ledger" and e["line"]["kind"] == "revenue":
            oid = e["line"]["orderId"]
            if oid in paid or oid not in dealer_of:
                continue
            paid.add(oid)
            s = state[dealer_of[oid]]
            if oid in refunded:
                s[4] //= 2
                s[5] += 1
            else:
                s[4] = min(TRUST_CAP, s[4] + 1)
    return at_arrival, decided


def week_rows(folder: str) -> tuple[str, str, list]:
    """(status, world id, rows) of one week folder. status is 'ok' or the reason it gave no rows."""
    try:
        path = Path(folder)
        meta = read_json(path / "meta.json")
        if meta.get("level") != 8:
            return "not level 8", meta.get("worldId", ""), []
        if not (path / "reveal.json.gz").exists():
            return "no reveal file", meta["worldId"], []
        if not (path / "events.jsonl.gz").exists():
            return "no events file", meta["worldId"], []
        revealed = read_json(path / "reveal.json.gz").get("requests") or []
        if not any(item.get("quote") for item in revealed):
            return "no quotes in the reveal", meta["worldId"], []
        drivers_path = path / "drivers.json.gz"
        n_drivers = len(read_json(drivers_path)) if drivers_path.exists() else ""
        at_arrival, _decided = dealer_states(path / "events.jsonl.gz")
        batches = Counter(i["request"]["batchId"] for i in revealed if i["request"].get("batchId") is not None)
        head = [meta["seed"], meta["worldId"], meta.get("policy") or ("prober-" + str(meta.get("mode", "")))]
        out = []
        for item in revealed:
            r, quote, outcome = item["request"], item.get("quote") or {}, item.get("outcome")
            if not quote or outcome not in ("won", "lost"):
                continue  # not quoted, never decided, or cancelled before a decision
            state = at_arrival.get(r["id"])
            if state is None:
                continue  # no price_request event: the dealer state at arrival is unknown
            quoted = []
            for o in r["options"]:
                cents = quote.get(o["kind"])
                if cents is None or not o["listPriceCents"]:
                    continue
                ratio = cents / o["listPriceCents"]
                if ratio >= DECLINE_RATIO:
                    continue
                quoted.append((o, cents, ratio))
            if not quoted:
                continue
            legs = r["legs"]
            p, d = legs[0]["pickup"], legs[0]["delivery"]
            km, minutes = ROADS.get((p["placeId"], d["placeId"]), ("", ""))
            arrived = r["arrivedAt"]
            base = [
                r["id"], None, r["dealerId"], arrived, arrived // DAY, arrived % DAY,
                p["placeId"], d["placeId"], km, minutes, len(legs),
                int(any(x["pickup"]["privateAddress"] for x in legs)),
                int(any(x["delivery"]["privateAddress"] for x in legs)),
                int(any(x["car"]["premium"] for x in legs)),
                int(any(x["car"]["electric"] for x in legs)),
                int(r.get("note") is not None),
                batches[r["batchId"]] if r.get("batchId") is not None else 1,
                "|".join(o["kind"] for o in r["options"]),
            ]  # fmt: skip
            min_ratio = round(min(q[2] for q in quoted), 5)
            for o, cents, ratio in quoted:
                if outcome == "lost":
                    result = "lost"
                else:
                    result = "won" if item.get("option") == o["kind"] else "won_other"
                row = head + base + [
                    o["listPriceCents"], r["referenceFeeCents"], round((o["deadline"] - arrived) / 60, 3),
                    n_drivers, *state[:4], cents, round(ratio, 5), len(quoted), min_ratio, result, *state[4:],
                ]  # fmt: skip
                row[4] = o["kind"]
                out.append(row)
        if not out:
            return "no decided, non-decline quotes", meta["worldId"], []
        return "ok", meta["worldId"], out
    except Exception as error:  # a folder that fails to parse is counted, and the run goes on
        return f"parse error: {type(error).__name__}", folder, []


def find_weeks(roots: list[str]) -> list[str]:
    found = []
    for root in roots:
        for here, dirs, files in os.walk(root):
            dirs.sort()
            if "meta.json" in files:
                found.append(here)
                dirs[:] = []
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("roots", nargs="+", help="folders that hold saved weeks")
    parser.add_argument("--out", default=str(HERE / "quotes.csv.gz"))
    parser.add_argument("--map", default=str(HERE.parent / "runs" / "map.json"))
    parser.add_argument("--limit", type=int, default=0, help="read only the first N week folders")
    parser.add_argument("--jobs", type=int, default=16)
    args = parser.parse_args()
    start = time.time()
    folders = find_weeks(args.roots)
    if args.limit:
        folders = folders[: args.limit]
    status, seen, rows_written = Counter(), set(), 0
    failed = []
    with Pool(args.jobs, init, (args.map,)) as pool, gzip.open(args.out, "wt", newline="", compresslevel=5) as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for folder, (state, world_id, rows) in zip(folders, pool.imap(week_rows, folders, chunksize=4)):
            if state == "ok" and world_id in seen:
                state = "duplicate world id"
            status[state] += 1
            if state.startswith("parse error"):
                failed.append(folder)
            if state != "ok":
                continue
            seen.add(world_id)
            writer.writerows(rows)
            rows_written += len(rows)
    print(f"{len(folders)} week folders, {status['ok']} with rows, {rows_written} rows -> {args.out}")
    for state, n in status.most_common():
        if state != "ok":
            print(f"  skipped {n}: {state}")
    for folder in failed[:10]:
        print(f"  failed: {folder}", file=sys.stderr)
    print(f"{time.time() - start:.0f} s")


if __name__ == "__main__":
    main()
