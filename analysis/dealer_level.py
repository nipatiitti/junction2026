"""Would a per-dealer level learned inside the week sharpen the win curve W?

Thresholds are the geometric midpoints of the two-sided ordered brackets (price / list) in
`src/strategies/recall/memory-<seed>.json`, joined to dealer, arrival time and delivery town from one saved week of
the seed. Per seed, after removing the world-day median and the cross-world threshold model's offset
(`src/params/threshold.json`), it reports:
  (a) the share of residual variance between dealers (one-way, dealers weighted by request count);
  (b) the variance removed by predicting each request from the shrunk mean of the same dealer's earlier requests
      (shrinkage k), over the week and after the dealer's 10th request;
  (c) the same for the delivery town, and for dealer x delivery region;
  (d) drift: correlation of each dealer's first-half and second-half mean;
  (e) the censored version: a Gaussian filter per dealer that sees only win / loss at a price near the prediction.

Usage: uv run python analysis/dealer_level.py   (standard library only)
"""

import gzip
import json
import math
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "data/scrape/runs/L8"
SEEDS = ["spread-1", "spread-2", "spread-3", "spread-4", "spread-5", "spread-9"]
DAY = 1440
CAPITAL = {"helsinki", "espoo", "vantaa", "kauniainen"}
TABLE = json.loads((ROOT / "src/params/threshold.json").read_text())


def offset(r, o):
    legs = r["legs"]
    leg = legs[0]
    cats = TABLE["cats"]
    fee = r.get("referenceFeeCents") or 0
    premium = any(lg["car"]["premium"] for lg in legs)
    priv = any(lg["pickup"]["privateAddress"] or lg["delivery"]["privateAddress"] for lg in legs)
    v = TABLE["intercept"]
    v += cats.get("pickup", {}).get(leg["pickup"]["placeId"], 0)
    v += cats.get("delivery", {}).get(leg["delivery"]["placeId"], 0)
    v += cats.get("premium", {}).get(str(premium), 0)
    v += cats.get("private", {}).get(str(priv), 0)
    if fee:
        v += TABLE.get("listFee", 0) * math.log(o["listPriceCents"] / fee)
    return v


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


def region(place):
    return "capital" if place in CAPITAL else "other"


def rows_of(seed):
    """One row per request: the mean residual of its options with a two-sided bracket."""
    mem = json.loads((ROOT / f"src/strategies/recall/memory-{seed}.json").read_text())["opts"]
    rows = []
    for r in sorted(requests_of(seed), key=lambda r: r["arrivedAt"]):
        ys = []
        for o in r["options"]:
            b = mem.get(f"{r['id']}/{o['kind']}")
            if not b or b[0] is None or b[1] is None or not b[0] < b[1]:
                continue
            ys.append(math.log(math.sqrt(b[0] * b[1])) - offset(r, o))
        if not ys:
            continue
        place = r["legs"][0]["delivery"]["placeId"]
        rows.append(
            {
                "at": r["arrivedAt"],
                "day": r["arrivedAt"] // DAY,
                "y": sum(ys) / len(ys),
                "dealer": r["dealerId"],
                "town": place,
                "dreg": r["dealerId"] + "/" + region(place),
            }
        )
    by_day = {}
    for x in rows:
        by_day.setdefault(x["day"], []).append(x["y"])
    med = {d: statistics.median(v) for d, v in by_day.items()}
    for x in rows:
        x["e"] = x["y"] - med[x["day"]]
    return rows


def between_share(rows, key):
    tot = statistics.fmean(x["e"] for x in rows)
    var = statistics.fmean((x["e"] - tot) ** 2 for x in rows)
    groups = {}
    for x in rows:
        groups.setdefault(x[key], []).append(x["e"])
    between = sum(len(g) * (statistics.fmean(g) - tot) ** 2 for g in groups.values()) / len(rows)
    return between / var, len(groups)


