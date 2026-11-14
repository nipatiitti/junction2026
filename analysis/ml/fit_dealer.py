"""Fits the dealer model: the hidden limit of one option of one request, as a multiple of its list price.

    uv run --python 3.13 --with numpy --with pandas --with scipy --with scikit-learn python fit_dealer.py

Model: P(win at price ratio r) = sigmoid(a * (mu(x) + b[seed, day] - log r)).
  mu(x)        what the dispatcher can see: lane, dealer, option, hour, trust, the dealer's wins and losses, ...
  b[seed, day] the level of that world on that day (the competitor's level, its day factor, the price war): the same
               for every policy that played the seed, so it is a nuisance intercept in training. In a live week it
               is unknown and learned from the week's own wins and losses (the `online` evaluator below, the same
               diagonal Kalman step as src/strategies/lean/demand.ts).
Test: the probe flips (quote_flips.csv), whose seeds are kept out of training.
"""

from __future__ import annotations

import json
import re
import sys

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.linear_model import LogisticRegression

TEST_SEED = re.compile(r"^(pr-|scrape-|p3q-|p3f-)")
PLACES: list[str] = []
DEALERS = [f"D{i:02d}" for i in range(1, 41)]
OPTIONS = ["same_day", "next_day", "within_3_days"]
LIST_EDGES = [3000, 4000, 5500, 7000, 9000, 12000]
HOURS = list(range(8, 19))
# The effects that are the same in every world. Dealers, hours, notes, addresses and batches carry under 2% each.
KEEP = {"option", "offered", "option_offered", "from", "to", "lane", "list", "log_list", "log_ref_over_list", "trust",
        "late", "win_balance", "win_share"}


def n_offered(v) -> int:
    s = str(v)
    return int(s) if s.isdigit() else s.count("|") + 1


def static_features(df: pd.DataFrame) -> tuple[sparse.csr_matrix, list[str]]:
    """The features a dispatcher sees at the request's arrival, without the price and without the world's level."""
    n = len(df)
    cols: list[np.ndarray] = []
    rows: list[np.ndarray] = []
    vals: list[np.ndarray] = []
    names: list[str] = []
    idx = np.arange(n)

    def onehot(codes: np.ndarray, labels: list[str], prefix: str) -> None:
        base = len(names)
        ok = codes >= 0
        rows.append(idx[ok]); cols.append(base + codes[ok]); vals.append(np.ones(ok.sum()))
        names.extend(f"{prefix}:{label}" for label in labels)

    def numeric(v: np.ndarray, name: str) -> None:
        v = np.nan_to_num(np.asarray(v, dtype=float))
        nz = v != 0
        rows.append(idx[nz]); cols.append(np.full(nz.sum(), len(names))); vals.append(v[nz])
        names.append(name)

    code = lambda series, labels: pd.Categorical(series, categories=labels).codes.astype(int)
    onehot(code(df.option, OPTIONS), OPTIONS, "option")
    offered = df.options_offered.map(n_offered).to_numpy()
    onehot(np.clip(offered, 1, 3) - 1, ["1", "2", "3"], "offered")
    onehot(code(df.option, OPTIONS) * 3 + np.clip(offered, 1, 3) - 1, [f"{o}/{k}" for o in OPTIONS for k in "123"], "option_offered")
    f, t = code(df.pickup_place, PLACES), code(df.delivery_place, PLACES)
    onehot(f, PLACES, "from")
    onehot(t, PLACES, "to")
    onehot(np.where((f >= 0) & (t >= 0), f * len(PLACES) + t, -1), [f"{a}>{b}" for a in PLACES for b in PLACES], "lane")
    onehot(code(df.dealer_id, DEALERS), DEALERS, "dealer")
    hour = np.clip(df.minute_of_day.to_numpy() // 60, HOURS[0], HOURS[-1]) - HOURS[0]
    onehot(hour.astype(int), [str(h) for h in HOURS], "hour")
    lp = df.list_price_cents.to_numpy(dtype=float)
    onehot(np.searchsorted(LIST_EDGES, lp), [f"<{e}" for e in LIST_EDGES] + ["top"], "list")
    numeric(np.log(lp / 5000), "log_list")
    numeric(np.log(df.reference_fee_cents.to_numpy(dtype=float) / lp), "log_ref_over_list")
    on_time = np.nan_to_num(df.dealer_on_time.to_numpy(dtype=float))
    numeric(np.log1p(np.minimum(on_time, 25) / 100), "trust")
    onehot(np.searchsorted([1, 5, 10, 15, 25], on_time, side="right"), ["0", "1-4", "5-9", "10-14", "15-24", "25"], "trust_bucket")
    numeric(np.minimum(np.nan_to_num(df.dealer_late.to_numpy(dtype=float)), 8) / 8, "late")
    won = np.nan_to_num(df.dealer_won.to_numpy(dtype=float))
    lost = np.nan_to_num(df.dealer_lost.to_numpy(dtype=float))
    numeric((won - lost) / (won + lost + 10), "win_balance")
    numeric(won / (won + lost + 10), "win_share")
    numeric(np.log1p(won + lost) / 5, "dealer_seen")
    for name in ("private_pickup", "private_delivery", "premium", "electric", "has_note"):
        numeric(df[name].to_numpy(dtype=float), name)
    numeric((df.legs.to_numpy(dtype=float) > 1).astype(float), "trade_in")
    batch = np.nan_to_num(df.batch_size.to_numpy(dtype=float), nan=1.0)
    numeric(np.log(np.maximum(batch, 1)), "log_batch")
    numeric(np.nan_to_num(df.hours_to_deadline.to_numpy(dtype=float)) / 24, "days_to_deadline")
    onehot(np.clip(df.day.to_numpy(dtype=int), 0, 4), ["mon", "tue", "wed", "thu", "fri"], "weekday")
    m = sparse.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, len(names)))
    keep = [i for i, name in enumerate(names) if name.split(":")[0] in KEEP]
    return m[:, keep], [names[i] for i in keep]


