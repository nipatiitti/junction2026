#!/usr/bin/env python3
"""One flat training file of gig spells from saved Spread weeks.

    python3 build_spells.py ROOT [ROOT ...] [--out spells.csv.gz] [--limit N] [--jobs 16]

A ROOT is any folder; every folder below it that holds meta.json + events.jsonl.gz + snapshot.json.gz is a week.
One row per spell: a stretch in which one open, unbooked gig showed one fee, cut at every hour boundary, and kept
only between 07:00 and 21:00. Standard library only. The logic follows junction2026/analysis/facts.py (gig_spells),
with these differences:

- a booking in minute t belongs to the row that contains minute t, and that row ends at t + 1 (so minutes >= 1);
- no action log is saved, so the fee comes from the gig's last schedule (snapshot). Before that schedule's first
  step (a reprice replaced the earlier schedule) the fee is the one drivers saw: the last view or booking fee at or
  before the minute (reveal views, gig_booked), else the first one after. fee_source says which: schedule, seen,
  guess (nothing seen: the last schedule's first fee);
- our withdraws are not saved: a gig that is still open after its last event and ends as withdrawn is closed at the
  next post of one of its orders, else after its last view (end_estimated = 1 on its rows).
"""

import bisect
import csv
import gzip
import io
import json
import math
import multiprocessing
import os
import shutil
import sys
import traceback
from collections import defaultdict

DAY = 1440
WORLD_END = 14280
OPEN_H, CLOSE_H = 7, 21
NEAR_KM = 60.0
MAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runs", "map.json")

COLUMNS = [
    "seed", "world_id", "policy", "gig_id", "order_id", "cars", "start_at", "minutes", "day", "hour",
    "pickup_place", "delivery_place", "km", "drive_minutes", "private_pickup", "private_delivery", "premium",
    "experienced_only", "manual_only", "typical_fee_cents", "fee_cents", "fee_ratio", "opening_ratio",
    "minutes_since_first_post", "minutes_to_last_pickup", "pickup_day_offset", "deadline_warned",
    "was_dropped_before", "views_before", "viewers_before", "views_in_spell", "n_drivers", "drivers_home_pickup",
    "drivers_home_delivery", "drivers_home_60km", "active_today", "active_today_near_pickup", "booked_today",
    "open_gigs_now", "booked_gigs_now", "booked", "booked_driver_id", "booked_driver_home",
    "booked_driver_viewed_before",
    # extras, not in the brief
    "via_offer", "fee_source", "end_estimated",
]  # fmt: skip

WORLD = None


def load_world():
    global WORLD
    if WORLD is None:
        m = json.load(open(MAP))
        places = {p["id"]: (p["lat"], p["lon"]) for p in m["places"]}

        def km(a, b):
            (lat1, lon1), (lat2, lon2) = (map(math.radians, p) for p in (a, b))
            h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
            return 2 * 6371 * math.asin(math.sqrt(h))

        near = {p: {q for q in places if km(places[p], places[q]) <= NEAR_KM} for p in places}
        roads = {(r["from"], r["to"]): (r["km"], r["minutes"]) for r in m["roads"]}
        WORLD = {"near": near, "roads": roads}
    return WORLD


def shown_fee(schedule, t):
    fee = schedule[0]["feeCents"]
    for step in schedule:
        if step["at"] > t:
            break
        fee = step["feeCents"]
    return fee


