"""How fast dealer trust is built in the board-config ts-bidprice weeks, and what a faster build would be worth.

Trust is rebuilt from the events: +1 per order delivered on time (at its last leg), halved on a late one, capped at
25. Run: uv run --no-project --python 3.13 python analysis/trust_timing.py
"""

import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "data" / "scrape" / "runs" / "L8"
# The board.json baseline weeks (ROUND4 table).
WEEKS = {
    "spread-6": "w3ff32a79829c94727946",
    "spread-7": "wdf35d90effe2c9324f4c",
    "spread-8": "wb40f39b3c2d538a55f57",
    "spread-10": "wfd9378a5dc666cf3804c",
}
MARKS = (5, 10, 15, 20, 25)
BANDS = ((0, 4), (5, 14), (15, 24), (25, 25))
DAY = 1440


def band_of(t):
    for lo, hi in BANDS:
        if lo <= t <= hi:
            return f"{lo}-{hi}"
    return "25"


def hm(at):
    return "never" if at is None else f"d{at // DAY} {at % DAY // 60:02d}:{at % 60:02d} (h{at / 60:.0f})"


def week(seed, wid):
    d = ROOT / seed / wid
    orders = {}
    changes = []  # (at, dealer, late, count before)
    won_at = {}
    delivered_at = {}
    for line in gzip.open(d / "events.jsonl.gz", "rt"):
        e = json.loads(line)
        k = e["kind"]
        if k == "order_won":
            o = e["order"]
            orders[o["id"]] = {"dealer": o["dealerId"], "deadline": o["deadline"], "left": len(o["legs"]), "option": o["option"]}
            won_at[o["id"]] = e["at"]
        elif k == "order_changed":
            o = orders.get(e["order"]["id"])
            if o:
                o["deadline"] = e["order"]["deadline"]
        elif k == "delivered":
            o = orders.get(e["orderId"])
            if o:
                o["left"] -= 1
                if o["left"] == 0:
                    changes.append((e["at"], o["dealer"], e["at"] > o["deadline"]))
                    delivered_at[e["orderId"]] = e["at"]
    changes.sort()
    reveal = json.load(gzip.open(d / "reveal.json.gz", "rt"))
    rows = sorted(reveal["requests"], key=lambda r: r["request"]["arrivedAt"])

    # Trust timeline per dealer.
    trust = defaultdict(float)
    mark_at = defaultdict(dict)
    halvings = []
    timeline = []  # (at, dealer, count after)
    for at, dealer, late in changes:
        t = trust[dealer]
        if late:
            halvings.append((dealer, t))
            trust[dealer] = t / 2
        else:
            trust[dealer] = min(25, t + 1)
            for m in MARKS:
                if trust[dealer] >= m and m not in mark_at[dealer]:
                    mark_at[dealer][m] = at
        timeline.append((at, dealer, trust[dealer]))

    per_dealer = Counter(r["request"]["dealerId"] for r in rows)
    top5 = [x for x, _ in per_dealer.most_common(5)]
    total = len(rows)

    # Count at each request's arrival.
    cur = defaultdict(float)
    i = 0
    req = []
    for r in rows:
        q = r["request"]
        while i < len(timeline) and timeline[i][0] <= q["arrivedAt"]:
            cur[timeline[i][1]] = timeline[i][2]
            i += 1
        t = cur[q["dealerId"]]
        quote = r.get("quote") or {}
        lists = {o["kind"]: o["listPriceCents"] for o in q["options"]}
        ratios = [c / lists[k] for k, c in quote.items() if k in lists and c / lists[k] < 2.5]
        won = r.get("outcome") == "won"
        price = quote.get(r.get("option")) if won else None
        req.append(
            {
                "at": q["arrivedAt"],
                "dealer": q["dealerId"],
                "t": t,
                "quoted": bool(ratios),
                "ratio": sum(ratios) / len(ratios) if ratios else None,
                "won": won,
                "price": price,
                "list": min(lists.values()),
                "winratio": price / lists[r["option"]] if won else None,
            }
        )

    print(f"\n=== {seed} {wid}: {total} requests, {sum(x['won'] for x in req)} won ===")
    print("Top five dealers: hour each count mark was reached, share of their requests before it")
    for dl in top5:
        mine = [x for x in req if x["dealer"] == dl]
        cells = []
        for m in MARKS:
            at = mark_at[dl].get(m)
            before = sum(1 for x in mine if at is None or x["at"] < at) / len(mine)
            cells.append(f"{m}:{hm(at)} {before:.0%}")
        print(f"  {dl} {len(mine)} req ({len(mine) / total:.0%}) | " + " | ".join(cells))
    print(f"Share of all requests while their dealer's count < 10: {sum(x['t'] < 10 for x in req) / total:.0%}, < 25: {sum(x['t'] < 25 for x in req) / total:.0%}")

    print("By trust band: quotes, win rate, mean quote/list, mean won price/list")
    bstat = {}
    for lo, hi in BANDS:
        b = [x for x in req if x["quoted"] and lo <= x["t"] <= hi]
        if not b:
            print(f"  {lo}-{hi}: none")
            continue
        w = [x for x in b if x["won"]]
        wr = len(w) / len(b)
        mr = sum(x["ratio"] for x in b) / len(b)
        wp = sum(x["winratio"] for x in w) / len(w) if w else 0
        bstat[(lo, hi)] = (wr, mr, wp)
        print(f"  {lo:>2}-{hi:<2}: {len(b):4d} quotes, win {wr:.0%}, quote/list {mr:.2f}, won/list {wp:.2f}")

    print("Monday and Tuesday wins by option; mean hours win -> delivery by option (whole week)")
    for day in (0, 1):
        c = Counter(o["option"] for oid, o in orders.items() if won_at[oid] // DAY == day)
        print(f"  day {day}: {dict(c)}")
    lag = defaultdict(list)
    for oid, at in delivered_at.items():
        lag[orders[oid]["option"]].append((at - won_at[oid]) / 60)
    print("  lag h: " + ", ".join(f"{k} {sum(v) / len(v):.1f}" for k, v in sorted(lag.items())))

    big = [h for h in halvings if h[0] in top5]
    print(f"Late halvings: {len(halvings)} in all, {len(big)} on top-5 dealers, counts before: {[round(t, 1) for _, t in big]}")

    # Estimate: top-5 reach 25 a day earlier. Requests from those dealers in the 24 h before their actual 25 mark
    # (or the last 24 h of their sub-25 time if never reached) would have met trust 25 instead of their count.
    # Value: list x (25 - count)/100 x win rate at 25 (price lift at the same win rate, pure margin).
    wr25 = bstat.get((25, 25), (None,))[0] or max(v[0] for v in bstat.values())
    gain = 0.0
    n = 0
    for dl in top5:
        mine = [x for x in req if x["dealer"] == dl and x["t"] < 25]
        if not mine:
            continue
        end = mark_at[dl].get(25, mine[-1]["at"] + 1)
        window = [x for x in mine if end - DAY <= x["at"] < end]
        n += len(window)
        gain += sum(x["list"] * (25 - x["t"]) / 100 * wr25 for x in window)
    print(f"Estimate: {n} top-5 requests in the day before their 25 mark; price lift x win rate {wr25:.0%} -> EUR {gain / 100:,.0f}")
    return gain / 100


def main():
    gains = [week(s, w) for s, w in WEEKS.items()]
    print(f"\nMean estimated gain from top-5 dealers reaching 25 a day earlier: EUR {sum(gains) / len(gains):,.0f} a week")


if __name__ == "__main__":
    main()