def online(week, a, var, probes=None, scales=None, drift=0.0005):
    """Walks one week's decided quotes in time order, learning effects as src/strategies/lean/demand.ts does.
    `var` maps an effect kind (world, day, dealer, from, to) to its prior variance; kinds left out are not learned.
    `week` has arrived_at, day, dealer_id, pickup_place, delivery_place, option, mu (static), lr, y. Returns each
    quote's chance before its outcome, and for `probes` the mu with the learned effects at their arrival."""
    eff: dict[str, list[float]] = {}
    out_p = np.zeros(len(week))
    cols = {c: week[c].to_numpy() for c in ("arrived_at", "day", "dealer_id", "pickup_place", "delivery_place", "option", "mu", "lr", "y")}
    pc = {c: probes[c].to_numpy() for c in ("arrived_at", "day", "dealer_id", "pickup_place", "delivery_place", "mu")} if probes is not None else None
    probe_mu = np.zeros(len(probes)) if probes is not None else None
    order = np.argsort(pc["arrived_at"], kind="stable") if pc else []
    k = 0
    today = -1

    def keys(c, i):
        ks = [("world", "world"), ("day", f"day:{c['day'][i]}"), ("dealer", f"dealer:{c['dealer_id'][i]}"),
              ("from", f"from:{c['pickup_place'][i]}"), ("to", f"to:{c['delivery_place'][i]}")]
        return [eff.setdefault(key, [0.0, var[kind]]) for kind, key in ks if var.get(kind, 0) > 0]

    def flush(until):
        nonlocal k
        while k < len(order) and pc["arrived_at"][order[k]] <= until:
            j = order[k]
            probe_mu[j] = pc["mu"][j] + sum(e[0] for e in keys(pc, j))
            k += 1

    at = cols["arrived_at"]
    n = len(week)
    i = 0
    while i < n:
        j = i
        while j < n and at[j] == at[i]:
            j += 1
        if cols["day"][i] > today:  # a new morning: the effects the competitor moves get some doubt back
            today = cols["day"][i]
            for key, e in eff.items():
                kind = key.split(":")[0]
                if kind in ("dealer", "from", "to"):
                    e[1] = min(var[kind], e[1] + drift)
        flush(at[i])
        for q in range(i, j):
            es = keys(cols, q)
            v = sum(e[1] for e in es)
            s = (scales or {}).get(cols["option"][q], 1 / a)
            scale = s * np.sqrt(1 + np.pi * v / (8 * s * s))
            out_p[q] = 1 / (1 + np.exp(-(cols["mu"][q] + sum(e[0] for e in es) - cols["lr"][q]) / scale))
        for q in range(i, j):  # the outcomes of this minute, one by one
            es = keys(cols, q)
            v = sum(e[1] for e in es)
            s = (scales or {}).get(cols["option"][q], 1 / a)
            scale = s * np.sqrt(1 + np.pi * v / (8 * s * s))
            p = 1 / (1 + np.exp(-(cols["mu"][q] + sum(e[0] for e in es) - cols["lr"][q]) / scale))
            grad = (cols["y"][q] - p) / scale
            curve = p * (1 - p) / (scale * scale)
            gain = 1 / (1 + v * curve)
            step = abs(v * grad * gain)
            damp = 0.12 / step if step > 0.12 else 1
            for e in es:
                e[0] += e[1] * grad * gain * damp
                e[1] = max(1e-5, e[1] - e[1] * e[1] * curve * gain)
        i = j
    flush(np.inf)
    return out_p, probe_mu


