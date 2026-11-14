#!/usr/bin/env python3
"""Unifies every measured probe flip of Spread (level 8) into two flat files: quote_flips.csv and fee_flips.csv.

    python3 ml/build_flips.py                      # probe, probe2, probe3 and passive next to ml/
    python3 ml/build_flips.py probe2 probe3 --context passive --out ml

Each source folder is searched for
  * the new format of sim/prober.ts: <folder>/{quote,fee}/L8/<seed>/probes.jsonl (+ events.jsonl.gz, drivers.json),
  * the old format of tools/probe.py: {quote,fee}-L8-<seed>.jsonl anywhere below the folder.
A --context folder holds saved weeks (<folder>/L8/<seed>/events.jsonl.gz, drivers.json.gz). The requests of a week
depend only on level and seed, so such a week supplies the request fields the old format did not save. A context
request is used only when its dealer, arrival minute, lane and list price (quote) agree with the probe row.

Sources are read-only. A line that is not JSON (the last line of a file still being written) is skipped, and a
seed folder without events.jsonl.gz yet gets empty cells for what only the events hold. Standard library only.
"""

import argparse
import csv
import gzip
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

LEVEL = 8
HERE = Path(__file__).resolve().parent
OLD_FILE = re.compile(r"(quote|fee)-L(\d+)-(.+)\.jsonl$")

QUOTE_COLUMNS = (
    "source, seed, request_id, option, dealer_id, arrived_at, day, minute_of_day, pickup_place, delivery_place, km, "
    "drive_minutes, legs, private_pickup, private_delivery, premium, electric, has_note, batch_size, options_offered, "
    "list_price_cents, reference_fee_cents, hours_to_deadline, n_drivers, dealer_on_time, dealer_late, dealer_won, "
    "dealer_lost, flip_ratio, bracket_low_ratio, bracket_high_ratio, ends, monotone"
).split(", ")
FEE_COLUMNS = (
    "source, seed, order_id, option, dealer_id, at, day, minute_of_day, pickup_place, delivery_place, km, "
    "drive_minutes, legs, private_pickup, private_delivery, premium, electric, ready_at, last_pickup_at, deadline, "
    "reference_fee_cents, window_minutes, n_drivers, drivers_home_pickup, drivers_home_delivery, load_open, "
    "load_booked, load_orders, flip_ratio, bracket_low_ratio, bracket_high_ratio, ends, monotone, booked_driver_id, "
    "booked_driver_home, booked_minutes, booked_views"
).split(", ")


