"""Post-mortem of late and undelivered orders in saved ts-bidprice weeks.

For every late or undelivered order, rebuild its story from the events and our
journal and name the first cause in the chain (a-h, see CAUSES). Splits weeks into
normal-volume (on time >= 92%) and high-volume (400+ orders or under 90% on time).

Run: uv run --no-project --python 3.13 python analysis/late_causes.py
"""

import collections
import glob
import gzip
import json
import os
import statistics
from pathlib import Path

MAIN = "/home/nipatiitti/projects/hackathons/junction2026"
RUNS = os.path.join(os.path.dirname(__file__), "..", "data", "scrape", "runs", "L8")
SEEDS = ["spread-6", "spread-7", "spread-8", "spread-10"]
CAUSES = {
    "a": "won with too little slack",
    "b": "posted late or held",
    "c": "no booking until close to pickup",
    "d": "booked then dropped / no-show",
    "e": "driver late / failed visit",
    "f": "order changed / snow",
    "g": "picked up in time, delivered late",
    "h": "other (booked early, picked up late)",
}
SLACK_A = 60  # minutes of slack beyond the drive at the win below which it is (a)
POST_B = 60  # minutes between win and first post beyond which it is (b)
BOOK_C = 90  # booked later than this before the latest pickup is (c)
CAUSE_OF = {}  # (world, order id) -> cause letter, filled by main() for analysis/unseen.py


def load_gz(path):
    with gzip.open(path, "rt") as f:
        if path.endswith(".jsonl.gz"):
            return [json.loads(line) for line in f]
        return json.load(f)


def find_journal(world):
    for p in [f"{MAIN}/out/journal/{world}.jsonl", *glob.glob(f"{MAIN}/.claude/worktrees/*/out/journal/{world}.jsonl")]:
        if os.path.exists(p):
            return p
    return None


def weeks():
    for seed in SEEDS:
        for d in sorted(glob.glob(f"{RUNS}/{seed}/*/")):
            meta = json.loads(Path(d, "meta.json").read_text())
            if meta.get("policy") != "ts-bidprice":
                continue
            world = os.path.basename(d.rstrip("/"))
            j = find_journal(world)
            if j:
                yield seed, world, d, meta, json.loads(Path(d, "score.json").read_text()), j


