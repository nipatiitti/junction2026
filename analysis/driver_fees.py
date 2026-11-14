"""How much a driver-side price model and direct offers could save, measured on the saved weeks.

Standard library only. Run: `uv run --no-project --python 3.13 python analysis/driver_fees.py`
(or `uv run python -m analysis.driver_fees`). Reads `data/scrape/runs/L8/<seed>/<world>/` and reports:

1. fees paid over typical, and how bookings happened (first step, raise, repost, urgent ramp, offer);
2. views before a booking, and what the booking driver's wait for a raise cost (fee booked minus the lowest fee
   that driver had already seen on that gig);
3. whether a driver's booked fee over typical follows their distances, rating or completed gigs;
4. direct offers of any policy: acceptance by distance and, for accepted ones, by fee over typical.
"""

import gzip
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "data" / "scrape" / "runs"
SEEDS = [f"spread-{i}" for i in range(1, 11)]


def load_places():
    m = json.loads((ROOT / "map.json").read_text())
    return {p["id"]: (p["lat"], p["lon"]) for p in m["places"]}


PLACES = load_places()


def km(a, b):
    if a not in PLACES or b not in PLACES:
        return float("nan")
    (la1, lo1), (la2, lo2) = PLACES[a], PLACES[b]
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = p2 - p1, math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def weeks(policy_filter):
    for seed in SEEDS:
        for meta_path in sorted((ROOT / "L8" / seed).glob("*/meta.json")):
            meta = json.loads(meta_path.read_text())
            if not meta.get("revealed") or not meta.get("score"):
                continue
            if policy_filter(meta.get("policy", "")):
                yield seed, meta_path.parent, meta


def load(folder):
    events = [json.loads(line) for line in gzip.open(folder / "events.jsonl.gz")]
    reveal = json.load(gzip.open(folder / "reveal.json.gz"))
    drivers = {d["id"]: d for d in json.load(gzip.open(folder / "drivers.json.gz"))}
    snap = json.load(gzip.open(folder / "snapshot.json.gz"))
    return events, reveal, drivers, snap


def week_stats(folder):
    events, reveal, drivers, snap = load(folder)
    reqs = {r["request"]["id"]: r["request"] for r in reveal["requests"]}
    orders = {o["id"]: o for o in snap["orders"]}
    gigs = {g["id"]: g for g in snap["gigs"]}

    def gig_info(g):
        typical, pickup, delivery, keys = 0.0, None, None, []
        for s in g["stops"]:
            o, req = orders.get(s["orderId"]), reqs.get(s["orderId"])
            if o is None or req is None:
                continue
            leg = o["legs"][s["leg"]]
            if s["kind"] == "pickup":
                typical += req["referenceFeeCents"] / max(1, len(o["legs"]))
                keys.append((s["orderId"], s["leg"]))
                pickup = pickup or leg["pickup"]["placeId"]
            else:
                delivery = leg["delivery"]["placeId"]
        return typical, pickup, delivery, keys

    info = {gid: gig_info(g) for gid, g in gigs.items()}
    # Gigs posted earlier for the same car: a later gig is a repost.
    first_post = {}
    for gid, g in sorted(gigs.items(), key=lambda kv: kv[1].get("postedAt", 0)):
        for k in info[gid][3]:
            first_post.setdefault(k, gid)
    views = defaultdict(list)  # gig -> [(at, driver, fee)]
    for v in reveal["views"]:
        views[v["gigId"]].append((v["at"], v["driverId"], v["feeCents"]))
    warned = {}
    accepted_offer, offers = set(), []
    for e in events:
        if e["kind"] == "deadline_close":
            warned.setdefault(e["orderId"], e["at"])
        elif e["kind"] == "offer_answered":
            offers.append(e)
            if e["answer"] == "accepted":
                accepted_offer.add((e["gigId"], e["driverId"]))
    bookings = []
    for e in events:
        if e["kind"] != "gig_booked" or e["gigId"] not in gigs:
            continue
        gid, drv, fee, at = e["gigId"], e["driverId"], e["feeCents"], e["at"]
        typical, pickup, delivery, keys = info[gid]
        if typical <= 0:
            continue
        vs = [v for v in views[gid] if v[0] <= at]
        open_fee = min((v[2] for v in views[gid]), default=fee)
        if (gid, drv) in accepted_offer:
            how = "offer"
        elif any(first_post.get(k) != gid for k in keys):
            how = "repost"
        elif any(o in warned and warned[o] <= at for o, _ in keys):
            how = "urgent"
        elif fee <= open_fee * 1.001:
            how = "first"
        else:
            how = "raise"
        own = [v[2] for v in vs if v[1] == drv]
        d = drivers.get(drv, {})
        home = d.get("homePlaceId")
        bookings.append(
            dict(
                gig=gid,
                driver=drv,
                fee=fee,
                typical=typical,
                ratio=fee / typical,
                how=how,
                viewers=len({v[1] for v in vs}),
                view_ratio=[v[2] / typical for v in vs],
                own_min=min(own) if own else None,
                to_pickup=km(home, pickup),
                from_delivery=km(delivery, home),
                rating=d.get("rating"),
                completed=d.get("completedGigs"),
            )
        )
    offer_rows = []
    for e in offers:
        g = gigs.get(e["gigId"])
        if not g:
            continue
        typical, pickup, delivery, _ = info[e["gigId"]]
        home = drivers.get(e["driverId"], {}).get("homePlaceId")
        booked = next(
            (b for b in bookings if b["gig"] == e["gigId"] and b["driver"] == e["driverId"]),
            None,
        )
        offer_rows.append(
            dict(
                answer=e["answer"],
                to_pickup=km(home, pickup),
                ratio=booked["ratio"] if booked and e["answer"] == "accepted" else None,
            )
        )
    return bookings, offer_rows


