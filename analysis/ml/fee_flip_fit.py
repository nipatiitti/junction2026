"""What explains the lowest flat fee that books a fresh gig within 3 hours (the fee probes)? Grouped CV by seed."""
import numpy as np, pandas as pd, lightgbm as lgb
f = pd.read_csv("fee_flips.csv")
f = f[f.monotone != 0].reset_index(drop=True)
f["above"] = (f.ends == "above").astype(int)
f["y"] = np.log(f.flip_ratio.fillna(f.bracket_low_ratio).clip(0.3, 2.5))
f["offset"] = (f.ready_at // 1440 - f["at"] // 1440).clip(0, 3)
f["h_to_last"] = (f.last_pickup_at - f["at"]) / 60
f["h_to_deadline"] = (f.deadline - f["at"]) / 60
f["hour"] = f.minute_of_day / 60
f["log_ref"] = np.log(f.reference_fee_cents)
f["home_pick_share"] = f.drivers_home_pickup / f.n_drivers
f["home_del_share"] = f.drivers_home_delivery / f.n_drivers
for c in ("pickup_place", "delivery_place", "option"):
    f[c + "_c"] = f[c].astype("category").cat.codes
print(len(f), "probes;", f.above.mean().round(3), "never booked up to the top fee")
print("median flip by pickup day offset:\n", f[f.above == 0].groupby("offset").flip_ratio.agg(["size", "median"]).round(2).to_string(),
      "\nnever-booked share by offset:", f.groupby("offset").above.mean().round(2).to_dict())
sets = {
    "static (lane, time, order)": ["offset", "h_to_last", "h_to_deadline", "hour", "day", "log_ref", "drive_minutes", "km", "private_pickup", "private_delivery", "premium", "electric", "legs", "pickup_place_c", "delivery_place_c", "option_c"],
}
sets["+ roster by town"] = sets["static (lane, time, order)"] + ["n_drivers", "drivers_home_pickup", "drivers_home_delivery", "home_pick_share", "home_del_share"]
sets["+ load"] = sets["+ roster by town"] + ["load_open", "load_booked", "load_orders"]
seeds = f.seed.to_numpy(); us = sorted(set(seeds))
inside = (f.flip_ratio.notna()).to_numpy()
for name, cols in sets.items():
    pred = np.zeros(len(f)); pa = np.zeros(len(f))
    for k in range(5):
        te = np.isin(seeds, us[k::5]); tr = ~te
        m = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=8, min_child_samples=30, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
        m.fit(f.loc[tr & inside, cols], f.y[tr & inside]); pred[te] = m.predict(f.loc[te, cols])
        c = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.03, num_leaves=8, min_child_samples=30, verbose=-1)
        c.fit(f.loc[tr, cols], f.above[tr]); pa[te] = c.predict_proba(f.loc[te, cols])[:, 1]
    y = f.y.to_numpy()[inside]; p = pred[inside]
    r2 = 1 - ((y - p) ** 2).mean() / ((y - y.mean()) ** 2).mean()
    a = f.above.to_numpy(); base = a.mean()
    ll = -(a * np.log(pa.clip(1e-4, 1)) + (1 - a) * np.log((1 - pa).clip(1e-4, 1))).mean()
    ll0 = -(base * np.log(base) + (1 - base) * np.log(1 - base))
    print(f"{name:<28} min fee: CV R2 {r2:.3f}, resid sd {np.std(y - p):.3f} (raw sd {np.std(y):.3f}) | never-booked log-loss {ll:.3f} (base {ll0:.3f})")
imp = sorted(zip(m.feature_importances_, cols), reverse=True)[:12]; print("top features:", ", ".join(f"{n} {v}" for v, n in imp))