def err(name: str, e: np.ndarray) -> dict:
    row = {"slice": name, "n": int(len(e)), "bias": float(e.mean()), "rmse": float(np.sqrt((e * e).mean())), "med_abs": float(np.median(np.abs(e)))}
    print(f"  {name:<22} n={row['n']:>5}  bias {row['bias']:+.3f}  rmse {row['rmse']:.3f}  med|e| {row['med_abs']:.3f}")
    return row


def main() -> None:
    global PLACES
    q = pd.read_csv("quotes.csv.gz", dtype={"options_offered": str})
    q = q[q.outcome != "won_other"].reset_index(drop=True)
    PLACES = sorted(set(q.pickup_place) | set(q.delivery_place))
    q["y"] = (q.outcome == "won").astype(float)
    q["lr"] = np.log(q.ratio)
    is_test = q.seed.map(lambda s: bool(TEST_SEED.match(s)))
    seeds = sorted(set(q.seed[~is_test]))
    rng = np.random.default_rng(7)
    val_seeds = set(rng.choice(seeds, size=len(seeds) // 10, replace=False))
    is_val = q.seed.isin(val_seeds)
    train = q[~is_test & ~is_val].reset_index(drop=True)
    val = q[is_val].reset_index(drop=True)
    print(f"train {len(train):,} rows, {train.seed.nunique()} seeds; validation {len(val):,} rows, {val.seed.nunique()} seeds")

    xs, names = static_features(train)
    sd_key = train.seed + "/" + train.day.astype(str)
    sd_codes, sd_labels = pd.factorize(sd_key)
    k = 2.0  # the scale of the seed-day columns: a weak ridge on those intercepts
    xsd = sparse.csr_matrix((np.full(len(train), k), (np.arange(len(train)), sd_codes)), shape=(len(train), len(sd_labels)))
    multi = sparse.csr_matrix((train.n_options_quoted.to_numpy() > 1).astype(float)[:, None])
    x = sparse.hstack([xs, sparse.csr_matrix(train.lr.to_numpy()[:, None]), multi, xsd]).tocsr()
    model = LogisticRegression(C=1.0, solver="lbfgs", max_iter=400)
    model.fit(x, train.y.to_numpy())
    w = model.coef_[0]
    ns = len(names)
    a = -w[ns]
    theta = w[:ns] / a
    base = model.intercept_[0] / a
    b = w[ns + 2 :] * k / a  # seed-day levels in log price
    print(f"slope a = {a:.2f} (logistic scale {1 / a:.3f} in log price), multi-option quote effect {w[ns + 1] / a:+.3f}")

    levels = pd.DataFrame({"key": sd_labels, "b": b})
    levels[["seed", "day"]] = levels.key.str.rsplit("/", n=1, expand=True)
    levels["day"] = levels.day.astype(int)
    centre = levels.b.mean()
    world = levels.groupby("seed").b.mean()
    within = levels.b - levels.seed.map(world)
    v_world, v_day = float(world.var()), float(within.var())
    print(f"level: mean {centre:+.3f}, sd between worlds {np.sqrt(v_world):.3f}, sd of a day within its world {np.sqrt(v_day):.3f}")
    print("  mean level by weekday:", levels.groupby("day").b.mean().round(3).to_dict())
    base += centre

    def mu_of(df: pd.DataFrame) -> np.ndarray:
        m, _ = static_features(df)
        return m @ theta + base

    top = sorted(zip(theta, names), key=lambda z: -abs(z[0]))
    print("largest effects (log price):", ", ".join(f"{n} {v:+.2f}" for v, n in top[:25]))
    for group in ("option:", "trust", "late", "win_", "to:vantaa", "to:helsinki", "to:hyvinkaa", "to:espoo", "private", "premium", "trade_in"):
        print("  ", ", ".join(f"{n} {v:+.3f}" for v, n in zip(theta, names) if n.startswith(group)))

    json.dump({"a": a, "base": base, "v_world": v_world, "v_day": v_day, "places": PLACES, "names": names, "theta": theta.tolist()},
              open("dealer_model.json", "w"))
    evaluate(val, mu_of, a, v_world, v_day)


def evaluate(val, mu_of, a, v_world, v_day):
    val = val.copy()
    val["mu"] = mu_of(val)
    worlds = sorted(val.world_id.unique())[::4]
    weeks = [w for _, w in val[val.world_id.isin(worlds)].sort_values("arrived_at", kind="stable").groupby("world_id", sort=False)]
    flips = pd.read_csv("quote_flips.csv", dtype={"options_offered": str})
    flips = flips[flips.flip_ratio.notna()].reset_index(drop=True)
    flips["mu"] = mu_of(flips)
    flips["target"] = np.log(flips.flip_ratio)
    desk = pd.read_csv("probe_week_quotes.csv.gz", dtype={"options_offered": str})
    desk = desk[desk.outcome != "won_other"].reset_index(drop=True)
    desk["y"] = (desk.outcome == "won").astype(float)
    desk["lr"] = np.log(desk.ratio)
    desk["mu"] = mu_of(desk)
    live = flips[flips.seed.isin(set(desk.seed))].reset_index(drop=True)
    for source, part in flips.groupby("source"):
        err(f"static mu, {source}", (part.mu - part.target).to_numpy())
    print(f"{len(weeks)} validation weeks, {len(live)} flips with a desk week")

    def score(var, scales=None, label=""):
        ll = []
        for week in weeks:
            p, _ = online(week, a, var, scales=scales)
            p = np.clip(p, 1e-6, 1 - 1e-6)
            y = week.y.to_numpy()
            ll.append(-(y * np.log(p) + (1 - y) * np.log(1 - p))[week.n_options_quoted.to_numpy() == 1])
        e = []
        for seed, week in desk.sort_values("arrived_at", kind="stable").groupby("seed"):
            part = live[live.seed == seed]
            _, pm = online(week, a, var, part, scales=scales)
            e.append(pm - part.target.to_numpy())
        e = np.concatenate(e)
        print(f"  {label:<46} log-loss {np.concatenate(ll).mean():.4f}   flips rmse {np.sqrt((e * e).mean()):.4f} med|e| {np.median(np.abs(e)):.4f} bias {e.mean():+.3f}")
        return e

    base_var = {"world": v_world, "day": v_day}
    score(base_var, label="world + day")
    for v in (0.001, 0.002, 0.004, 0.008):
        score({**base_var, "dealer": v}, label=f"+ dealer {v}")
        score({**base_var, "dealer": v, "to": v, "from": v}, label=f"+ dealer, to, from {v}")
    for mult in (0.8, 1.25, 1.5):
        score({"world": v_world * mult, "day": v_day * mult}, label=f"world + day, variances x {mult}")
    for sm in (0.8, 1.0, 1.2):
        for sn in (1.0, 1.2, 1.4):
            sc = {"same_day": sm / a, "next_day": sn / a, "within_3_days": sn / a}
            score(base_var, scales=sc, label=f"scale same_day x{sm}, others x{sn}")


if __name__ == "__main__":
    sys.exit(main())
