"""The driver cost model: the lowest flat fee, over the typical fee, that books a fresh gig within 3 hours.

    uv run --python 3.13 --with numpy --with pandas --with scikit-learn python fit_fee.py

Fitted on the fee probes (fee_flips.csv), the only exact measurements of what a gig costs its cheapest driver. A
linear model in log fee, so it reads as a table and ports to TypeScript as it is; scored by seed-grouped CV.
"""
import json
import numpy as np, pandas as pd
from sklearn.linear_model import Ridge, LogisticRegression

f = pd.read_csv("fee_flips.csv")
f = f[f.monotone != 0].reset_index(drop=True)
f["above"] = (f.ends == "above").astype(int)


def features(f: pd.DataFrame) -> pd.DataFrame:
    x = pd.DataFrame(index=f.index)
    at = f["at"]
    offset = (f.ready_at // 1440 - at // 1440).clip(lower=0)
    x["log_typical"] = np.log(f.reference_fee_cents / 5000)
    x["log_typical_sq"] = x.log_typical ** 2
    x["pickup_today"] = (offset == 0).astype(float)
    x["pickup_later"] = (offset >= 2).astype(float)
    hour = f.minute_of_day / 60
    x["hour"] = (hour - 13) / 5
    x["today_late_hour"] = x.pickup_today * np.clip(hour - 12, 0, 6) / 6
    x["hours_to_last_pickup"] = np.log(np.clip((f.last_pickup_at - at) / 60, 1, 96) / 24)
    x["friday"] = (f.day == 4).astype(float)
    x["monday"] = (f.day == 0).astype(float)
    x["private_pickup"] = f.private_pickup.astype(float)
    x["private_delivery"] = f.private_delivery.astype(float)
    x["premium"] = f.premium.astype(float)
    x["electric"] = f.electric.astype(float)
    x["trade_in"] = (f.legs > 1).astype(float)
    x["long_drive"] = np.clip(f.drive_minutes / 60 - 3, 0, 6) / 6
    x["home_pickup"] = np.log1p(f.drivers_home_pickup) / 5
    x["home_delivery"] = np.log1p(f.drivers_home_delivery) / 5
    x["drivers"] = np.log(f.n_drivers / 777)
    x["load_booked"] = np.nan_to_num(f.load_booked) / 300
    x["load_open"] = np.nan_to_num(f.load_open) / 40
    return x


x = features(f)
inside = f.flip_ratio.notna().to_numpy()
y = np.log(f.flip_ratio.clip(0.3, 2.5)).to_numpy()
seeds = f.seed.to_numpy(); us = sorted(set(seeds))
pred = np.zeros(len(f)); pa = np.zeros(len(f))
for k in range(5):
    te = np.isin(seeds, us[k::5]); tr = ~te
    pred[te] = Ridge(alpha=1.0).fit(x[tr & inside], y[tr & inside]).predict(x[te])
    pa[te] = LogisticRegression(C=1.0, max_iter=2000).fit(x[tr], f.above[tr]).predict_proba(x[te])[:, 1]
r = y[inside] - pred[inside]
a = f.above.to_numpy(); base = a.mean()
print(f"{len(f)} probes of {len(us)} seeds, {inside.sum()} with a flip; never booked {base:.3f}")
print(f"CV by seed: R2 {1 - (r ** 2).mean() / np.var(y[inside]):.3f}, residual sd {r.std():.3f} (raw {y[inside].std():.3f})")
print(f"never booked: log-loss {-(a * np.log(pa) + (1 - a) * np.log(1 - pa)).mean():.3f} (base {-(base * np.log(base) + (1 - base) * np.log(1 - base)):.3f})")
q = pd.qcut(pred[inside], 5)
print("predicted fifth -> measured median fee / typical, share under 0.88, never booked:")
print(pd.DataFrame({"pred": np.exp(pred[inside]), "flip": f.flip_ratio[inside].to_numpy(), "q": q}).groupby("q", observed=True).agg(pred=("pred", "median"), flip=("flip", "median"), under88=("flip", lambda v: (v < 0.88).mean()), n=("flip", "size")).round(2).to_string())
print(pd.DataFrame({"q": pd.qcut(pa, 5), "above": a}).groupby("q", observed=True).above.agg(["mean", "size"]).round(3).to_string())
m = Ridge(alpha=1.0).fit(x[inside], y[inside]); c = LogisticRegression(C=1.0, max_iter=2000).fit(x, f.above)
print("fee  :", f"base {m.intercept_:+.3f}", ", ".join(f"{n} {v:+.3f}" for n, v in zip(x.columns, m.coef_)))
print("never:", f"base {c.intercept_[0]:+.3f}", ", ".join(f"{n} {v:+.2f}" for n, v in zip(x.columns, c.coef_[0])))
json.dump({"sd": float(r.std()), "fee": {"base": float(m.intercept_), **dict(zip(x.columns, map(float, m.coef_)))},
           "never": {"base": float(c.intercept_[0]), **dict(zip(x.columns, map(float, c.coef_[0])))}}, open("fee_model.json", "w"), indent=1)