def ols(rows, cols):
    """R² and coefficients of ratio on cols (with an intercept), by the normal equations."""
    xs = [[1.0] + [r[c] for c in cols] for r in rows]
    ys = [r["ratio"] for r in rows]
    n, k = len(xs), len(cols) + 1
    if n <= k:
        return float("nan"), []
    a = [[sum(x[i] * x[j] for x in xs) for j in range(k)] for i in range(k)]
    b = [sum(x[i] * y for x, y in zip(xs, ys)) for i in range(k)]
    for i in range(k):  # Gauss-Jordan
        p = max(range(i, k), key=lambda r: abs(a[r][i]))
        a[i], a[p], b[i], b[p] = a[p], a[i], b[p], b[i]
        if abs(a[i][i]) < 1e-12:
            return float("nan"), []
        for r in range(k):
            if r != i:
                f = a[r][i] / a[i][i]
                a[r] = [u - f * w for u, w in zip(a[r], a[i])]
                b[r] -= f * b[i]
    beta = [b[i] / a[i][i] for i in range(k)]
    mean = sum(ys) / n
    sst = sum((y - mean) ** 2 for y in ys)
    sse = sum((y - sum(c * v for c, v in zip(beta, x))) ** 2 for x, y in zip(xs, ys))
    return 1 - sse / sst if sst else float("nan"), beta


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else float("nan")


