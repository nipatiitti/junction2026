#!/usr/bin/env python3
"""Why orders of the `lean` strategy arrive late on the real server, and what it paid drivers.

    python3 lean_late.py [RUNS_ROOT] [--jobs 16]

Reads every saved week below RUNS_ROOT (default ../runs/L8) whose meta.json has policy == "ts-lean". Standard library
only. Parsing follows build_spells.py. Prints tables A-E (see the task brief).

Definitions (choices of this script, not of the game):
- late: the order has a `late_refund` or `undelivered_penalty` ledger line. Cancelled orders are left out.
- LP: `lastPickupAt` from `order_won`, replaced by an `order_changed` that came while the old LP was still ahead.
- cause of a late order, first that applies:
  1  never booked: no driver ever booked a gig of the order;
  2a booked after LP: the first booking came after LP;
  2b booked at the last minute: the first booking came in the last NEAR minutes before LP and the car was collected
     after LP (or never);
  3  dropped: a booking made at or before LP was given back (gig_dropped / no_show) and the booking that held came
     after LP - NEAR, or never;
  4  failed visit: a visit_failed event or failed-visit ledger line names the order;
  5  slow: first car collected at or before LP, still delivered late;
  6  other: booked more than NEAR minutes before LP, no drop that cost the time, collected after LP.
- fee over typical: the gig's fee over the sum of its cars' typical fees (referenceFeeCents share per leg).
- fee shown at a minute: the last gig of the order posted by then; from its last schedule once that has started, else
  the last fee a driver saw at or before the minute (reveal views, bookings), else the first seen after.
"""

import bisect
import gzip
import json
import multiprocessing
import os
import re
import sys
from collections import Counter, defaultdict

DAY = 1440
NEAR = 90  # minutes before LP inside which a first booking counts as "at the last minute" (lean's BOOK_AHEAD)
WAKE, SLEEP = 7 * 60, 21 * 60
HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.join(HERE, "..", "runs", "map.json")
CAUSES = ["1", "2a", "2b", "3", "4", "5", "6"]
CAUSE_NAME = {
    "1": "never booked",
    "2a": "first booking after LP",
    "2b": "first booking <90m before LP",
    "3": "dropped, rebooked late/never",
    "4": "failed visit",
    "5": "collected in time, slow",
    "6": "other (booked early, collected late)",
}
ROADS = None


def roads():
    global ROADS
    if ROADS is None:
        m = json.load(open(MAP))
        ROADS = {(r["from"], r["to"]): r["minutes"] for r in m["roads"]}
    return ROADS