def main():
    all_weeks = list(weeks())
    # drive times by place pair across every week
    drive = collections.defaultdict(list)
    for _, _, d, _, _, _ in all_weeks:
        rev = load_gz(d + "reveal.json.gz")
        req = {r["request"]["id"]: r["request"] for r in rev["requests"]}
        for o in rev["orders"]:
            r = req.get(o["orderId"])
            for i, lg in enumerate(o["legs"]):
                if r and lg["pickedUpAt"] is not None and lg["deliveredAt"] is not None and i < len(r["legs"]):
                    pair = (r["legs"][i]["pickup"]["placeId"], r["legs"][i]["delivery"]["placeId"])
                    drive[pair].append(lg["deliveredAt"] - lg["pickedUpAt"])
    drive_med = {k: statistics.median(v) for k, v in drive.items()}
    glob_med = statistics.median([x for v in drive.values() for x in v])

    table = {"normal": collections.Counter(), "high": collections.Counter()}
    refunds = {"normal": collections.Counter(), "high": collections.Counter()}
    totals = {"normal": [0, 0], "high": [0, 0]}
    detail = {"normal": collections.defaultdict(list), "high": collections.defaultdict(list)}
    booked_stats = {"normal": [], "high": []}  # (lead before latest pickup, fee/ref, views) for every booked gig
    by_option = {"normal": collections.Counter(), "high": collections.Counter()}
    won_option = {"normal": collections.Counter(), "high": collections.Counter()}
    by_pickday = {"normal": collections.Counter(), "high": collections.Counter()}

    for seed, world, d, meta, score, jpath in all_weeks:
        grp = "high" if score["wonOrders"] >= 400 or score["onTimeShare"] < 0.9 else "normal"
        totals[grp][0] += 1
        totals[grp][1] += score["wonOrders"]
        ev = load_gz(d + "events.jsonl.gz")
        rev = load_gz(d + "reveal.json.gz")
        req = {r["request"]["id"]: r["request"] for r in rev["requests"]}
        ref = {k: v["referenceFeeCents"] for k, v in req.items()}
        legs_rev = {o["orderId"]: o["legs"] for o in rev["orders"]}
        won, changed, gig_ev, refund = (
            {},
            collections.defaultdict(list),
            collections.defaultdict(list),
            collections.Counter(),
        )
        snow = []
        views = collections.Counter()
        for e in ev:
            k = e["kind"]
            if k == "order_won":
                won[e["order"]["id"]] = (e["at"], e["order"])
            elif k == "order_changed":
                changed[e["order"]["id"]].append(e["at"])
                won[e["order"]["id"]] = (won.get(e["order"]["id"], (e["at"],))[0], e["order"])
            elif k == "forecast":
                snow.append((e["from"], e["to"], set(e.get("placeIds", []))))
            elif k == "gig_viewed":
                views[e["gigId"]] += 1
            elif k == "ledger":
                ln = e["line"]
                if ln.get("orderId") and ln["cents"] < 0 and ln["kind"] != "fee":
                    refund[ln["orderId"]] -= ln["cents"]
            if "gigId" in e and k not in ("gig_viewed",):
                gig_ev[e["gigId"]].append(e)
        posts = collections.defaultdict(list)  # order -> [(at, gigId, first fee, n reprices)]
        reprices = collections.Counter()
        first_fee = {}
        with Path(jpath).open() as stream:
            for line in stream:
                x = json.loads(line)
                a = x["action"]
                if a["type"] == "post" and x["result"].get("ok"):
                    g = x["result"]["id"]
                    first_fee[g] = a["schedule"][0]["feeCents"]
                    for oid in {s["orderId"] for s in a["stops"]}:
                        posts[oid].append((x["at"], g))
                elif a["type"] == "reprice":
                    reprices[a["gigId"]] += 1
        gig_orders = collections.defaultdict(set)
        for oid, ps in posts.items():
            for _, g in ps:
                gig_orders[g].add(oid)

        for oid, (wat, order) in won.items():
            r = req.get(oid)
            L = legs_rev.get(oid, [])
            D = order["deadline"]
            leg0 = order["legs"][0]
            pair = (leg0["pickup"]["placeId"], leg0["delivery"]["placeId"])
            dr = drive_med.get(pair, glob_med)
            ready = max(wat, leg0["pickup"]["window"]["from"])
            latest_pick = D - dr
            won_option[grp][order["option"]] += 1
            for _, g in posts.get(oid, []):
                b = next((e for e in gig_ev[g] if e["kind"] == "gig_booked"), None)
                if b:
                    booked_stats[grp].append((latest_pick - b["at"], b["feeCents"] / max(1, ref.get(oid, 1)), views[g]))
            delivered = [lg["deliveredAt"] for lg in L]
            late = any(x is None for x in delivered) or (delivered and max(delivered) > D)
            if not late or order.get("cancelled"):
                continue
            if r is None:
                continue
            by_option[grp][order["option"]] += 1
            by_pickday[grp][int(ready // 1440)] += 1
            gigs = [g for _, g in sorted(posts.get(oid, []))]
            gev = sorted([e for g in gigs for e in gig_ev[g]], key=lambda e: e["seq"])
            booked = [e for e in gev if e["kind"] == "gig_booked"]
            drops = [e for e in gev if e["kind"] in ("gig_dropped", "no_show")]
            bad = [e for e in gev if e["kind"] in ("driver_late", "visit_failed")]
            picked = L[0]["pickedUpAt"] if L else None
            first_post = min((a for a, _ in posts.get(oid, [])), default=None)
            snowed = any(f <= latest_pick and t >= ready and pair[0] in p | {pair[1]} for f, t, p in snow) or any(
                f <= latest_pick and t >= ready and pair[1] in p for f, t, p in snow
            )
            slack = latest_pick - ready
            if changed.get(oid) or snowed:
                c = "f"
                info = {"changed": bool(changed.get(oid)), "snow": snowed}
            elif slack < SLACK_A:
                c = "a"
                info = {"slack_min": round(slack), "option": order["option"]}
            elif first_post is None or first_post - wat > POST_B:
                c = "b"
                info = {"gap": None if first_post is None else first_post - wat}
            elif drops and (not booked or drops[0]["seq"] < booked[-1]["seq"] or picked is None):
                c = "d"
                dr0 = drops[0]
                rebook = next((e for e in booked if e["seq"] > dr0["seq"]), None)
                info = {
                    "lead_at_drop": round(latest_pick - dr0["at"]),
                    "rebook_after": None if rebook is None else rebook["at"] - dr0["at"],
                    "kind": dr0["kind"],
                }
            elif not booked or booked[0]["at"] > latest_pick - BOOK_C:
                c = "c"
                b = booked[0] if booked else None
                g = b["gigId"] if b else (gigs[0] if gigs else None)
                info = {
                    "open_h": round(((b["at"] if b else latest_pick) - (first_post or wat)) / 60, 1),
                    "lead_min": None if not b else round(latest_pick - b["at"]),
                    "fee_ref": None if not b else round(b["feeCents"] / max(1, ref.get(oid, 1)), 2),
                    "fee_first": None if not g else round(first_fee.get(g, 0) / max(1, ref.get(oid, 1)), 2),
                    "views": views[g] if g else 0,
                    "reprices": reprices[g] if g else 0,
                    "hour": None if not b else round((b["at"] % 1440) / 60, 1),
                }
            elif bad:
                c = "e"
                info = {"kind": bad[0]["kind"], "reason": bad[0].get("reason")}
            elif picked is not None and picked <= latest_pick:
                c = "g"
                info = {"pick_to_deadline": D - picked, "drive_med": dr, "actual": (max(delivered) or 0) - picked}
            else:
                c = "h"
                info = {
                    "booked_lead": round(latest_pick - booked[0]["at"]),
                    "picked_late_by": None if picked is None else round(picked - latest_pick),
                }
            CAUSE_OF[(world, oid)] = c
            table[grp][c] += 1
            refunds[grp][c] += refund.get(oid, 0)
            detail[grp][c].append(info)

    for grp in ("normal", "high"):
        n = sum(table[grp].values())
        print(f"\n== {grp}: {totals[grp][0]} weeks, {totals[grp][1]} orders, {n} late/undelivered ==")
        print("late by option:", dict(by_option[grp]), "won by option:", dict(won_option[grp]))
        print("late by ready day:", dict(sorted(by_pickday[grp].items())))
        for c in "abcdefgh":
            k = table[grp][c]
            print(f"  {c} {CAUSES[c]:40s} {k:4d} {k / max(1, n):5.1%}  EUR {refunds[grp][c] / 100:8.0f}")
        for c in "acdgh":
            rows = detail[grp][c]
            if not rows:
                continue
            print(f"  -- {c} details ({len(rows)}):")
            keys = rows[0].keys()
            for key in keys:
                vals = [
                    r[key] for r in rows if isinstance(r.get(key), (int, float)) and not isinstance(r.get(key), bool)
                ]
                if vals:
                    q = statistics.quantiles(vals, n=4) if len(vals) > 1 else [vals[0]] * 3
                    print(f"     {key}: n={len(vals)} p25={q[0]:.1f} med={q[1]:.1f} p75={q[2]:.1f}")
                else:
                    print(f"     {key}: {collections.Counter(str(r.get(key)) for r in rows).most_common(4)}")
        bs = booked_stats[grp]
        if bs:
            print("  all booked gigs: lead before latest pickup (min) by bucket -> count, median fee/ref, median views")
            for lo, hi in [(-9999, 0), (0, 90), (90, 240), (240, 720), (720, 99999)]:
                sel = [b for b in bs if lo <= b[0] < hi]
                if sel:
                    print(
                        f"     [{lo},{hi}) n={len(sel)} fee/ref={statistics.median([s[1] for s in sel]):.2f}"
                        f" views={statistics.median([s[2] for s in sel])}"
                    )


if __name__ == "__main__":
    main()