def main():
    policy = sys.argv[1] if len(sys.argv) > 1 else "ts-bidprice"
    all_b, per_seed = [], defaultdict(list)
    for seed, folder, meta in weeks(lambda p: p == policy):
        b, _ = week_stats(folder)
        per_seed[seed].append(b)
        all_b.extend(b)

    print(f"## 1-2. Fees and views, policy {policy} (means per week)\n")
    hdr = "seed       wks  books  paid/typ  first raise repost urgent offer  viewers  wait EUR/wk  waiters"
    print(hdr)
    tot_wait, tot_weeks = 0.0, 0
    for seed in SEEDS:
        if seed not in per_seed:
            continue
        ws = per_seed[seed]
        bs = [x for w in ws for x in w]
        paid = sum(x["fee"] for x in bs) / sum(x["typical"] for x in bs)
        how = Counter(x["how"] for x in bs)
        wait = sum(max(0, x["fee"] - x["own_min"]) for x in bs if x["own_min"] is not None) / 100
        waiters = sum(1 for x in bs if x["own_min"] is not None and x["fee"] > x["own_min"])
        tot_wait += wait
        tot_weeks += len(ws)
        sh = {k: how[k] / len(bs) for k in ("first", "raise", "repost", "urgent", "offer")}
        print(
            f"{seed:10} {len(ws):3} {len(bs) / len(ws):6.0f} {paid:8.3f}  "
            + " ".join(f"{sh[k]:5.2f}" for k in sh)
            + f"  {statistics.median(x['viewers'] for x in bs):7.0f}  {wait / len(ws):10.0f}  {waiters / len(bs):7.2f}"
        )
    bs = all_b
    paid = sum(x["fee"] for x in bs) / sum(x["typical"] for x in bs)
    print(f"\nall: {tot_weeks} weeks, {len(bs)} bookings, fees paid / typical {paid:.3f}")
    print(
        f"booked fee/typical quartiles {q([x['ratio'] for x in bs], 0.25):.2f} {q([x['ratio'] for x in bs], 0.5):.2f} "
        f"{q([x['ratio'] for x in bs], 0.75):.2f}"
    )
    vr = [r for x in bs for r in x["view_ratio"]]
    print(
        f"viewers before booking: median {q([x['viewers'] for x in bs], 0.5)}, p90 {q([x['viewers'] for x in bs], 0.9)}; "
        f"view fee/typical median {q(vr, 0.5):.2f}"
    )
    had = [x for x in bs if x["own_min"] is not None]
    waited = [x for x in had if x["fee"] > x["own_min"]]
    print(
        f"booking driver had viewed earlier: {len(had) / len(bs):.2f} of bookings; of those paid above their first-seen "
        f"fee: {len(waited) / max(1, len(had)):.2f}"
    )
    print(
        f"paid above the booking driver's lowest seen fee (upper bound on offer saving): EUR {tot_wait / tot_weeks:.0f} "
        f"a week, {sum(x['fee'] for x in waited) and tot_wait * 100 / sum(x['fee'] for x in bs):.1%} of fees"
    )
    if waited:
        print(
            f"  per waited booking: median EUR {q([(x['fee'] - x['own_min']) / 100 for x in waited], 0.5):.1f}, "
            f"ratio over first-seen median {q([x['fee'] / x['own_min'] for x in waited], 0.5):.2f}"
        )
    # Repost/urgent share of the wait
    by = Counter()
    for x in waited:
        by[x["how"]] += (x["fee"] - x["own_min"]) / 100 / tot_weeks
    print("  wait EUR/week by booking kind: " + ", ".join(f"{k} {v:.0f}" for k, v in by.most_common()))

    print("\n## 3. Is a driver's price predictable? OLS of booked fee/typical\n")
    rows = [
        dict(x, log_completed=math.log1p(x["completed"]))
        for x in bs
        if x["rating"] is not None and not math.isnan(x["to_pickup"]) and x["how"] in ("first", "raise")
    ]
    print(
        f"{len(rows)} first-step or raise bookings with driver data; sd of ratio "
        f"{statistics.pstdev(r['ratio'] for r in rows):.3f}"
    )
    for cols in (
        ["to_pickup"],
        ["from_delivery"],
        ["rating"],
        ["log_completed"],
        ["to_pickup", "from_delivery", "rating", "log_completed"],
    ):
        r2, beta = ols(rows, cols)
        print(f"  {'+'.join(cols):45} R2 {r2:.3f}  coef " + ", ".join(f"{c} {v:+.4f}" for c, v in zip(cols, beta[1:])))
    # Per-driver fixed effect: share of variance between drivers with >= 3 bookings (a week-level identity).
    byd = defaultdict(list)
    for r in rows:
        byd[r["driver"]].append(r["ratio"])
    multi = {d: v for d, v in byd.items() if len(v) >= 3}
    ys = [y for v in multi.values() for y in v]
    if ys:
        mu = statistics.fmean(ys)
        sst = sum((y - mu) ** 2 for y in ys)
        ssw = sum((y - statistics.fmean(v)) ** 2 for v in multi.values() for y in v)
        print(
            f"  driver identity (drivers with >=3 bookings, {len(multi)} drivers, {len(ys)} bookings): "
            f"R2 {1 - ssw / sst:.3f} (upper bound, overfits with few bookings each)"
        )
    # The opening fee explains how much? (driver books what is on the board)
    print("\n## 4. Direct offers in saved weeks of any policy\n")
    offers = []
    nweeks = 0
    for seed, folder, meta in weeks(lambda p: True):
        ev_has = False
        with gzip.open(folder / "events.jsonl.gz", "rt") as f:
            for line in f:
                if '"offer_answered"' in line:
                    ev_has = True
                    break
        if not ev_has:
            continue
        nweeks += 1
        offers.extend(week_stats(folder)[1])
    if not offers:
        print("no offers in the saved weeks")
        return
    ans = Counter(o["answer"] for o in offers)
    print(f"{nweeks} weeks with offers, {len(offers)} answers: {dict(ans)}")
    for lo, hi in ((0, 10), (10, 30), (30, 60), (60, 120), (120, 1e9)):
        sub = [o for o in offers if lo <= o["to_pickup"] < hi]
        if sub:
            acc = sum(o["answer"] == "accepted" for o in sub) / len(sub)
            print(f"  home->pickup {lo:>4}-{hi if hi < 1e9 else 'inf':>4} km: {len(sub):5} answers, accepted {acc:.2f}")
    accr = [o["ratio"] for o in offers if o["ratio"] is not None]
    if accr:
        print(f"  accepted offers' fee/typical: quartiles {q(accr, 0.25):.2f} {q(accr, 0.5):.2f} {q(accr, 0.75):.2f}")


if __name__ == "__main__":
    main()
