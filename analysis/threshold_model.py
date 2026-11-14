"""How much of the per-request threshold scatter is predictable across worlds from what is known at quote time.

Joins the trust-free threshold brackets in `src/strategies/recall/memory-<seed>.json` (midpoint where both sides are
known and in order) to each request's features from one saved week of the seed, fits a ridge regression of
log(threshold / world median) on the features on five seeds and tests it on the sixth. Writes the table fitted on
all six seeds to `src/params/threshold.json`.

Usage: uv run python analysis/threshold_model.py
"""

import gzip
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "data/scrape/runs/L8"
SEEDS = ["spread-1", "spread-2", "spread-3", "spread-4", "spread-5", "spread-9"]
DAY = 1440
CAPITAL = {"helsinki", "espoo", "vantaa", "kauniainen"}


def requests_of(seed):
    for world in sorted((RUNS / seed).iterdir()):
        ev = world / "events.jsonl.gz"
        if not ev.exists():
            continue
        out = []
        with gzip.open(ev, "rt") as f:
            for line in f:
                e = json.loads(line)
                if e["kind"] == "price_request":
                    out.append(e["request"])
        if len(out) > 500:
            return out
    return []


def rows_of(seed):
    mem = json.loads((ROOT / f"src/strategies/recall/memory-{seed}.json").read_text())["opts"]
    batch_size = {}
    reqs = requests_of(seed)
    for r in reqs:
        if r.get("batchId"):
            batch_size[r["batchId"]] = batch_size.get(r["batchId"], 0) + 1
    rows = []
    for r in reqs:
        legs = r["legs"]
        leg = legs[0]
        fee = r.get("referenceFeeCents") or 0
        note = r.get("note")
        for i, o in enumerate(r["options"]):
            b = mem.get(f"{r['id']}/{o['kind']}")
            if not b or b[0] is None or b[1] is None or not b[0] < b[1]:
                continue
            thr = math.sqrt(b[0] * b[1])
            rows.append(
                {
                    "seed": seed,
                    "day": r["arrivedAt"] // DAY,
                    "y": math.log(thr),
                    "dealer": r["dealerId"],
                    "option": o["kind"],
                    "rung": str(i),
                    "pickup": leg["pickup"]["placeId"],
                    "delivery": leg["delivery"]["placeId"],
                    "capital": str(leg["delivery"]["placeId"] in CAPITAL),
                    "legs": str(min(len(legs), 3)),
                    "premium": str(any(lg["car"]["premium"] for lg in legs)),
                    "electric": str(any(lg["car"]["electric"] for lg in legs)),
                    "private": str(
                        sum(lg["pickup"]["privateAddress"] + lg["delivery"]["privateAddress"] for lg in legs) > 0
                    ),
                    "batch": str(min(batch_size.get(r.get("batchId"), 1), 4)),
                    "weekday": str((r["arrivedAt"] // DAY) % 7),
                    "hour": str((r["arrivedAt"] % DAY) // 180),
                    "note": (note or {}).get("language", "none") if note else "none",
                    "listfee": math.log(o["listPriceCents"] / fee) if fee else 0.0,
                    "loglist": math.log(o["listPriceCents"]),
                }
            )
    return rows


CATS = ["dealer", "option", "rung", "pickup", "delivery", "capital", "legs", "premium", "electric", "private", "batch",
        "weekday", "hour", "note"]
NUMS = ["listfee", "loglist"]


def design(rows, cats, nums, levels=None):
    if levels is None:
        levels = {c: sorted({r[c] for r in rows}) for c in cats}
    cols = []
    for c in cats:
        vals = np.array([r[c] for r in rows])
        cols.append((vals[:, None] == np.array(levels[c])[None, :]).astype(float))
    for n in nums:
        cols.append(np.array([[r[n]] for r in rows]))
    X = np.concatenate(cols, 1) if cols else np.zeros((len(rows), 0))
    return X, levels


def target(rows, by_day):
    """log threshold minus the median of its world (or of its world's day): the world level the online filter learns."""
    y = np.array([r["y"] for r in rows])
    keys = [(r["seed"], r["day"]) if by_day else r["seed"] for r in rows]
    med = {}
    for k in set(keys):
        med[k] = float(np.median(y[[i for i, kk in enumerate(keys) if kk == k]]))
    return y - np.array([med[k] for k in keys])


def fit(X, y, lam=3.0):
    mu = X.mean(0)
    Xc = X - mu
    beta = np.linalg.solve(Xc.T @ Xc + lam * np.eye(X.shape[1]), Xc.T @ (y - y.mean()))
    return beta, mu, y.mean()


def predict(X, model):
    beta, mu, y0 = model
    return (X - mu) @ beta + y0


def cv(rows, cats, nums, by_day):
    out = {}
    for held in SEEDS:
        tr = [r for r in rows if r["seed"] != held]
        te = [r for r in rows if r["seed"] == held]
        Xtr, lev = design(tr, cats, nums)
        Xte, _ = design(te, cats, nums, lev)
        ytr, yte = target(tr, by_day), target(te, by_day)
        m = fit(Xtr, ytr)
        res = yte - predict(Xte, m)
        res -= np.median(res)
        out[held] = (float(np.std(yte)), float(np.std(res)), len(te))
    return out


def main():
    rows = [r for s in SEEDS for r in rows_of(s)]
    print(f"{len(rows)} options with a two-sided bracket")
    for by_day in (False, True):
        print(f"\n== target: log(threshold / {'world-day' if by_day else 'world'} median) ==")
        full = cv(rows, CATS, NUMS, by_day)
        print("held-out seed: n, sd before, sd after (all features), share of variance removed")
        for s, (b, a, n) in full.items():
            print(f"  {s}: n={n} sd {b:.4f} -> {a:.4f}  ({1 - (a / b) ** 2:+.1%})")
        mean_after = np.mean([a for _, a, _ in full.values()])
        print(f"  mean sd after: {mean_after:.4f}")
        print("feature alone (mean held-out sd after) / drop-one (mean held-out sd after):")
        for f in CATS + NUMS:
            c1 = [f] if f in CATS else []
            n1 = [f] if f in NUMS else []
            alone = np.mean([a for _, a, _ in cv(rows, c1, n1, by_day).values()])
            cr = [c for c in CATS if c != f]
            nr = [n for n in NUMS if n != f]
            drop = np.mean([a for _, a, _ in cv(rows, cr, nr, by_day).values()])
            print(f"  {f:10s} alone {alone:.4f}   without {drop:.4f}")
        sys.stdout.flush()

    # Dealer stability: dealer mean residual in each seed, correlation across seeds.
    y = target(rows, True)
    dealers = sorted({r["dealer"] for r in rows})
    tab = np.full((len(SEEDS), len(dealers)), np.nan)
    for i, s in enumerate(SEEDS):
        for j, d in enumerate(dealers):
            v = [y[k] for k, r in enumerate(rows) if r["seed"] == s and r["dealer"] == d]
            if len(v) >= 5:
                tab[i, j] = np.mean(v)
    cors = []
    for i in range(len(SEEDS)):
        for k in range(i + 1, len(SEEDS)):
            ok = ~np.isnan(tab[i]) & ~np.isnan(tab[k])
            cors.append(np.corrcoef(tab[i, ok], tab[k, ok])[0, 1])
    print(f"\ndealer mean (world-day) across seeds: mean pairwise correlation {np.mean(cors):.3f}")

    # Final table on all seeds, world-day target, the features the strategy can see.
    # Dealer id does not transfer (pairwise correlation about 0), so the table keeps the place, car and price terms.
    cats = ["pickup", "delivery", "premium", "private"]
    nums = ["listfee"]
    print("lean model (pickup, delivery, premium, private, list/fee), world-day target, held-out sd:")
    for s, (b, a, n) in cv(rows, cats, nums, True).items():
        print(f"  {s}: sd {b:.4f} -> {a:.4f}  ({1 - (a / b) ** 2:+.1%})")
    X, lev = design(rows, cats, nums)
    yy = target(rows, True)
    beta, mu, y0 = fit(X, yy)
    pred = (X - mu) @ beta
    table = {"intercept": 0.0, "cats": {}, "listFee": 0.0}
    k = 0
    for c in cats:
        table["cats"][c] = {}
        for v in lev[c]:
            table["cats"][c][v] = round(float(beta[k]), 4)
            k += 1
    table["listFee"] = round(float(beta[k]), 4)
    # offset = intercept + sum of the request's category values + listFee x log(list / typical fee): zero on average.
    table["intercept"] = round(float(-(mu @ beta)), 4)
    table["note"] = "log offset of the threshold from the world-day level; fitted by analysis/threshold_model.py"
    table["sdBefore"] = round(float(np.std(yy)), 4)
    table["sdAfterInSample"] = round(float(np.std(yy - pred)), 4)
    out = ROOT / "src/params/threshold.json"
    out.write_text(json.dumps(table, indent=1) + "\n")
    print(f"wrote {out}")
    print(f"\nlistFee slope {table['listFee']:+.3f}")
    for c in cats:
        print(c, {k2: v for k2, v in table["cats"][c].items()})


if __name__ == "__main__":
    main()
