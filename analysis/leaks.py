"""Where do the missing orders go? Request-by-request look at our ts-bidprice weeks (minValueCents 60)
against every other saved week on the same seed. Standard library only.

uv run --no-project --python 3.13 python analysis/leaks.py
"""

import collections
import gzip
import json
import os
import statistics as st

ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "scrape", "runs", "L8")
SEEDS = ["spread-6", "spread-7", "spread-8", "spread-10"]


def load(seed):
    weeks = []
    for w in sorted(os.listdir(os.path.join(ROOT, seed))):
        d = os.path.join(ROOT, seed, w)
        try:
            meta = json.load(open(os.path.join(d, "meta.json")))
            rev = json.load(gzip.open(os.path.join(d, "reveal.json.gz")))
        except Exception:
            continue
        params = (meta.get("settings") or {}).get("params") or {}
        ours = meta.get("policy") == "ts-bidprice" and params.get("minValueCents") == 60
        weeks.append((w, meta, rev, ours))
    return weeks


def pct(a, b):
    return f"{100 * a / b:5.1f}%" if b else "  -  "


def main():
    agg = collections.Counter()
    by_nq = collections.defaultdict(lambda: [0, 0])
    chosen = collections.Counter()
    by_hour = collections.defaultdict(lambda: [0, 0, 0])
    by_day = collections.defaultdict(lambda: [0, 0, 0])
    by_kind = collections.defaultdict(lambda: [0, 0, 0, 0])  # requests, quoted, won-by-us, won-by-others-elsewhere
    lost_gap = []
    unq_won_elsewhere = []
    lost_won_elsewhere = []
    n_ours = 0
    for seed in SEEDS:
        weeks = load(seed)
        others = [x for x in weeks if not x[3]]
        # best (highest) price at which some other system won each request, per option
        won_else = collections.defaultdict(list)
        for _, _, rev, _ in others:
            for r in rev["requests"]:
                if r["outcome"] == "won" and r.get("option"):
                    q = (r.get("quote") or {}).get(r["option"])
                    if q:
                        won_else[r["request"]["id"]].append((q, r["option"]))
        for w, meta, rev, ours in weeks:
            if not ours:
                continue
            n_ours += 1
            for r in rev["requests"]:
                req = r["request"]
                opts = req["options"]
                q = r.get("quote") or {}
                lp = {o["kind"]: o["listPriceCents"] for o in opts}
                nq = sum(1 for k in lp if k in q and q[k] < 3 * lp[k])
                won = r["outcome"] == "won"
                agg["req"] += 1
                agg[f"opts{len(opts)}"] += 1
                key = "none" if nq == 0 else ("all" if nq == len(opts) else "some")
                agg["q_" + key] += 1
                by_nq[(len(opts), nq)][0] += 1
                by_nq[(len(opts), nq)][1] += won
                if won:
                    agg["won"] += 1
                    chosen[(tuple(sorted(k for k in q if q[k] < 3 * lp[k])), r["option"])] += 1
                day = req["arrivedAt"] // 1440
                hour = (req["arrivedAt"] % 1440) // 60
                for tab, k in ((by_hour, hour), (by_day, day)):
                    tab[k][0] += 1
                    tab[k][1] += nq > 0
                    tab[k][2] += won
                kind = "trade" if len(req["legs"]) > 1 else ("batch" if req.get("batchId") else "single")
                kind += "/" + "+".join(sorted(lp))
                bk = by_kind[kind]
                bk[0] += 1
                bk[1] += nq > 0
                bk[2] += won
                ew = won_else.get(req["id"])
                bk[3] += bool(ew) and not won
                if not won and ew:
                    best = max(ew)
                    if nq == 0:
                        unq_won_elsewhere.append((best[0], best[1], req["referenceFeeCents"], lp[best[1]]))
                    else:
                        ours_q = q.get(best[1])
                        lost_won_elsewhere.append((best[0], ours_q, best[1], req["referenceFeeCents"], lp[best[1]]))
                if not won and nq:
                    k0 = min((k for k in q if q[k] < 3 * lp[k]), key=lambda k: q[k] / lp[k])
                    lost_gap.append(q[k0] / lp[k0])
    W = n_ours
    print(f"our weeks: {W}; per week:")
    for k in ("req", "q_none", "q_some", "q_all", "won", "opts1", "opts2", "opts3"):
        print(f"  {k:8s} {agg[k] / W:7.1f}")
    print("\nwin rate by (options offered, options we quoted): requests/week, win%")
    for k in sorted(by_nq):
        n, w = by_nq[k]
        print(f"  {k}  {n / W:6.1f}  {pct(w, n)}")
    print("\nwhich option the dealer took, given the set we quoted (per week)")
    for k, v in chosen.most_common(15):
        print(f"  {k}  {v / W:5.1f}")
    print("\nby day: req/wk quoted% won% of quoted")
    for k in sorted(by_day):
        a, b, c = by_day[k]
        print(f"  day {k} {a / W:6.1f} {pct(b, a)} {pct(c, b)}")
    print("\nby hour")
    for k in sorted(by_hour):
        a, b, c = by_hour[k]
        print(f"  {k:02d}h {a / W:6.1f} {pct(b, a)} {pct(c, b)}")
    print("\nby kind: req/wk quoted% won%-of-quoted lost-but-won-elsewhere/wk")
    for k in sorted(by_kind, key=lambda k: -by_kind[k][0]):
        a, b, c, d = by_kind[k]
        print(f"  {k:40s} {a / W:6.1f} {pct(b, a)} {pct(c, b)} {d / W:6.1f}")
    print(f"\nunquoted by us but won by another system: {len(unq_won_elsewhere) / W:.1f}/wk")
    if unq_won_elsewhere:
        print(
            "  their price / typical fee median",
            round(st.median(p / f for p, _, f, _ in unq_won_elsewhere if f), 2),
            " / list median",
            round(st.median(p / lp for p, _, _, lp in unq_won_elsewhere), 2),
            " EUR (price-1.05*fee)/wk",
            round(sum(p - 1.05 * f for p, _, f, _ in unq_won_elsewhere) / W / 100),
        )
        c = collections.Counter(o for _, o, _, _ in unq_won_elsewhere)
        print("  by option", {k: round(v / W, 1) for k, v in c.items()})
    print(f"quoted-and-lost by us but won by another system: {len(lost_won_elsewhere) / W:.1f}/wk")
    if lost_won_elsewhere:
        rat = [o / t for t, o, *_ in lost_won_elsewhere if o]
        print("  our quote / their winning price, median", round(st.median(rat), 3))
        nq_opt = sum(1 for t, o, *_ in lost_won_elsewhere if o is None)
        print(f"  ...of which we did not quote the option they won: {nq_opt / W:.1f}/wk")
        print(
            "  EUR (their price-1.05*fee)/wk",
            round(sum(t - 1.05 * f for t, _, _, f, _ in lost_won_elsewhere) / W / 100),
        )
        for lo, hi in ((0, 1.05), (1.05, 1.15), (1.15, 1.3), (1.3, 9)):
            print(f"  ratio {lo}-{hi}: {sum(1 for r in rat if lo <= r < hi) / W:.1f}/wk")
    print("\nlost quotes, our quote/list on cheapest option: quartiles", [round(x, 2) for x in st.quantiles(lost_gap, n=4)])


if __name__ == "__main__":
    main()
