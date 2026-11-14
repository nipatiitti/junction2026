#!/usr/bin/env python3
"""One flat file of every order won (and not cancelled) in saved weeks of Spread, with what was known at the
quote and what the order cost afterwards.

    python3 build_orders.py ROOT [ROOT ...] [--out orders.csv.gz] [--map map.json] [--limit N] [--jobs 16]

A ROOT is any folder; every folder below it that holds meta.json + events.jsonl.gz + snapshot.json.gz is a week.
Standard library only. Reads only; writes the output file. Parsing follows build_quotes.py (request facts) and
build_spells.py (gigs, driver homes, open and booked gigs).

How the columns are made:
- request facts (places, km, flags, list price, typical fee, ready_at, deadline) come from the price_request, so
  they are what was known at the quote. deadline is the won option's deadline in the request; the order_won event
  can carry a later one (car ready later than stated). last_pickup_at is order_won's lastPickupAt.
- state at won_at counts what happened before the order_won event: earlier order_won events (cancelled ones
  included), gigs posted / booked before that minute and still open / booked, as in build_spells.py (our own withdraws are not saved, so their
  minute is estimated there), drivers whose first view or booking of the day was before that minute.
- gigs, their stops, posting minute and fee schedule come from snapshot.json.gz (the events hold no posting).
- money: every ledger line of the order, summed per kind, written positive. A line with a gig and no order (the
  driver fee of a gig with several orders) is split between the gig's orders in proportion to their typical fees
  (typical fee x legs in the gig / legs of the order), the remainder going to the first order.
- on_time: a revenue line and no late_refund line. late_minutes: from the refund's text, else last delivery minus
  the order's last known deadline; 0 when on time, empty when not delivered.
- posts: gigs that carried the order. bookings / drops / expired: gig_booked / gig_dropped + no_show / gig_expired
  events of those gigs. first_ = the earliest, final_ = the last booking of any of those gigs.
- ratios: fee over the gig's typical fee (summed over its cars). The opening fee is the gig's schedule at its
  posting minute; when a reprice replaced that schedule, the first fee a driver saw, else the schedule's first fee.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import json
import math
import os
import re
import sys
import time
import traceback
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
DAY = 1440
WORLD_END = 14280
NEAR_KM = 60.0
COLUMNS = [
    "seed", "world_id", "policy", "order_id", "option", "dealer_id", "won_at", "day", "minute_of_day",
    "pickup_place", "delivery_place", "km", "drive_minutes", "legs", "private_pickup", "private_delivery",
    "premium", "electric", "has_note", "list_price_cents", "reference_fee_cents", "price_cents", "ready_at",
    "deadline", "last_pickup_at", "hours_ready_to_deadline", "pickup_day_offset", "hours_won_to_last_pickup",
    "n_drivers", "drivers_home_pickup", "drivers_home_delivery", "drivers_home_60km_pickup", "orders_won_so_far",
    "orders_won_today", "open_gigs_at_win", "booked_gigs_at_win", "active_today", "active_today_near_pickup",
    "fee_paid_cents", "release_fee_cents", "failed_visit_cents", "fine_cents", "waiting_cents",
    "late_refund_cents", "undelivered_penalty_cents", "revenue_cents", "on_time", "late_minutes", "delivered",
    "posts", "bookings", "drops", "expired", "in_multi_car_gig", "first_post_at", "first_opening_ratio",
    "first_booked_at", "first_booked_ratio", "final_booked_ratio", "minutes_post_to_final_booking",
]  # fmt: skip
MONEY = {
    "driver_fee": "fee_paid", "release_fee": "release_fee", "failed_visit": "failed_visit", "fine": "fine",
    "waiting": "waiting", "late_refund": "late_refund", "undelivered_penalty": "undelivered_penalty",
    "revenue": "revenue",
}  # fmt: skip
LATE = re.compile(r"Late by (\d+) minutes")

ROADS: dict = {}
NEAR: dict = {}


def read_json(path: Path):
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(path.read_text())


def init(map_path: str) -> None:
    global ROADS, NEAR
    world = read_json(Path(map_path))
    ROADS = {(r["from"], r["to"]): (r["km"], r["minutes"]) for r in world["roads"]}
    places = {p["id"]: (p["lat"], p["lon"]) for p in world["places"]}

    def km(a, b):
        (lat1, lon1), (lat2, lon2) = (map(math.radians, p) for p in (a, b))
        h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        return 2 * 6371 * math.asin(math.sqrt(h))

    NEAR = {p: {q for q in places if km(places[p], places[q]) <= NEAR_KM} for p in places}


def build_week(folder: str) -> tuple[list, dict]:
    path = Path(folder)
    meta = read_json(path / "meta.json")
    snapshot = read_json(path / "snapshot.json.gz")
    drivers = read_json(path / "drivers.json.gz")
    try:
        reveal = read_json(path / "reveal.json.gz") or {}
    except Exception:
        reveal = {}
    stats = Counter()
    head = [meta["seed"], meta["worldId"], meta.get("policy") or ("prober-" + str(meta.get("mode", "")))]

    home = {d["id"]: d["homePlaceId"] for d in drivers}
    home_count = Counter(home.values())
    near_count = {p: sum(home_count[q] for q in qs) for p, qs in NEAR.items()}
    gigs = {g["id"]: g for g in snapshot.get("gigs", [])}

    # ---- one pass over the events
    requests, won, won_seq, cancelled = {}, {}, [], set()
    last_deadline = {}
    activity = defaultdict(dict)  # day -> driver -> first minute of a view or booking
    gig_view_ats = defaultdict(list)
    changes = defaultdict(list)  # gig -> (at, seq, kind, payload)
    accepted = set()
    counts = defaultdict(Counter)  # gig -> event kind -> n
    books = defaultdict(list)  # gig -> (at, seq, fee, driver)
    delivered_gig, delivered_order = {}, {}
    ledger = []
    with gzip.open(path / "events.jsonl.gz", "rt", encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            kind, at = e["kind"], e["at"]
            if kind == "gig_viewed":
                gig_view_ats[e["gigId"]].append(at)
                activity[at // DAY].setdefault(e["driverId"], at)
            elif kind == "price_request":
                requests[e["request"]["id"]] = e["request"]
            elif kind == "order_won":
                o = e["order"]
                if o["id"] not in won:
                    won[o["id"]] = (at, o)
                    won_seq.append((at, o["id"]))
                last_deadline[o["id"]] = o["deadline"]
            elif kind == "order_changed":
                last_deadline[e["order"]["id"]] = e["order"]["deadline"]
            elif kind == "order_cancelled":
                cancelled.add(e["orderId"])
                for item in e.get("gigs") or []:
                    changes[item["gigId"]].append((at, e["seq"], "cancel", item.get("outcome")))
            elif kind == "offer_answered":
                if e.get("answer") == "accepted":
                    accepted.add((e["gigId"], e["driverId"], at))
            elif kind == "gig_booked":
                gid = e["gigId"]
                changes[gid].append((at, e["seq"], kind, None))
                books[gid].append((at, e["seq"], e.get("feeCents"), e["driverId"]))
                counts[gid][kind] += 1
                activity[at // DAY].setdefault(e["driverId"], at)
            elif kind in ("gig_dropped", "no_show", "gig_expired"):
                changes[e["gigId"]].append((at, e["seq"], kind, None))
                counts[e["gigId"]][kind] += 1
            elif kind == "delivered":
                if e.get("gigId") is not None:
                    delivered_gig[e["gigId"]] = max(at, delivered_gig.get(e["gigId"], 0))
                delivered_order[e["orderId"]] = max(at, delivered_order.get(e["orderId"], 0))
            elif kind == "ledger":
                ledger.append(e["line"])
    for item in reveal.get("requests") or []:  # a request with no price_request event
        requests.setdefault(item["request"]["id"], item["request"])

    # ---- what each gig carries: its orders, typical fee, and each order's share of a fee paid for the gig
    info, order_gigs = {}, defaultdict(list)
    for gid, g in gigs.items():
        cars = Counter(s["orderId"] for s in g["stops"] if s["kind"] == "pickup")
        orders = list(dict.fromkeys(s["orderId"] for s in g["stops"]))
        weight, known = {}, True
        for oid in orders:
            order_gigs[oid].append(gid)
            r = requests.get(oid)
            if r and r.get("referenceFeeCents") and r["legs"]:
                weight[oid] = r["referenceFeeCents"] * (cars[oid] or 1) / len(r["legs"])
            else:
                known = False
        if not known:  # a typical fee is missing: split by cars, and no ratios for this gig
            weight = {oid: cars[oid] or 1 for oid in orders}
            stats["gigs_without_typical_fee"] += 1
        info[gid] = {"orders": orders, "weight": weight, "typical": sum(weight.values()) if known else None}

    def later_post(gid, after):
        mine = gigs[gid]["postedAt"]
        later = [
            gigs[x]["postedAt"] for oid in info[gid]["orders"] for x in order_gigs[oid]
            if x != gid and gigs[x]["postedAt"] >= after and gigs[x]["postedAt"] > mine
        ]  # fmt: skip
        return min(later) if later else None

    # ---- open and booked intervals of each gig (build_spells.py)
    open_starts, open_ends, booked_starts, booked_ends = [], [], [], []
    for gid, g in gigs.items():
        open_from, booked_from = g["postedAt"], None
        for at, _seq, kind, payload in sorted(changes.get(gid, [])):
            if kind == "gig_booked":
                if open_from is not None:
                    open_starts.append(open_from)
                    open_ends.append(max(at + 1, open_from))
                    open_from = None
                if booked_from is None:
                    booked_from = at
            elif kind in ("gig_dropped", "no_show"):
                if booked_from is not None:
                    booked_starts.append(booked_from)
                    booked_ends.append(at)
                    booked_from = None
                if open_from is None:
                    open_from = at
            elif kind == "gig_expired" or (kind == "cancel" and payload in ("withdrawn", "released")):
                if open_from is not None:
                    open_starts.append(open_from)
                    open_ends.append(at)
                    open_from = None
                if booked_from is not None:
                    booked_starts.append(booked_from)
                    booked_ends.append(at)
                    booked_from = None
        if open_from is not None:
            end = WORLD_END
            if g["status"] == "withdrawn":  # withdrawn by us at a minute that is not saved
                end = later_post(gid, open_from)
                if end is None:
                    seen = [t for t in gig_view_ats.get(gid, []) if t >= open_from]
                    end = max(seen) + 1 if seen else open_from
            open_starts.append(open_from)
            open_ends.append(max(end, open_from))
        if booked_from is not None:
            if g["status"] == "withdrawn":  # released by us at a minute that is not saved
                end = later_post(gid, booked_from) or WORLD_END
            else:
                end = delivered_gig.get(gid, WORLD_END)
            booked_starts.append(booked_from)
            booked_ends.append(max(end, booked_from))
    for lst in (open_starts, open_ends, booked_starts, booked_ends):
        lst.sort()

    # ---- the account, by order
    account = defaultdict(Counter)
    refund_text, multi_paid = {}, set()
    for line in ledger:
        key = MONEY.get(line["kind"])
        if key is None:
            stats["ledger_kind_" + line["kind"]] += 1
            continue
        oid, gid, cents = line["orderId"], line["gigId"], -line["cents"]
        if key == "revenue":
            cents = line["cents"]
        if oid is not None:
            account[oid][key] += cents
            if key == "late_refund":
                refund_text.setdefault(oid, line.get("detail") or "")
        elif gid in info:
            weight = info[gid]["weight"]
            total = sum(weight.values())
            shares = {o: int(cents * w // total) for o, w in weight.items()}
            first = next(iter(weight))
            shares[first] += cents - sum(shares.values())
            for o, part in shares.items():
                account[o][key] += part
            if len(weight) > 1:
                multi_paid.update(weight)
        else:
            stats["ledger_lines_without_order"] += 1
    paid_lines = Counter((line["orderId"], line["kind"]) for line in ledger if line["orderId"] is not None)

    def opening_fee(gid):
        g = gigs[gid]
        schedule, posted = g["schedule"], g["postedAt"]
        if schedule[0]["at"] <= posted:
            fee = schedule[0]["feeCents"]
            for step in schedule:
                if step["at"] > posted:
                    break
                fee = step["feeCents"]
            return fee
        seen = [(at, fee) for at, _s, fee, drv in books.get(gid, []) if fee and (gid, drv, at) not in accepted]
        seen += [(v["at"], v["feeCents"]) for v in reveal.get("views") or [] if v["gigId"] == gid]
        seen = sorted(x for x in seen if x[0] < schedule[0]["at"])
        if seen:
            stats["opening_fee_seen"] += 1
            return seen[0][1]
        stats["opening_fee_guessed"] += 1
        return schedule[0]["feeCents"]

    day_active, day_active_near = {}, {}

    def active(day, t, place):
        if day not in day_active:
            day_active[day] = sorted(activity.get(day, {}).values())
        key = (day, place)
        if key not in day_active_near:
            ok = NEAR.get(place, ())
            day_active_near[key] = sorted(at for drv, at in activity.get(day, {}).items() if home.get(drv) in ok)
        return bisect.bisect_left(day_active[day], t), bisect.bisect_left(day_active_near[key], t)

    def ratio(fee, gid):
        typical = info[gid]["typical"]
        return round(fee / typical, 4) if fee and typical else ""

    rows = []
    won_ats = [at for at, _ in won_seq]
    for n_before, (won_at, oid) in enumerate(won_seq):
        o = won[oid][1]
        if oid in cancelled:
            stats["cancelled"] += 1
            continue
        r = requests.get(oid)
        if r is None:
            stats["won_without_request"] += 1
            continue
        option = next((x for x in r["options"] if x["kind"] == o["option"]), None)
        legs = r["legs"]
        p, d = legs[0]["pickup"], legs[0]["delivery"]
        pp, dp = p["placeId"], d["placeId"]
        km, minutes = ROADS.get((pp, dp)) or ROADS.get((dp, pp)) or ("", "")
        day = won_at // DAY
        ready = p["window"]["from"]
        deadline = option["deadline"] if option else o["deadline"]
        if o["deadline"] != deadline:
            stats["deadline_moved_at_win"] += 1
        last_pickup = o.get("lastPickupAt")
        act, act_near = active(day, won_at, pp)
        a = account.get(oid, Counter())
        delivered = int(paid_lines[(oid, "revenue")] > 0)
        late = paid_lines[(oid, "late_refund")] > 0
        late_minutes = ""
        if delivered:
            late_minutes = 0
            if late:
                match = LATE.search(refund_text.get(oid, ""))
                if match:
                    late_minutes = int(match[1])
                else:
                    stats["late_minutes_from_events"] += 1
                    late_minutes = max(0, delivered_order.get(oid, 0) - last_deadline.get(oid, deadline))
        gids = sorted(order_gigs.get(oid, []), key=lambda x: (gigs[x]["postedAt"], int(x[1:]) if x[1:].isdigit() else 0))
        booked = sorted((at, seq, fee, x) for x in gids for at, seq, fee, _drv in books.get(x, []))
        first_post = gigs[gids[0]]["postedAt"] if gids else ""
        multi = oid in multi_paid or any(len(info[x]["orders"]) > 1 and books.get(x) for x in gids)
        if not gids:
            stats["orders_never_posted"] += 1
        rows.append(head + [
            oid, o["option"], o["dealerId"], won_at, day, won_at % DAY, pp, dp, km, minutes, len(legs),
            int(any(x["pickup"]["privateAddress"] for x in legs)),
            int(any(x["delivery"]["privateAddress"] for x in legs)),
            int(any(x["car"]["premium"] for x in legs)),
            int(any(x["car"]["electric"] for x in legs)),
            int(r.get("note") is not None),
            option["listPriceCents"] if option else "", r.get("referenceFeeCents", ""), o["priceCents"],
            ready, deadline, last_pickup if last_pickup is not None else "",
            round((deadline - ready) / 60, 3), ready // DAY - day,
            round((last_pickup - won_at) / 60, 3) if last_pickup is not None else "",
            len(home), home_count.get(pp, 0), home_count.get(dp, 0), near_count.get(pp, 0),
            n_before, n_before - bisect.bisect_left(won_ats, day * DAY),
            bisect.bisect_left(open_starts, won_at) - bisect.bisect_right(open_ends, won_at),
            bisect.bisect_left(booked_starts, won_at) - bisect.bisect_right(booked_ends, won_at),
            act, act_near,
            a["fee_paid"], a["release_fee"], a["failed_visit"], a["fine"], a["waiting"], a["late_refund"],
            a["undelivered_penalty"], a["revenue"], int(delivered and not late), late_minutes, delivered,
            len(gids), sum(counts[x]["gig_booked"] for x in gids),
            sum(counts[x]["gig_dropped"] + counts[x]["no_show"] for x in gids),
            sum(counts[x]["gig_expired"] for x in gids), int(bool(multi)),
            first_post, ratio(opening_fee(gids[0]), gids[0]) if gids else "",
            booked[0][0] if booked else "", ratio(booked[0][2], booked[0][3]) if booked else "",
            ratio(booked[-1][2], booked[-1][3]) if booked else "",
            booked[-1][0] - first_post if booked else "",
        ])  # fmt: skip
    return rows, dict(stats)


def work(folder: str):
    try:
        rows, stats = build_week(folder)
        return folder, rows, stats, None
    except Exception:
        return folder, [], {}, traceback.format_exc(limit=3)


def find_weeks(roots: list[str]) -> list[str]:
    found = []
    for root in roots:
        for here, dirs, files in os.walk(root):
            dirs.sort()
            if "meta.json" in files:
                if "events.jsonl.gz" in files and "snapshot.json.gz" in files:
                    found.append(here)
                dirs[:] = []
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("roots", nargs="+", help="folders that hold saved weeks")
    parser.add_argument("--out", default=str(HERE / "orders.csv.gz"))
    parser.add_argument("--map", default=str(HERE.parent / "runs" / "map.json"))
    parser.add_argument("--limit", type=int, default=0, help="read only N week folders, evenly spread")
    parser.add_argument("--jobs", type=int, default=16)
    args = parser.parse_args()
    start = time.time()
    folders = find_weeks(args.roots)
    if args.limit:
        folders = folders[:: max(1, len(folders) // args.limit)][: args.limit]
    read, total, skipped, duplicates, seen, stats = 0, 0, [], 0, set(), Counter()
    tmp = args.out + ".tmp"
    with Pool(args.jobs, init, (args.map,)) as pool, gzip.open(tmp, "wt", newline="", compresslevel=5) as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(COLUMNS)
        for folder, rows, st, error in pool.imap(work, folders, chunksize=4):
            if error:
                skipped.append(folder)
                print(f"skip {folder}: {error.strip().splitlines()[-1]}", file=sys.stderr)
                continue
            world_id = rows[0][1] if rows else folder
            if world_id in seen:
                duplicates += 1
                continue
            seen.add(world_id)
            read += 1
            total += len(rows)
            stats.update(st)
            writer.writerows(rows)
    os.replace(tmp, args.out)
    print(f"{args.out}: {total} rows, {len(folders)} week folders, {read} read, {len(skipped)} failed, "
          f"{duplicates} duplicate world ids")  # fmt: skip
    print(dict(sorted(stats.items())))
    print(f"{time.time() - start:.0f} s")


if __name__ == "__main__":
    main()