def read_json_gz(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def build_week(folder):
    """The rows of one week, as lists in COLUMNS order, and a few counters."""
    world = load_world()
    near, roads = world["near"], world["roads"]
    meta = json.load(open(os.path.join(folder, "meta.json")))
    snapshot = read_json_gz(os.path.join(folder, "snapshot.json.gz"))
    drivers = read_json_gz(os.path.join(folder, "drivers.json.gz"))
    try:
        reveal = read_json_gz(os.path.join(folder, "reveal.json.gz")) or {}
    except Exception:
        reveal = {}
    seed, world_id, policy = meta.get("seed"), meta.get("worldId") or snapshot.get("worldId"), meta.get("policy")
    stats = defaultdict(int)

    home = {d["id"]: d["homePlaceId"] for d in drivers}
    home_count = defaultdict(int)
    for h in home.values():
        home_count[h] += 1
    near_count = {p: sum(home_count[q] for q in qs) for p, qs in near.items()}

    gigs = {g["id"]: g for g in snapshot.get("gigs", [])}

    # ---- one pass over the events
    requests = {}  # id -> request
    order_ver = defaultdict(lambda: ([], []))  # order -> (ats, order bodies)
    last_pickup = defaultdict(lambda: ([], []))  # order -> (ats, lastPickupAt)
    warned = defaultdict(list)  # order -> deadline_close minutes
    gig_view_ats = defaultdict(list)  # gig -> view minutes
    gig_view_rows = defaultdict(list)  # gig -> (at, driver)
    changes = defaultdict(list)  # gig -> (at, phase, seq, kind, payload)
    accepted = set()
    seen_fees = defaultdict(list)  # gig -> (at, fee): what drivers saw
    book_ats = []
    activity = defaultdict(dict)  # day -> driver -> first minute of a view or booking
    drops = defaultdict(list)  # gig -> gig_dropped minutes
    delivered_at = {}
    events = []
    with gzip.open(os.path.join(folder, "events.jsonl.gz"), "rt") as f:
        for line in f:
            e = json.loads(line)
            kind = e["kind"]
            if kind == "gig_viewed":
                at, gid, drv = e["at"], e["gigId"], e["driverId"]
                gig_view_ats[gid].append(at)
                gig_view_rows[gid].append((at, drv))
                activity[at // DAY].setdefault(drv, at)
            elif kind == "price_request":
                requests[e["request"]["id"]] = e["request"]
            elif kind in ("ledger", "picked_up", "order_lost", "forecast"):
                continue
            else:
                events.append(e)
    for e in events:
        kind, at, seq, gid = e["kind"], e["at"], e["seq"], e.get("gigId")
        if kind in ("order_won", "order_changed"):
            o = e["order"]
            order_ver[o["id"]][0].append(at)
            order_ver[o["id"]][1].append(o)
            if o.get("lastPickupAt") is not None:
                last_pickup[o["id"]][0].append(at)
                last_pickup[o["id"]][1].append(o["lastPickupAt"])
        elif kind == "deadline_close":
            warned[e["orderId"]].append(at)
            if e.get("lastPickupAt") is not None:
                last_pickup[e["orderId"]][0].append(at)
                last_pickup[e["orderId"]][1].append(e["lastPickupAt"])
        elif kind == "order_cancelled":
            for item in e.get("gigs") or []:
                changes[item["gigId"]].append((at, 0, seq, "cancel", item.get("outcome")))
        elif kind == "offer_answered":
            if e.get("answer") == "accepted":
                accepted.add((gid, e["driverId"], at))
        elif kind == "gig_booked":
            changes[gid].append((at, 0, seq, kind, (e["driverId"], e.get("feeCents"))))
            book_ats.append(at)
            activity[at // DAY].setdefault(e["driverId"], at)
        elif kind in ("gig_dropped", "no_show", "gig_expired"):
            changes[gid].append((at, 0, seq, kind, None))
            if kind == "gig_dropped":
                drops[gid].append(at)
        elif kind == "delivered" and gid is not None:
            delivered_at[gid] = max(at, delivered_at.get(gid, 0))
    book_ats.sort()
    for gid, items in changes.items():
        for at, _p, _s, kind, payload in items:
            if kind == "gig_booked" and payload[1] is not None and (gid, payload[0], at) not in accepted:
                seen_fees[gid].append((at, payload[1]))
    for v in reveal.get("views") or []:
        seen_fees[v["gigId"]].append((v["at"], v["feeCents"]))

    # ---- what each gig carries
    def order_at(oid, t):
        ats, bodies = order_ver.get(oid, ([], []))
        i = bisect.bisect_right(ats, t)
        if i:
            return bodies[i - 1]
        return bodies[0] if bodies else requests.get(oid)

    info, order_gigs = {}, defaultdict(list)
    for gid, g in gigs.items():
        stops = g["stops"]
        pickups = [s for s in stops if s["kind"] == "pickup"]
        deliveries = [s for s in stops if s["kind"] == "delivery"]
        orders = list(dict.fromkeys(s["orderId"] for s in stops))
        for oid in orders:
            order_gigs[oid].append(gid)
        per_order = defaultdict(int)
        car_legs = []
        for s in pickups:
            per_order[s["orderId"]] += 1
            r = requests.get(s["orderId"])
            if r and s["leg"] < len(r["legs"]):
                car_legs.append(r["legs"][s["leg"]])
        typical, typical_ok = 0.0, bool(pickups)
        for oid, n in per_order.items():
            r = requests.get(oid)
            if r and r.get("referenceFeeCents") is not None and r["legs"]:
                typical += r["referenceFeeCents"] * n / len(r["legs"])
            else:
                typical_ok = False
        km = minutes = 0.0
        for leg in car_legs:
            a, b = leg["pickup"]["placeId"], leg["delivery"]["placeId"]
            road = roads.get((a, b)) or roads.get((b, a)) or (0, 0)
            km += road[0]
            minutes += road[1]

        def place(stop, side):
            r = requests.get(stop["orderId"]) if stop else None
            return r["legs"][stop["leg"]][side]["placeId"] if r and stop["leg"] < len(r["legs"]) else None

        info[gid] = {
            "order_id": stops[0]["orderId"],
            "orders": orders,
            "cars": len(pickups),
            "first_pickup": pickups[0] if pickups else None,
            "pickup_place": place(pickups[0] if pickups else None, "pickup"),
            "delivery_place": place(deliveries[-1] if deliveries else None, "delivery"),
            "km": round(km, 1),
            "drive_minutes": round(minutes),
            "private_pickup": int(any(x["pickup"]["privateAddress"] for x in car_legs)),
            "private_delivery": int(any(x["delivery"]["privateAddress"] for x in car_legs)),
            "premium": int(any(x["car"]["premium"] for x in car_legs)),
            "typical": round(typical) if typical_ok and typical > 0 else None,
        }

    def later_post(gid, after):
        later = [
            gigs[o]["postedAt"] for oid in info[gid]["orders"] for o in order_gigs[oid]
            if o != gid and gigs[o]["postedAt"] >= after and (gigs[o]["postedAt"], o) != (gigs[gid]["postedAt"], gid)
            and gigs[o]["postedAt"] > gigs[gid]["postedAt"]
        ]  # fmt: skip
        return min(later) if later else None

    # ---- open and booked intervals of each gig
    open_ivs = {}  # gig -> [(start, end_exclusive, booking or None, estimated)]
    open_starts, open_ends, booked_starts, booked_ends = [], [], [], []
    for gid, g in gigs.items():
        ivs, open_from, booked_from = [], None, None
        items = [(g["postedAt"], -1, -1, "post", None), *changes.get(gid, [])]
        for at, _phase, _seq, kind, payload in sorted(items, key=lambda c: c[:3]):
            if kind == "post":
                open_from = at
            elif kind == "gig_booked":
                if open_from is not None:
                    ivs.append((open_from, at + 1, (at, payload[0], payload[1]), 0))
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
                    ivs.append((open_from, at, None, 0))
                    open_from = None
                if booked_from is not None:
                    booked_starts.append(booked_from)
                    booked_ends.append(at)
                    booked_from = None
        if open_from is not None:
            if g["status"] == "withdrawn":
                end = later_post(gid, open_from)
                if end is None:
                    seen = [t for t in gig_view_ats.get(gid, []) if t >= open_from]
                    end = max(seen) + 1 if seen else open_from
                ivs.append((open_from, end, None, 1))
                stats["withdraw_estimated"] += 1
            else:
                ivs.append((open_from, WORLD_END, None, 0))
        if booked_from is not None:
            if g["status"] == "withdrawn":  # released by us at an unknown minute
                end = later_post(gid, booked_from) or WORLD_END
            else:
                end = delivered_at.get(gid, WORLD_END)
            booked_starts.append(booked_from)
            booked_ends.append(max(end, booked_from))
        ivs = [iv for iv in ivs if iv[1] > iv[0]]
        open_ivs[gid] = ivs
        for a, b, _bk, _est in ivs:
            open_starts.append(a)
            open_ends.append(b)
    for lst in (open_starts, open_ends, booked_starts, booked_ends):
        lst.sort()

    # ---- order-level lookups (an order's gigs: every gig that carries it)
    order_views, order_viewer_first, order_first_ats, first_post, order_drops = {}, {}, {}, {}, {}

    def order_lookups(oid):
        if oid not in order_views:
            gids = order_gigs[oid]
            order_views[oid] = sorted(t for x in gids for t in gig_view_ats.get(x, []))
            firsts = {}
            for at, drv in sorted(v for x in gids for v in gig_view_rows.get(x, [])):
                firsts.setdefault(drv, at)
            order_viewer_first[oid] = firsts
            order_first_ats[oid] = sorted(firsts.values())
            first_post[oid] = min(gigs[x]["postedAt"] for x in gids)
            order_drops[oid] = min((t for x in gids for t in drops.get(x, [])), default=None)

    # ---- per day: first activity minutes, all drivers and by pickup place
    day_active, day_active_near = {}, {}

    def active(day, t, place):
        if day not in day_active:
            day_active[day] = sorted(activity.get(day, {}).values())
        key = (day, place)
        if key not in day_active_near:
            ok = near.get(place, ())
            day_active_near[key] = sorted(at for drv, at in activity.get(day, {}).items() if home.get(drv) in ok)
        return bisect.bisect_left(day_active[day], t), bisect.bisect_left(day_active_near[key], t)

    rows = []
    for gid, g in gigs.items():
        ivs = open_ivs[gid]
        if not ivs:
            continue
        inf = info[gid]
        oid = inf["order_id"]
        order_lookups(oid)
        schedule = g["schedule"]
        s0 = schedule[0]["at"]
        seen = sorted(x for x in seen_fees.get(gid, []) if x[0] < s0)
        seen_ats = [x[0] for x in seen]

        def fee_at(t, schedule=schedule, s0=s0, seen=seen, seen_ats=seen_ats):
            if t >= s0:
                return shown_fee(schedule, t), "schedule"
            if seen:
                i = bisect.bisect_right(seen_ats, t)
                return seen[max(i - 1, 0)][1], "seen"
            return schedule[0]["feeCents"], "schedule" if s0 <= g["postedAt"] else "guess"

        typical = inf["typical"]
        opening = fee_at(g["postedAt"])[0]
        opening_ratio = round(opening / typical, 4) if typical else ""
        views = gig_view_ats.get(gid, [])
        pp, dp = inf["pickup_place"], inf["delivery_place"]
        fp = inf["first_pickup"]
        gviews = sorted(views)
        change_ats = sorted({s["at"] for s in schedule} | set(seen_ats))
        for a, b, booking, estimated in ivs:
            cuts = {a}
            cuts.update(t for t in change_ats if a < t < b)
            cuts.update(range((a // 60 + 1) * 60, b, 60))
            cuts = sorted(cuts)
            for i, p in enumerate(cuts):
                q = cuts[i + 1] if i + 1 < len(cuts) else b
                hour = p % DAY // 60
                last = i + 1 == len(cuts)
                if not (OPEN_H <= hour < CLOSE_H):
                    if last and booking:
                        stats["bookings_outside_hours"] += 1
                    continue
                fee, source = fee_at(p)
                day = p // DAY
                is_booked = int(bool(last and booking))
                drv = drv_home = viewed = via_offer = ""
                if is_booked:
                    b_at, drv, b_fee = booking
                    drv_home = home.get(drv, "")
                    first = order_viewer_first[oid].get(drv)
                    viewed = int(first is not None and first < p)
                    via_offer = int((gid, drv, b_at) in accepted)
                    stats["bookings"] += 1
                    if not via_offer and b_fee is not None and b_fee != fee:
                        stats["booking_fee_mismatch"] += 1
                # the order's state known at p
                lps = []
                for o in inf["orders"]:
                    ats, values = last_pickup.get(o, ([], []))
                    j = bisect.bisect_right(ats, p)
                    if j:
                        lps.append(values[j - 1])
                to_last = min(lps) - p if lps else ""
                offset = ""
                if fp is not None:
                    start = (fp.get("window") or {}).get("from")
                    if start is None:
                        body = order_at(fp["orderId"], p)
                        if body and fp["leg"] < len(body["legs"]):
                            start = body["legs"][fp["leg"]]["pickup"]["window"]["from"]
                    if start is not None:
                        offset = start // DAY - day
                is_warned = int(any(t <= p for o in inf["orders"] for t in warned.get(o, [])))
                dropped = order_drops[oid]
                act, act_near = active(day, p, pp)
                rows.append([
                    seed, world_id, policy, gid, oid, inf["cars"], p, q - p, day, hour,
                    pp, dp, inf["km"], inf["drive_minutes"], inf["private_pickup"], inf["private_delivery"],
                    inf["premium"], int(bool(g["audience"]["experienced"])), int(bool(g["audience"]["manualLicence"])),
                    typical if typical else "", fee, round(fee / typical, 4) if typical else "", opening_ratio,
                    p - first_post[oid], to_last, offset, is_warned, int(dropped is not None and dropped <= p),
                    bisect.bisect_left(order_views[oid], p), bisect.bisect_left(order_first_ats[oid], p),
                    bisect.bisect_left(gviews, q) - bisect.bisect_left(gviews, p),
                    len(home), home_count.get(pp, 0), home_count.get(dp, 0), near_count.get(pp, 0),
                    act, act_near, bisect.bisect_left(book_ats, p) - bisect.bisect_left(book_ats, day * DAY),
                    bisect.bisect_right(open_starts, p) - bisect.bisect_right(open_ends, p),
                    bisect.bisect_right(booked_starts, p) - bisect.bisect_right(booked_ends, p),
                    is_booked, drv, drv_home, viewed, via_offer, source, estimated,
                ])  # fmt: skip
    return rows, dict(stats)


def work(job):
    folder, part = job
    try:
        rows, stats = build_week(folder)
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(rows)
        with open(part, "wb") as f:
            f.write(gzip.compress(buf.getvalue().encode(), 5))
        return folder, len(rows), stats, None
    except Exception:
        return folder, 0, {}, traceback.format_exc(limit=3)


def find_weeks(roots):
    weeks = []
    for root in roots:
        for path, dirs, files in os.walk(root):
            dirs.sort()
            if "meta.json" in files and "events.jsonl.gz" in files and "snapshot.json.gz" in files:
                weeks.append(path)
                dirs[:] = []
    return weeks


def main(argv):
    here = os.path.dirname(os.path.abspath(__file__))
    out, limit, jobs, roots = os.path.join(here, "spells.csv.gz"), None, 16, []
    it = iter(argv)
    for arg in it:
        if arg == "--out":
            out = next(it)
        elif arg == "--limit":
            limit = int(next(it))
        elif arg == "--jobs":
            jobs = int(next(it))
        else:
            roots.append(arg)
    if not roots:
        sys.exit(__doc__)
    weeks = find_weeks(roots)
    if limit:
        weeks = weeks[:: max(1, len(weeks) // limit)][:limit]
    parts = out + ".parts"
    shutil.rmtree(parts, ignore_errors=True)
    os.makedirs(parts)
    todo = [(w, os.path.join(parts, f"{i:06d}.gz")) for i, w in enumerate(weeks)]
    total, read, skipped, stats = 0, 0, [], defaultdict(int)
    with multiprocessing.Pool(jobs) as pool:
        for n, (folder, count, st, err) in enumerate(pool.imap_unordered(work, todo, chunksize=4), 1):
            if err:
                skipped.append(folder)
                print(f"skip {folder}: {err.strip().splitlines()[-1]}", file=sys.stderr)
            else:
                read += 1
                total += count
                for k, v in st.items():
                    stats[k] += v
            if n % 500 == 0:
                print(f"{n}/{len(todo)} weeks, {total} rows", file=sys.stderr)
    with open(out + ".tmp", "wb") as f:
        f.write(gzip.compress((",".join(COLUMNS) + "\n").encode()))
        for _w, part in todo:
            if os.path.exists(part):
                with open(part, "rb") as p:
                    shutil.copyfileobj(p, f)
    os.replace(out + ".tmp", out)
    shutil.rmtree(parts, ignore_errors=True)
    print(f"{out}: {total} rows, {read} weeks read, {len(skipped)} skipped")
    print(dict(stats))


if __name__ == "__main__":
    main(sys.argv[1:])