def read_text(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return f.read()
    return path.read_text(encoding="utf-8")


def json_lines(path: Path) -> tuple[list[dict], int]:
    """The JSON objects of a .jsonl(.gz) file and the number of lines that did not parse."""
    rows, bad = [], 0
    try:
        text = read_text(path)
    except (OSError, EOFError, gzip.BadGzipFile, UnicodeDecodeError):
        return rows, 1
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            bad += 1
    return rows, bad


class World:
    """What one saved world (a seed folder) says about its requests and drivers. Either part may be missing."""

    def __init__(self, folder: Path | None):
        self.requests: dict[str, dict] = {}  # request id -> the request of its price_request event
        self.batches: Counter = Counter()  # batch id -> requests in it
        self.homes: dict[str, str] | None = None  # driver id -> home place, None when there is no driver list
        self.has_events = False
        if folder is None:
            return
        for name in ("events.jsonl.gz", "events.jsonl"):
            if (folder / name).is_file():
                events, _ = json_lines(folder / name)
                for e in events:
                    if e.get("kind") == "price_request" and isinstance(e.get("request"), dict):
                        q = e["request"]
                        self.requests[q["id"]] = q
                        if q.get("batchId"):
                            self.batches[q["batchId"]] += 1
                self.has_events = bool(events)
                break
        for name in ("drivers.json", "drivers.json.gz"):
            if (folder / name).is_file():
                try:
                    drivers = json.loads(read_text(folder / name))
                except (OSError, EOFError, ValueError):
                    continue
                if isinstance(drivers, dict):
                    drivers = drivers.get("drivers")
                if isinstance(drivers, list):
                    self.homes = {d["id"]: d.get("homePlaceId") for d in drivers if isinstance(d, dict) and "id" in d}
                    break

    def n_drivers(self):
        return None if self.homes is None else len(self.homes)

    def at_home(self, place):
        return None if self.homes is None or place is None else sum(1 for h in self.homes.values() if h == place)

    def home(self, driver_id):
        return None if self.homes is None or driver_id is None else self.homes.get(driver_id)

    def batch_size(self, batch_id, known: bool):
        """Requests of the batch in this world; 1 for a request outside any batch. None when it cannot be told."""
        if known and not batch_id:
            return 1
        return self.batches[batch_id] if self.has_events and batch_id in self.batches else None


def flag(value):
    return None if value is None else int(bool(value))


def clock(at):
    """(day 0-4, minute of the day) of a minute counted from Monday 00:00."""
    return (None, None) if at is None else (int(at) // 1440, int(at) % 1440)


def ratio(cents, base):
    return None if cents is None or not base else cents / base


def request_fields(q: dict | None) -> dict:
    """The fields of a price_request's request (or an order, which has the same legs) that a probe row may lack."""
    if not q:
        return {}
    legs = q.get("legs") or []
    first = legs[0] if legs else {}
    return {
        "legs": len(legs) or None,
        "pickup_place": first.get("pickup", {}).get("placeId"),
        "delivery_place": first.get("delivery", {}).get("placeId"),
        "private_pickup": flag(first.get("pickup", {}).get("privateAddress")),
        "private_delivery": flag(first.get("delivery", {}).get("privateAddress")),
        "premium": flag(any(l.get("car", {}).get("premium") for l in legs)) if legs else None,
        "electric": flag(any(l.get("car", {}).get("electric") for l in legs)) if legs else None,
        "has_note": int(bool((q.get("note") or {}).get("text"))),
        "ready_at": first.get("pickup", {}).get("window", {}).get("from"),
        "options_offered": len(q["options"]) if q.get("options") else None,
        "deadlines": {o["kind"]: o.get("deadline") for o in q.get("options") or []},
    }


def first_lane(lane):
    """(pickup, delivery, legs) of a lane saved as [[pickup, delivery], ...] (new) or [pickup, delivery] (old)."""
    if not lane:
        return None, None, None
    if isinstance(lane[0], list):
        return lane[0][0], lane[0][1], len(lane)
    return lane[0], lane[1], None


def flip_fields(flip, low, high, ends, monotone, trial_ratios) -> dict:
    """The flip and its bracket as ratios. Outside the searched range the bracket has one side: the highest value
    tried when the flip is above it, the lowest when it is below."""
    if ends == "above":
        flip, low, high = None, max(trial_ratios, default=None), None
    elif ends == "below":
        flip, low, high = None, None, min(trial_ratios, default=None)
    return {
        "flip_ratio": flip,
        "bracket_low_ratio": low,
        "bracket_high_ratio": high,
        "ends": ends,
        "monotone": flag(monotone),
    }


def road_fields(roads, pickup, delivery) -> dict:
    road = roads.get((pickup, delivery))
    return {"km": road["km"] if road else None, "drive_minutes": road["minutes"] if road else None}


# ---------- the new format (sim/prober.ts) ----------
def new_quote(row, world: World, source, seed, roads) -> dict:
    ctx = request_fields(world.requests.get(row["requestId"]))
    pickup, delivery, legs = first_lane(row.get("lane"))
    private = (row.get("private") or [[None, None]])[0]
    at = row.get("at")
    day, minute = clock(at)
    base = row.get("listPriceCents")
    deadline = ctx.get("deadlines", {}).get(row["option"])
    dealer = row.get("dealer") or {}
    bracket = row.get("bracket") or [None, None]
    return {
        "source": source,
        "seed": seed,
        "request_id": row["requestId"],
        "option": row["option"],
        "dealer_id": row.get("dealerId"),
        "arrived_at": at,
        "day": day,
        "minute_of_day": minute,
        "pickup_place": pickup,
        "delivery_place": delivery,
        **road_fields(roads, pickup, delivery),
        "legs": row.get("legs") or legs,
        "private_pickup": flag(private[0]),
        "private_delivery": flag(private[1]),
        "premium": ctx.get("premium"),
        "electric": ctx.get("electric"),
        "has_note": int(bool(row["note"])) if "note" in row else ctx.get("has_note"),
        "batch_size": world.batch_size(row.get("batchId"), "batchId" in row),
        "options_offered": len(row["options"]) if row.get("options") else ctx.get("options_offered"),
        "list_price_cents": base,
        "reference_fee_cents": row.get("referenceFeeCents"),
        "hours_to_deadline": None if deadline is None or at is None else (deadline - at) / 60,
        "n_drivers": world.n_drivers(),
        "dealer_on_time": dealer.get("onTime"),
        "dealer_late": dealer.get("late"),
        "dealer_won": dealer.get("won"),
        "dealer_lost": dealer.get("lost"),
        # x is already price / list price; a trial is "high" when the dealer did not take the price
        **flip_fields(
            row.get("flip"),
            bracket[0],
            bracket[1],
            row.get("ends"),
            row.get("monotone"),
            [t["x"] for t in row.get("trials") or []],
        ),
    }


def new_fee(row, world: World, source, seed, roads) -> dict:
    ctx = request_fields(world.requests.get(row["orderId"]))
    pickup, delivery, legs = first_lane(row.get("lane"))
    private = (row.get("private") or [[None, None]])[0]
    at = row.get("at")
    day, minute = clock(at)
    load = row.get("load") or {}
    bracket = row.get("bracket") or [None, None]
    trials = row.get("trials") or []
    booked = min((t for t in trials if t.get("high")), key=lambda t: t["x"], default={})
    return {
        "source": source,
        "seed": seed,
        "order_id": row["orderId"],
        "option": row.get("option"),
        "dealer_id": row.get("dealerId"),
        "at": at,
        "day": day,
        "minute_of_day": minute,
        "pickup_place": pickup,
        "delivery_place": delivery,
        **road_fields(roads, pickup, delivery),
        "legs": legs,
        "private_pickup": flag(private[0]),
        "private_delivery": flag(private[1]),
        "premium": flag(row["premium"]) if "premium" in row else ctx.get("premium"),
        "electric": flag(row["electric"]) if "electric" in row else ctx.get("electric"),
        "ready_at": row["readyAt"] if "readyAt" in row else ctx.get("ready_at"),
        "last_pickup_at": row.get("lastPickupAt"),
        "deadline": row.get("deadline"),
        "reference_fee_cents": row.get("referenceFeeCents"),
        "window_minutes": row.get("windowMinutes"),
        "n_drivers": world.n_drivers(),
        "drivers_home_pickup": world.at_home(pickup),
        "drivers_home_delivery": world.at_home(delivery),
        "load_open": load.get("open"),
        "load_booked": load.get("booked"),
        "load_orders": load.get("orders"),
        **flip_fields(
            row.get("flip"), bracket[0], bracket[1], row.get("ends"), row.get("monotone"), [t["x"] for t in trials]
        ),
        "booked_driver_id": booked.get("driverId"),
        "booked_driver_home": world.home(booked.get("driverId")),
        "booked_minutes": booked.get("minutes"),
        "booked_views": booked.get("views"),
    }


# ---------- the old format (tools/probe.py) ----------
# quote: "false" = lost at both ends of the range (the flip is below it), "true" = won at both (above it).
# fee: "never" = unbooked even at the top fee (above), "always" = booked even at the lowest (below).
OLD_ENDS = {"quote": {"false": "below", "true": "above"}, "fee": {"never": "above", "always": "below"}}


def old_flip(mode, row, base) -> dict | None:
    ends = row.get("ends")
    if ends is not None:
        ends = OLD_ENDS[mode].get(ends)
        if ends is None:  # "inverted" or unknown: not a measurement
            return None
    elif row.get("flipCents") is None:
        return None
    bracket = row.get("bracketCents") or [None, None]
    trials = [ratio(t[0], base) for t in row.get("trials") or [] if isinstance(t, list) and t]
    flip = row.get("flipRatio")
    if flip is None:
        flip = ratio(row.get("flipCents"), base)
    return flip_fields(
        flip,
        ratio(bracket[0], base),
        ratio(bracket[1], base),
        ends,
        row.get("monotone"),
        [t for t in trials if t is not None],
    )


def matching_request(world: World, request_id, row, at, option=None) -> dict | None:
    """The context world's request of this id, when it is the same request as the probe row's."""
    q = world.requests.get(request_id)
    if not q:
        return None
    lane = row.get("lane") or [None, None]
    legs = q.get("legs") or [{}]
    same = (
        q.get("dealerId") == row.get("dealerId")
        and legs[0].get("pickup", {}).get("placeId") == lane[0]
        and legs[0].get("delivery", {}).get("placeId") == lane[1]
        and q.get("referenceFeeCents") == row.get("referenceFeeCents")
    )
    if option is not None:  # a quote probe: the request arrived at this minute with this list price
        prices = {o["kind"]: o.get("listPriceCents") for o in q.get("options") or []}
        same = same and q.get("arrivedAt") == at and prices.get(option) == row.get("listPriceCents")
    else:  # a fee probe: the order was won after the request arrived
        same = same and at is not None and q.get("arrivedAt", 10**9) <= at
    return q if same else None


def old_quote(row, world: World, source, seed, roads, stats) -> dict | None:
    base = row.get("listPriceCents")
    flip = old_flip("quote", row, base)
    if flip is None:
        return None
    at = row.get("arrivedAt")
    q = matching_request(world, row["requestId"], row, at, row["option"])
    stats["matched" if q else "unmatched"] += 1
    ctx = request_fields(q)
    pickup, delivery, _ = first_lane(row.get("lane"))
    day, minute = clock(at)
    deadline = ctx.get("deadlines", {}).get(row["option"])
    return {
        "source": source,
        "seed": seed,
        "request_id": row["requestId"],
        "option": row["option"],
        "dealer_id": row.get("dealerId"),
        "arrived_at": at,
        "day": day,
        "minute_of_day": minute,
        "pickup_place": pickup,
        "delivery_place": delivery,
        **road_fields(roads, pickup, delivery),
        "legs": row.get("legs"),
        "private_pickup": ctx.get("private_pickup"),
        "private_delivery": ctx.get("private_delivery"),
        "premium": ctx.get("premium"),
        "electric": ctx.get("electric"),
        "has_note": ctx.get("has_note"),
        "batch_size": world.batch_size(q.get("batchId"), True) if q else None,
        "options_offered": len(row["options"]) if row.get("options") else ctx.get("options_offered"),
        "list_price_cents": base,
        "reference_fee_cents": row.get("referenceFeeCents"),
        "hours_to_deadline": None if deadline is None or at is None else (deadline - at) / 60,
        "n_drivers": world.n_drivers(),
        # the old probe did not save what the dealer had seen of us: left empty
        **flip,
    }


def old_fee(row, world: World, source, seed, roads, stats) -> dict | None:
    base = row.get("referenceFeeCents")
    flip = old_flip("fee", row, base)
    if flip is None:
        return None
    at = row.get("wonAt")
    q = matching_request(world, row["orderId"], row, at)
    stats["matched" if q else "unmatched"] += 1
    ctx = request_fields(q)
    pickup, delivery, _ = first_lane(row.get("lane"))
    day, minute = clock(at)
    booked = row.get("atFlip") or {}
    return {
        "source": source,
        "seed": seed,
        "order_id": row["orderId"],
        "option": row.get("option"),
        "dealer_id": row.get("dealerId"),
        "at": at,
        "day": day,
        "minute_of_day": minute,
        "pickup_place": pickup,
        "delivery_place": delivery,
        **road_fields(roads, pickup, delivery),
        "legs": row.get("legs"),
        "private_pickup": ctx.get("private_pickup"),
        "private_delivery": ctx.get("private_delivery"),
        "premium": flag(row["premium"]) if row.get("premium") is not None else ctx.get("premium"),
        "electric": ctx.get("electric"),
        "ready_at": ctx.get("ready_at"),
        "last_pickup_at": row.get("lastPickupAt"),
        "deadline": row.get("deadline"),
        "reference_fee_cents": base,
        "window_minutes": row.get("windowMinutes"),
        "n_drivers": world.n_drivers(),
        "drivers_home_pickup": world.at_home(pickup),
        "drivers_home_delivery": world.at_home(delivery),
        **flip,
        "booked_driver_id": booked.get("driverId"),
        "booked_driver_home": world.home(booked.get("driverId")),
        "booked_minutes": booked.get("minutes"),
        "booked_views": booked.get("views"),
    }


# ---------- main ----------
def load_roads(folders: list[Path], given: Path | None) -> dict:
    candidates = [given] if given else []
    candidates += [HERE.parent / "runs" / "map.json"] + [f / "map.json" for f in folders]
    for path in candidates:
        if path and path.is_file():
            roads = json.loads(path.read_text())["roads"]
            return {(r["from"], r["to"]): r for r in roads}
    sys.exit("no map.json found: pass --map")


def percentile(values: list[float], p: float) -> float:
    values = sorted(values)
    k = (len(values) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def cell(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(round(value, 6))
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folders", nargs="*", type=Path, help="probe output folders (default: probe probe2 probe3)")
    parser.add_argument("--context", nargs="*", type=Path, help="folders of saved weeks, for the old format")
    parser.add_argument("--map", type=Path, help="map.json (default: runs/map.json)")
    parser.add_argument("--out", type=Path, default=HERE, help="where the two CSV files go (default: next to this)")
    args = parser.parse_args()
    data = HERE.parent
    folders = args.folders or [p for p in (data / "probe", data / "probe2", data / "probe3") if p.is_dir()]
    contexts = args.context if args.context is not None else [p for p in (data / "passive",) if p.is_dir()]
    roads = load_roads(folders, args.map)

    rows = {"quote": {}, "fee": {}}  # mode -> (seed, id, option) -> row
    counts = {"quote": Counter(), "fee": Counter()}
    notes: list[str] = []
    context_worlds: dict[str, World] = {}

    def context(seed: str) -> World:
        if seed not in context_worlds:
            folder = next((c / f"L{LEVEL}" / seed for c in contexts if (c / f"L{LEVEL}" / seed).is_dir()), None)
            context_worlds[seed] = World(folder)
        return context_worlds[seed]

    def add(mode, row, key):
        if row is None:
            return
        if key in rows[mode]:
            counts[mode]["duplicate"] += 1
            return
        rows[mode][key] = row
        counts[mode][row["source"]] += 1

    for folder in folders:
        source = folder.resolve().name
        if not folder.is_dir():
            notes.append(f"{folder}: not a folder, skipped")
            continue
        # the new format
        for mode in ("quote", "fee"):
            for path in sorted(folder.glob(f"{mode}/L{LEVEL}/*/probes.jsonl")):
                seed = path.parent.name
                probes, bad = json_lines(path)
                world = World(path.parent)
                missing = [n for n, ok in (("events", world.has_events), ("drivers", world.homes is not None)) if not ok]
                if bad or missing:
                    notes.append(
                        f"{source}/{mode}/{seed}: {bad} unreadable line(s)"
                        + (f", no {' or '.join(missing)} yet" if missing else "")
                    )
                for row in probes:
                    try:
                        if mode == "quote":
                            add(mode, new_quote(row, world, source, seed, roads), (seed, row["requestId"], row["option"]))
                        else:
                            add(mode, new_fee(row, world, source, seed, roads), (seed, row["orderId"], ""))
                    except (KeyError, TypeError, IndexError) as error:
                        counts[mode]["bad row"] += 1
                        notes.append(f"{source}/{mode}/{seed}: row skipped ({error!r})")
        # the old format
        for path in sorted(folder.rglob("*.jsonl")):
            match = OLD_FILE.fullmatch(path.name)
            if not match or int(match[2]) != LEVEL:
                continue
            mode, seed = match[1], match[3]
            probes, bad = json_lines(path)
            world, stats = context(seed), Counter()
            for row in probes:
                try:
                    if mode == "quote":
                        made, key = old_quote(row, world, source, seed, roads, stats), (seed, row["requestId"], row["option"])
                    else:
                        made, key = old_fee(row, world, source, seed, roads, stats), (seed, row["orderId"], "")
                except (KeyError, TypeError, IndexError) as error:
                    counts[mode]["bad row"] += 1
                    notes.append(f"{path.name}: row skipped ({error!r})")
                    continue
                if made is None:
                    counts[mode]["no measurement"] += 1
                add(mode, made, key)
            if bad or stats["unmatched"]:
                notes.append(
                    f"{path.name}: {bad} unreadable line(s), {stats['unmatched']} of "
                    f"{stats['matched'] + stats['unmatched']} rows without a matching context request"
                )

    args.out.mkdir(parents=True, exist_ok=True)
    for mode, columns in (("quote", QUOTE_COLUMNS), ("fee", FEE_COLUMNS)):
        out = args.out / f"{mode}_flips.csv"
        made = list(rows[mode].values())
        with open(out, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            for row in made:
                writer.writerow([cell(row.get(c)) for c in columns])
        print(f"{out}: {len(made)} rows")
        for source in sorted({r["source"] for r in made}):
            part = [r for r in made if r["source"] == source]
            print(f"  {source}: {len(part)} rows, {len({r['seed'] for r in part})} seeds")
        extra = {k: v for k, v in counts[mode].items() if k in ("duplicate", "bad row", "no measurement")}
        if extra:
            print(f"  left out: {extra}")
        inside = [r["flip_ratio"] for r in made if not r["ends"] and r["flip_ratio"] is not None]
        if inside:
            print(
                f"  flip_ratio inside the bracket (n={len(inside)}): median {statistics.median(inside):.4f}, "
                f"p10 {percentile(inside, 0.1):.4f}, p90 {percentile(inside, 0.9):.4f}"
            )
        if made:
            ends = Counter(r["ends"] or "inside" for r in made)
            print("  ends: " + ", ".join(f"{k} {v} ({100 * v / len(made):.1f}%)" for k, v in sorted(ends.items())))
            print(f"  not monotone: {sum(1 for r in made if r['monotone'] == 0)}")
            empty = {c: sum(1 for r in made if r.get(c) is None) for c in columns if c != "ends"}
            print("  empty cells: " + (", ".join(f"{c} {n}" for c, n in empty.items() if n) or "none"))
    for note in notes:
        print("note:", note)


if __name__ == "__main__":
    main()