def read_gz(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def awake(a, b):
    s = 0
    for day in range(a // DAY, b // DAY + 1):
        s += max(0, min(b, day * DAY + SLEEP) - max(a, day * DAY + WAKE))
    return s


def shown_fee(schedule, t):
    fee = schedule[0]["feeCents"]
    for step in schedule:
        if step["at"] > t:
            break
        fee = step["feeCents"]
    return fee


def week(folder):
    rd = roads()
    meta = json.load(open(os.path.join(folder, "meta.json")))
    snapshot = read_gz(os.path.join(folder, "snapshot.json.gz"))
    try:
        reveal = read_gz(os.path.join(folder, "reveal.json.gz")) or {}
    except Exception:
        reveal = {}
    p = meta["settings"]["params"]
    group = (p.get("stepped"), p.get("chains"), p.get("target"), p.get("open"))

    requests, won, lp_hist, cancelled = {}, {}, defaultdict(list), set()
    late_kind, failed, changed, driver_late = {}, set(), set(), set()
    books, drops = defaultdict(list), defaultdict(list)  # gig -> [(at, driver, fee)], [(at, kind)]
    picked, delivered = defaultdict(list), defaultdict(list)  # order -> [(at, gig)]
    viewers = defaultdict(list)  # gig -> [(at, driver)]
    gig_started, late_min = {}, {}
    with gzip.open(os.path.join(folder, "events.jsonl.gz"), "rt") as f:
        for line in f:
            e = json.loads(line)
            k, at = e["kind"], e["at"]
            if k == "gig_viewed":
                viewers[e["gigId"]].append((at, e["driverId"]))
            elif k == "price_request":
                requests[e["request"]["id"]] = e["request"]
            elif k == "order_won":
                o = e["order"]
                won[o["id"]] = (at, o)
                lp_hist[o["id"]].append((at, o.get("lastPickupAt")))
            elif k == "order_changed":
                o = e["order"]
                changed.add(o["id"])
                lp_hist[o["id"]].append((at, o.get("lastPickupAt")))
                if o["id"] in won:
                    won[o["id"]] = (won[o["id"]][0], won[o["id"]][1], o)
            elif k == "order_cancelled":
                cancelled.add(e["orderId"])
            elif k == "ledger":
                ln = e["line"]
                if ln["kind"] in ("late_refund", "undelivered_penalty"):
                    late_kind[ln["orderId"]] = ln["kind"]
                    mm = re.search(r"Late by (\d+) minutes", ln.get("detail") or "")
                    if mm:
                        late_min[ln["orderId"]] = int(mm.group(1))
                elif "visit" in ln["kind"] or "Failed visit" in (ln.get("detail") or ""):
                    failed.add(ln.get("orderId"))
            elif k == "visit_failed":
                failed.add(e.get("orderId"))
            elif k == "gig_booked":
                books[e["gigId"]].append((at, e["driverId"], e.get("feeCents")))
            elif k in ("gig_dropped", "no_show"):
                drops[e["gigId"]].append((at, k))
            elif k == "driver_late":
                driver_late.add(e["gigId"])
            elif k == "picked_up":
                picked[e["orderId"]].append((at, e.get("gigId")))
            elif k == "delivered":
                delivered[e["orderId"]].append((at, e.get("gigId")))
            elif k == "gig_started":
                gig_started[e["gigId"]] = at

    gigs = {g["id"]: g for g in snapshot.get("gigs", [])}
    order_gigs, gig_typ = defaultdict(list), {}
    for gid, g in gigs.items():
        per = Counter(s["orderId"] for s in g["stops"] if s["kind"] == "pickup")
        typ, ok = 0.0, bool(per)
        for oid, n in per.items():
            order_gigs[oid].append(gid)
            r = requests.get(oid)
            if r and r.get("referenceFeeCents") and r["legs"]:
                typ += r["referenceFeeCents"] * n / len(r["legs"])
            else:
                ok = False
        for oid in {s["orderId"] for s in g["stops"]} - set(per):
            order_gigs[oid].append(gid)
        gig_typ[gid] = typ if ok and typ > 0 else None
    seen = defaultdict(list)  # gig -> (at, fee) drivers saw
    view_fee = defaultdict(list)  # gig -> (at, driver, fee)
    for v in reveal.get("views") or []:
        seen[v["gigId"]].append((v["at"], v["feeCents"]))
        view_fee[v["gigId"]].append((v["at"], v["driverId"], v["feeCents"]))
    for gid, bs in books.items():
        for at, _d, fee in bs:
            if fee is not None:
                seen[gid].append((at, fee))
    for v in seen.values():
        v.sort()

    def ratio_at(oid, t):
        """Fee over typical that the order's latest gig posted by t shows at t, or None."""
        cands = [g for g in order_gigs[oid] if gigs[g]["postedAt"] <= t]
        if not cands:
            return None
        gid = max(cands, key=lambda g: gigs[g]["postedAt"])
        typ = gig_typ[gid]
        if not typ:
            return None
        sch = gigs[gid]["schedule"]
        if t >= sch[0]["at"]:
            return shown_fee(sch, t) / typ
        s = seen.get(gid, [])
        if not s:
            return None
        i = bisect.bisect_right([x[0] for x in s], t)
        return s[max(i - 1, 0)][1] / typ

    out = []
    for oid, rec in won.items():
        if oid in cancelled:
            continue
        wat, o0 = rec[0], rec[1]
        o = rec[-1]
        lp = None
        for at, v in lp_hist[oid]:
            if v is not None and (lp is None or at <= lp):
                lp = v
        if lp is None:
            continue
        gl = order_gigs[oid]
        bk = sorted((at, g, d, fee) for g in gl for at, d, fee in books.get(g, []))
        dr = sorted((at, g, k) for g in gl for at, k in drops.get(g, []))
        pk = sorted(picked.get(oid, []))
        first_pick = pk[0][0] if pk else None
        held = None
        if pk:
            hg = pk[0][1]
            hb = [b for b in bk if b[1] == hg and b[0] <= pk[0][0]]
            held = hb[-1] if hb else None
        late = oid in late_kind
        cause, sub = "", ""
        if late:
            fb = bk[0][0] if bk else None
            intime_drop = any(any(b[1] == g and b[0] <= min(at, lp) for b in bk) for at, g, _k in dr)
            if fb is None:
                cause = "1"
            elif fb > lp:
                cause = "2a"
            elif fb > lp - NEAR and (first_pick is None or first_pick > lp):
                cause = "2b"
            elif intime_drop and (held is None or held[0] > lp - NEAR):
                cause = "3"
            elif oid in failed:
                cause = "4"
            elif first_pick is not None and first_pick <= lp:
                cause = "5"
            else:
                cause = "6"
                sub = (
                    "changed" if oid in changed
                    else "driver_late" if any(g in driver_late for g in gl)
                    else "dropped, rebooked >90m ahead" if dr
                    else "plain"
                )  # fmt: skip
        legs = o0["legs"]
        drive = 0
        for lg in legs:
            a, b = lg["pickup"]["placeId"], lg["delivery"]["placeId"]
            drive += rd.get((a, b)) or rd.get((b, a)) or 0
        ready = min(lg["pickup"]["window"]["from"] for lg in legs)
        first_post = min((gigs[g]["postedAt"] for g in gl), default=None)
        vs = sorted(v for g in gl for v in viewers.get(g, []))
        row = {
            "group": group, "late": late, "cause": cause, "sub": sub, "kind": late_kind.get(oid, ""),
            "win_to_lp": (lp - wat) / 60, "awake_to_lp": awake(wat, lp) / 60,
            "offset": min(2, max(0, ready // DAY - wat // DAY)),
            "drive": 0 if drive < 90 else 1 if drive <= 300 else 2,
            "viewers_lp": len({d for at, d in vs if at <= lp}), "views_lp": sum(1 for at, d in vs if at <= lp),
            "post_delay": None if first_post is None else first_post - wat,
            "ratios": [ratio_at(oid, lp - h * 60) for h in (24, 12, 6, 3)],
            "posted_by": [first_post is not None and first_post <= lp - h * 60 for h in (24, 12, 6, 3)],
            "chain": any(len({s["orderId"] for s in gigs[g]["stops"]}) > 1 for g in gl),
            "option": o0.get("option"), "dropped": bool(dr), "ndrops": len(dr),
            "first_book_ratio": None, "first_book_after_lp": None,
            "fb_before_lp": (lp - bk[0][0]) / 60 if bk else None,
            "lp_day_start": (lp - (lp // DAY * DAY + WAKE)) / 60,
            "max_seen": max((f / gig_typ[g] for g in gl if gig_typ.get(g) for t, f in seen.get(g, []) if t <= lp), default=None),
            "pick_margin": None if first_pick is None else lp - first_pick,
            "late_min": late_min.get(oid),
            "book_after_post": None if not bk else bk[0][0] - gigs[bk[0][1]]["postedAt"],
            "long_gig": any(len(g2["stops"]) > 2 for g2 in (gigs[g] for g in gl)),
            "paid": None, "wait": None, "lower": None, "first_look": None, "at_open": None,
        }  # fmt: skip
        if bk and gig_typ.get(bk[0][1]) and bk[0][3] is not None:
            row["first_book_ratio"] = bk[0][3] / gig_typ[bk[0][1]]
            row["first_book_after_lp"] = (bk[0][0] - lp) / 60
        if held and gig_typ.get(held[1]) and held[3] is not None and first_post is not None:
            at, hg, drv, fee = held
            r = fee / gig_typ[hg]
            row["paid"] = r
            row["wait"] = at - first_post
            if view_fee:
                earlier = [
                    f / gig_typ[g] for g in gl if gig_typ.get(g) for t, d, f in view_fee.get(g, []) if d == drv and t < at
                ]  # fmt: skip
                row["lower"] = any(x < r * 0.995 for x in earlier)
                row["first_look"] = not earlier
            row["at_open"] = fee <= gigs[hg]["schedule"][0]["feeCents"] and at >= gigs[hg]["schedule"][0]["at"]
        out.append(row)
    s = meta["score"]
    return group, {"orders": s["wonOrders"], "ontime": s["onTimeShare"], "margin": s["marginCents"],
                   "ranked": s.get("ranked"), "reveal": bool(reveal.get("views"))}, out  # fmt: skip


def find(root):
    res = []
    for path, dirs, files in os.walk(root):
        dirs.sort()
        if "probe3" in path:
            dirs[:] = []
            continue
        if "meta.json" in files and "events.jsonl.gz" in files and "snapshot.json.gz" in files:
            dirs[:] = []
            try:
                if json.load(open(os.path.join(path, "meta.json"))).get("policy") == "ts-lean":
                    res.append(path)
            except Exception:
                pass
    return res


def q(xs, f):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return float("nan")
    i = f * (len(xs) - 1)
    lo = int(i)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def med(xs):
    return q(xs, 0.5)


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else float("nan")


def gname(g):
    f = lambda v: "-" if v is None else ("T" if v is True else "F" if v is False else str(v))  # noqa: E731
    return f"stepped={f(g[0])} chains={f(g[1])} target={f(g[2])} open={f(g[3])}"


def main(argv):
    root, jobs = os.path.join(HERE, "..", "runs", "L8"), 16
    it = iter(argv)
    for a in it:
        if a == "--jobs":
            jobs = int(next(it))
        else:
            root = a
    folders = find(root)
    roads()
    with multiprocessing.Pool(jobs) as pool:
        results = pool.map(week, folders, chunksize=2)
    weeks, rows = defaultdict(list), []
    for g, w, out in results:
        weeks[g].append(w)
        rows.extend(out)
    order = sorted(weeks, key=lambda g: tuple(str(x) for x in g))
    print(f"{len(folders)} ts-lean weeks, {len(rows)} won orders not cancelled, {sum(r['late'] for r in rows)} late; "
          f"{sum(1 for ws in weeks.values() for w in ws if not w['reveal'])} weeks without reveal views")  # fmt: skip
    W = 46

    print("\nA. Weeks per param group")
    print(f"{'group':{W}} weeks orders ontime% <90%  margin EUR  late/wk")
    for g in order:
        ws = weeks[g]
        nl = sum(1 for r in rows if r["group"] == g and r["late"])
        print(f"{gname(g):{W}} {len(ws):5d} {mean([w['orders'] for w in ws]):6.0f} {100 * mean([w['ontime'] for w in ws]):7.1f} "
              f"{sum(w['ontime'] < 0.9 for w in ws):4d} {mean([w['margin'] for w in ws]) / 100:11.0f} {nl / len(ws):8.1f}")  # fmt: skip
    allw = [w for ws in weeks.values() for w in ws]
    print(f"{'ALL':{W}} {len(allw):5d} {mean([w['orders'] for w in allw]):6.0f} {100 * mean([w['ontime'] for w in allw]):7.1f} "
          f"{sum(w['ontime'] < 0.9 for w in allw):4d} {mean([w['margin'] for w in allw]) / 100:11.0f} {sum(r['late'] for r in rows) / len(allw):8.1f}")  # fmt: skip

    print("\nB. Late orders by main cause: count per week (share of the group's late orders)")
    for c in CAUSES:
        print(f"   {c:2} = {CAUSE_NAME[c]}")
    print(f"{'group':{W}} " + " ".join(f"{c:>10}" for c in CAUSES) + "   undeliv/wk")
    for g in [*order, None]:
        rs = [r for r in rows if r["late"] and (g is None or r["group"] == g)]
        n = len(weeks[g]) if g else len(allw)
        cnt = Counter(r["cause"] for r in rs)
        und = sum(r["kind"] == "undelivered_penalty" for r in rs)
        print(f"{(gname(g) if g else 'ALL'):{W}} "
              + " ".join(f"{cnt[c] / n:4.1f} ({100 * cnt[c] / max(1, len(rs)):2.0f}%)" for c in CAUSES) + f" {und / n:8.2f}")  # fmt: skip
    lates = [r for r in rows if r["late"]]
    print("   cause 6 detail:", dict(Counter(r["sub"] for r in lates if r["cause"] == "6")))
    print("   late orders with any drop/no-show, by cause:", dict(Counter(r["cause"] for r in lates if r["dropped"])))
    print(f"   drop/no-show on {100 * mean([r['dropped'] for r in rows if not r['late']]):.1f}% of on-time orders, "
          f"{100 * mean([r['dropped'] for r in lates]):.1f}% of late orders")  # fmt: skip

    c5 = [r for r in lates if r["cause"] == "5"]
    c6 = [r for r in lates if r["cause"] == "6" and r["sub"] == "plain"]
    print(f"   cause 5 (n={len(c5)}): minutes late median {med([r['late_min'] for r in c5]):.0f} (p25 {q([r['late_min'] for r in c5], .25):.0f}, p75 {q([r['late_min'] for r in c5], .75):.0f}); "
          f"collected {med([r['pick_margin'] for r in c5]):.0f} min before LP (median); drive >300 min: {100 * mean([r['drive'] == 2 for r in c5]):.0f}%; "
          f"late by at most 120 min: {100 * mean([(r['late_min'] or 1e9) <= 120 for r in c5]):.0f}%")  # fmt: skip
    print(f"   cause 6 plain (n={len(c6)}): first booking {med([r['fb_before_lp'] for r in c6]):.1f} h before LP (median), collected {-med([r['pick_margin'] for r in c6]):.0f} min after LP (median); "
          f"drive >300 min: {100 * mean([r['drive'] == 2 for r in c6]):.0f}%; minutes late median {med([r['late_min'] for r in c6]):.0f}")  # fmt: skip

    print("\nC. Causes 1, 2a, 2b: the fee did not find a driver in time")
    nf = [r for r in rows if r["cause"] in ("1", "2a", "2b")]
    ok = [r for r in rows if not r["late"]]

    def crow(label, rs):
        cells = []
        for i in range(4):
            xs = [r["ratios"][i] for r in rs if r["ratios"][i] is not None]
            posted = sum(r["posted_by"][i] for r in rs)
            cells.append(f"{med(xs):5.2f} (n={len(xs)}, posted {posted})")
        print(f"{label:34} n={len(rs):4d} | " + " | ".join(cells))

    print("fee shown / typical, median, at 24h | 12h | 6h | 3h before LP (n = orders with a known fee then, posted = had a gig by then)")
    crow("causes 1+2a+2b, all groups", nf)
    for c in ("1", "2a", "2b"):
        crow(f"  cause {c}", [r for r in nf if r["cause"] == c])
    crow("  stepped=T", [r for r in nf if r["group"][0] is True])
    crow("  stepped=F", [r for r in nf if r["group"][0] is False])
    crow("  stepped=- (older, open 0.68/-)", [r for r in nf if r["group"][0] is None])
    print(f"distinct drivers who viewed the order by LP: median {med([r['viewers_lp'] for r in nf]):.0f}, "
          f"quartiles {q([r['viewers_lp'] for r in nf], .25):.0f}-{q([r['viewers_lp'] for r in nf], .75):.0f}, "
          f"none: {sum(r['viewers_lp'] == 0 for r in nf)}; on-time orders: median {med([r['viewers_lp'] for r in ok]):.0f}")  # fmt: skip
    print(f"minutes from win to first post: median {med([r['post_delay'] for r in nf]):.0f}, p90 {q([r['post_delay'] for r in nf], .9):.0f}; "
          f"never posted: {sum(r['post_delay'] is None for r in nf)}")  # fmt: skip
    b2 = [r for r in nf if r["first_book_ratio"] is not None]
    print(f"when a driver did book (2a, 2b; n={len(b2)}): fee/typical at that first booking median {med([r['first_book_ratio'] for r in b2]):.2f} "
          f"(p10 {q([r['first_book_ratio'] for r in b2], .1):.2f}, p90 {q([r['first_book_ratio'] for r in b2], .9):.2f}), "
          f"hours after LP median {med([r['first_book_after_lp'] for r in b2]):.1f}")  # fmt: skip
    print(f"highest fee/typical any driver saw by LP: median {med([r['max_seen'] for r in nf]):.2f}, p25 {q([r['max_seen'] for r in nf], .25):.2f}; "
          f"at least 1.5: {100 * mean([(r['max_seen'] or 0) >= 1.5 for r in nf]):.0f}% of them")  # fmt: skip
    b3 = [r for r in nf if r["cause"] == "2a" and r["book_after_post"] is not None]
    print(f"cause 2a: minutes from the post of the gig that was booked to that booking: median {med([r['book_after_post'] for r in b3]):.0f}, "
          f"p75 {q([r['book_after_post'] for r in b3], .75):.0f} (the harness reposts when the old gig expires)")  # fmt: skip
    print("orders with no booking yet at X hours before LP -> share that end late for want of a driver (1, 2a, 2b)")
    for lab, sel in (("all", lambda r: True), ("stepped=T chains=F", lambda r: r["group"][0] is True and r["group"][1] is False),
                     ("stepped=T chains=T", lambda r: r["group"][0] is True and r["group"][1] is True),
                     ("stepped=F", lambda r: r["group"][0] is False), ("stepped=- (older)", lambda r: r["group"][0] is None)):  # fmt: skip
        cells = []
        for h in (24, 12, 6, 3):
            rs = [r for r in rows if sel(r) and r["win_to_lp"] >= h and (r["fb_before_lp"] is None or r["fb_before_lp"] < h)]
            cells.append(f"{h}h: {len(rs):5d} open, {100 * mean([r['cause'] in ('1', '2a', '2b') for r in rs]):4.1f}% late")
        print(f"   {lab:20} " + " | ".join(cells))
    rs = [r for r in rows if r["fb_before_lp"] is None or r["fb_before_lp"] < r["lp_day_start"]]
    print(f"orders with no booking when drivers wake (07:00) on the day of LP: {len(rs)} ({100 * len(rs) / len(rows):.0f}% of orders), "
          f"{100 * mean([r['cause'] in ('1', '2a', '2b') for r in rs]):.1f}% of them end late for want of a driver; "
          f"they are {100 * sum(r['cause'] in ('1', '2a', '2b') for r in rs) / len(nf):.0f}% of causes 1+2a+2b")  # fmt: skip
    for lab, sel in (("chains=T weeks, order was in a multi-car gig", lambda r: r["group"][1] is True and r["long_gig"]),
                     ("chains=T weeks, order never in a multi-car gig", lambda r: r["group"][1] is True and not r["long_gig"]),
                     ("chains=F weeks", lambda r: r["group"][1] is False)):  # fmt: skip
        rs = [r for r in rows if sel(r)]
        print(f"   {lab:48} {len(rs):5d} orders, no-driver late {100 * mean([r['cause'] in ('1', '2a', '2b') for r in rs]):4.1f}%, all late {100 * mean([r['late'] for r in rs]):4.1f}%")
    for key, names in (("offset", ["ready today", "tomorrow", "later"]), ("drive", ["<90 min", "90-300", ">300 min"])):
        print(f"by {'pickup_day_offset' if key == 'offset' else 'drive length'}:  bucket: no-driver late orders (share of them) / all orders in bucket = rate; all-cause late rate")
        for i, nm in enumerate(names):
            a = sum(r[key] == i for r in nf)
            allb = [r for r in rows if r[key] == i]
            print(f"   {nm:12} {a:4d} ({100 * a / max(1, len(nf)):3.0f}%) / {len(allb):5d} = {100 * a / max(1, len(allb)):4.1f}%;  "
                  f"all causes {100 * mean([r['late'] for r in allb]):4.1f}%")  # fmt: skip
    print("offset x drive, no-driver late rate % (orders in cell):")
    for i, nm in enumerate(["ready today", "tomorrow", "later"]):
        cells = []
        for j in range(3):
            cell = [r for r in rows if r["offset"] == i and r["drive"] == j]
            cells.append(f"{100 * mean([r['cause'] in ('1', '2a', '2b') for r in cell]):5.1f} ({len(cell):4d})")
        print(f"   {nm:12} " + "  ".join(cells))

    print("\nD. Orders on time: what the booking that held paid")
    print(f"{'group':{W}}     n  paid/typ p10  med  p90 | wait min med  p90 | viewed lower% | first look% | at opening fee%")
    for g in [*order, None]:
        rs = [r for r in ok if (g is None or r["group"] == g) and r["paid"] is not None]
        pd = [r["paid"] for r in rs]
        wt = [r["wait"] for r in rs]
        print(f"{(gname(g) if g else 'ALL'):{W}} {len(rs):5d}  {q(pd, .1):12.2f} {med(pd):4.2f} {q(pd, .9):4.2f} | "
              f"{med(wt):12.0f} {q(wt, .9):4.0f} | {100 * mean([r['lower'] for r in rs]):13.1f} | "
              f"{100 * mean([r['first_look'] for r in rs]):11.1f} | {100 * mean([r['at_open'] for r in rs]):6.1f}")  # fmt: skip
    rs = [r for r in ok if r["paid"] is not None]
    for lab, sel in (("booked within 30 min of first post", lambda r: r["wait"] <= 30),
                     ("booked 30 min - 6 h after", lambda r: 30 < r["wait"] <= 360),
                     ("booked later than 6 h", lambda r: r["wait"] > 360)):  # fmt: skip
        s = [r for r in rs if sel(r)]
        print(f"   {lab:36} {100 * len(s) / len(rs):4.1f}% of on-time orders, paid/typical median {med([r['paid'] for r in s]):.2f}")
    lt = [r for r in lates if r["paid"] is not None]
    print(f"   late orders that were delivered (n={len(lt)}): paid/typical median {med([r['paid'] for r in lt]):.2f}, p90 {q([r['paid'] for r in lt], .9):.2f}")

    print("\nE. Hours from winning the order to LP (and hours of those that drivers are awake, 07-21)")
    print(f"{'':34}     n   clock p25  med  p75 | awake p25  med  p75 | under 6 awake hours")
    for lab, rs in (("on time", ok), ("late, all causes", lates), ("late, causes 1+2a+2b", nf),
                    ("late, cause 3 (dropped)", [r for r in lates if r["cause"] == "3"]),
                    ("late, causes 5+6", [r for r in lates if r["cause"] in ("5", "6")])):  # fmt: skip
        a, b = [r["win_to_lp"] for r in rs], [r["awake_to_lp"] for r in rs]
        print(f"{lab:34} {len(rs):5d}  {q(a, .25):10.1f} {med(a):4.1f} {q(a, .75):4.1f} | {q(b, .25):9.1f} {med(b):4.1f} {q(b, .75):4.1f} | "
              f"{100 * mean([x < 6 for x in b]):5.1f}%")  # fmt: skip
    print("late rate by awake hours from win to LP:")
    for lo, hi in ((0, 4), (4, 6), (6, 10), (10, 16), (16, 28), (28, 1e9)):
        rs = [r for r in rows if lo <= r["awake_to_lp"] < hi]
        if rs:
            print(f"   {lo:>3}-{'' if hi > 1e6 else hi:<4} h: {len(rs):5d} orders, late {100 * mean([r['late'] for r in rs]):4.1f}%, "
                  f"no-driver late {100 * mean([r['cause'] in ('1', '2a', '2b') for r in rs]):4.1f}%, "
                  f"share of all late {100 * sum(r['late'] for r in rs) / max(1, len(lates)):4.1f}%")  # fmt: skip


if __name__ == "__main__":
    main(sys.argv[1:])
