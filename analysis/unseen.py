"""Gigs no driver sees: what was known at quote time about the cause-c orders of analysis/late_causes.py
(no driver booked until close to the pickup), against every other won order, and the net euros of a rule
"fewer than K roster drivers within R km of the pickup".

Run: uv run --no-project --python 3.13 python analysis/unseen.py
"""

import collections
import contextlib
import io
import json
import math
import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import late_causes as lc

MAP_PATH = Path(__file__).parent / ".." / "data" / "scrape" / "runs" / "map.json"
MAP = json.loads(MAP_PATH.read_text())
POS = {p["id"]: (p["lat"], p["lon"]) for p in MAP["places"]}


def km(a, b):
    (la1, lo1), (la2, lo2) = POS[a], POS[b]
    x = math.radians(lo2 - lo1) * math.cos(math.radians((la1 + la2) / 2))
    return 6371 * math.hypot(x, math.radians(la2 - la1))


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        lc.main()
    rows = []  # (seed, world, cause, margin EUR, feats)
    weeks = collections.Counter()
    viewers = []  # (hours since post, viewer home km from pickup) for cause-c gigs
    for seed, world, d, _meta, score, jpath in lc.weeks():
        if score["wonOrders"] >= 400 or score["onTimeShare"] < 0.9:
            continue  # normal weeks only, as the post-mortem's headline
        weeks[seed] += 1
        roster = lc.load_gz(d + "drivers.json.gz")
        homes = [r["homePlaceId"] for r in roster]
        near = {p: [sum(km(p, h) <= r for h in homes) for r in (30, 60, 100)] for p in POS}
        towns = [p for p, c in collections.Counter(homes).items() if c >= 20]
        margin = collections.Counter()
        won = {}
        gig_order, post_at = {}, {}
        with Path(jpath).open() as stream:
            for line in stream:
                x = json.loads(line)
                if x["action"]["type"] == "post" and x["result"].get("ok"):
                    for s in x["action"]["stops"]:
                        gig_order[x["result"]["id"]] = s["orderId"]
                    post_at[x["result"]["id"]] = x["at"]
        for e in lc.load_gz(d + "events.jsonl.gz"):
            if e["kind"] == "order_won":
                won[e["order"]["id"]] = e["order"]
            elif e["kind"] == "ledger":
                ln = e["line"]
                oid = ln.get("orderId") or gig_order.get(ln.get("gigId"))
                if oid:
                    margin[oid] += ln["cents"]
        rev = lc.load_gz(d + "reveal.json.gz")
        home = {r["id"]: r["homePlaceId"] for r in roster}
        for oid, o in won.items():
            leg = o["legs"][0]
            pu, de = leg["pickup"]["placeId"], leg["delivery"]["placeId"]
            f = {
                "pu30": near[pu][0],
                "pu60": near[pu][1],
                "pu100": near[pu][2],
                "de30": near[de][0],
                "pu_town": min((km(pu, t) for t in towns), default=999),
                "km": km(pu, de),
                "opt": o["option"],
                "day": int(leg["pickup"]["window"]["from"] // 1440),
                "prem": leg["car"]["premium"],
                "priv": leg["pickup"]["privateAddress"] or leg["delivery"]["privateAddress"],
            }
            rows.append((seed, world, lc.CAUSE_OF.get((world, oid), "ok"), margin[oid] / 100, f))
        for v in rev["views"]:
            oid = gig_order.get(v["gigId"])
            if oid and lc.CAUSE_OF.get((world, oid)) == "c" and v["driverId"] in home and oid in won:
                pu = won[oid]["legs"][0]["pickup"]["placeId"]
                viewers.append(((v["at"] - post_at[v["gigId"]]) / 60, km(pu, home[v["driverId"]])))
    nweeks = sum(weeks.values())
    print(f"{nweeks} normal weeks {dict(weeks)}, {len(rows)} won orders, {sum(r[2] == 'c' for r in rows)} cause c")
    for key in ("pu30", "pu60", "pu100", "de30", "pu_town", "km"):
        cc = [r[4][key] for r in rows if r[2] == "c"]
        ok = [r[4][key] for r in rows if r[2] == "ok"]
        print(f"  {key:8s} cause c median {statistics.median(cc):6.1f}   on-time median {statistics.median(ok):6.1f}")
    for key in ("opt", "prem", "priv", "day"):
        cc = collections.Counter(r[4][key] for r in rows if r[2] == "c")
        al = collections.Counter(r[4][key] for r in rows)
        print(f"  {key}: " + ", ".join(f"{k}={cc[k]}/{al[k]} ({cc[k] / al[k]:.0%})" for k in sorted(al, key=str)))
    print("rule: decline when roster drivers within R km of the pickup < K (per week)")
    for key in ("pu30", "pu60"):
        for k in (1, 2, 3, 5, 8):
            sel = [r for r in rows if r[4][key] < k]
            c = [r for r in sel if r[2] == "c"]
            o = [r for r in sel if r[2] != "c"]
            print(
                f"  {key}<{k}: c {len(c) / nweeks:4.1f} (margin EUR {sum(r[3] for r in c) / nweeks:7.0f}), "
                f"others {len(o) / nweeks:5.1f} (margin EUR {sum(r[3] for r in o) / nweeks:7.0f}), "
                f"net {-sum(r[3] for r in sel) / nweeks:+7.0f}/wk  by seed: "
                + " ".join(
                    f"{s}:c{sum(r[2] == 'c' for r in sel if r[0] == s) / weeks[s]:.1f}"
                    f"/o{sum(r[2] != 'c' for r in sel if r[0] == s) / weeks[s]:.1f}"
                    f"/{-sum(r[3] for r in sel if r[0] == s) / weeks[s]:+.0f}"
                    for s in sorted(weeks)
                )
            )
    print("rule: decline when the leg is >= L km and pu30 < K (per week)")
    for leg_km in (200, 300, 400):
        for k in (10, 20, 40, 999):
            sel = [r for r in rows if r[4]["km"] >= leg_km and r[4]["pu30"] < k]
            c = [r for r in sel if r[2] == "c"]
            print(
                f"  km>={leg_km} pu30<{k}: c {len(c) / nweeks:4.1f}, others {(len(sel) - len(c)) / nweeks:5.1f}, "
                f"net {-sum(r[3] for r in sel) / nweeks:+7.0f}/wk  by seed: "
                + " ".join(f"{s}:{-sum(r[3] for r in sel if r[0] == s) / weeks[s]:+.0f}" for s in sorted(weeks))
            )
    by_h = collections.Counter(min(int(h // 6) * 6, 48) for h, _ in viewers)
    print("cause-c gig views by hours since post (6 h buckets, 48 = 48+):", dict(sorted(by_h.items())))
    if viewers:
        ks = [k for _, k in viewers]
        print(
            f"  viewer home km from pickup: median {statistics.median(ks):.0f}, within 30 km {sum(k <= 30 for k in ks) / len(ks):.0%}"
        )


if __name__ == "__main__":
    main()