def online(rows, key, k, after=10):
    """Variance removed by predicting from the shrunk mean of the same group's earlier rows (in time order)."""
    s, n = {}, {}
    base = statistics.fmean(x["e"] for x in rows)  # residuals are centred by the day median, so ~0
    se0 = se1 = se0a = se1a = 0.0
    for x in rows:
        g = x[key]
        c = n.get(g, 0)
        pred = s.get(g, 0.0) / (c + k)
        e = x["e"] - base
        se0 += e * e
        se1 += (e - pred) ** 2
        if c >= after:
            se0a += e * e
            se1a += (e - pred) ** 2
        s[g] = s.get(g, 0.0) + e
        n[g] = c + 1
    return 1 - se1 / se0, (1 - se1a / se0a) if se0a else float("nan")


def drift(rows):
    mid = statistics.median(x["at"] for x in rows)
    a, b = {}, {}
    for x in rows:
        (a if x["at"] < mid else b).setdefault(x["dealer"], []).append(x["e"])
    common = [d for d in a if d in b and len(a[d]) >= 5 and len(b[d]) >= 5]
    if len(common) < 3:
        return float("nan"), len(common)
    return statistics.correlation(
        [statistics.fmean(a[d]) for d in common], [statistics.fmean(b[d]) for d in common]
    ), len(common)


def phi(z):
    return 0.5 * math.erfc(-z / math.sqrt(2))


def pdf(z):
    return math.exp(-z * z / 2) / math.sqrt(2 * math.pi)


def censored(rows, prior_sd, noise_sd, seed=0):
    """Gaussian assumed-density filter per dealer that sees only win / loss: each request is quoted at the dealer's
    predicted level plus a jitter (bidprice quotes near the middle of W). Variance removed of the residual."""
    rng = random.Random(seed)
    m, v = {}, {}
    se0 = se1 = 0.0
    for x in rows:
        d = x["dealer"]
        mu, var = m.get(d, 0.0), v.get(d, prior_sd**2)
        e = x["e"]
        se0 += e * e
        se1 += (e - mu) ** 2
        price = mu + rng.gauss(0, 0.1)
        win = price <= e  # threshold at or above the price: accepted
        s = math.sqrt(var + noise_sd**2)
        z = (price - mu) / s
        # Probit update on the dealer level: P(win) = 1 - Phi((price - level) / noise)
        if win:
            p = max(1e-9, 1 - phi(z))
            lam = pdf(z) / p
            mu2 = mu + var / s * lam
            var2 = var * (1 - var / s**2 * lam * (lam - z))
        else:
            p = max(1e-9, phi(z))
            lam = pdf(z) / p
            mu2 = mu - var / s * lam
            var2 = var * (1 - var / s**2 * lam * (lam + z))
        m[d], v[d] = mu2, max(var2, 1e-6)
    return 1 - se1 / se0


def main():
    seeds = sys.argv[1:] or SEEDS
    print(
        "seed       n   sd    (a)dlr  (a)town | (b) k=3 all/after10 | k=8 | k=20 | (c)town k=8 | (c)dlr*reg k=8 | (d)corr | (e)cens"
    )
    for seed in seeds:
        rows = rows_of(seed)
        sd = statistics.pstdev(x["e"] for x in rows)
        a, nd = between_share(rows, "dealer")
        at, _ = between_share(rows, "town")
        bs = [online(rows, "dealer", k) for k in (3, 8, 20)]
        ct = online(rows, "town", 8)
        cr = online(rows, "dreg", 8)
        dr, nc = drift(rows)
        ce = censored(rows, prior_sd=0.04, noise_sd=sd)
        null = (nd - 1) / len(rows)
        fmt = lambda p: f"{p[0]:+.3f}/{p[1]:+.3f}"
        print(
            f"{seed:9} {len(rows):4} {sd:.3f} {a:.3f}({nd},null {null:.3f}) {at:.3f} | {fmt(bs[0])} | {fmt(bs[1])} | {fmt(bs[2])} |"
            f" {fmt(ct)} | {fmt(cr)} | {dr:+.2f}({nc}) | {ce:+.3f}"
        )


if __name__ == "__main__":
    main()
