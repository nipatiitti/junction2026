"""The order model: what a won order costs to serve, over its typical fee, and the chance that it arrives late,
from what the desk sees when it quotes. Fitted on the real orders of the saved weeks (orders.csv.gz).

    uv run --python 3.13 --with numpy --with pandas --with scikit-learn python fit_order.py

Linear, so it reads as a table and ports to TypeScript as it is; scored by seed-grouped CV.
"""
import json
import numpy as np, pandas as pd
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.metrics import roc_auc_score

o = pd.read_csv("orders.csv.gz")
wk = o.groupby("world_id").agg(n=("on_time", "size"), ot=("on_time", "mean"))
o = o[o.world_id.isin(wk[(wk.ot >= 0.93) & (wk.n.between(250, 520))].index)].reset_index(drop=True)  # ranked, tuned desks
cost = o[["fee_paid_cents", "release_fee_cents", "failed_visit_cents", "fine_cents", "waiting_cents"]].sum(axis=1)
o["cost_ratio"] = (cost / o.reference_fee_cents).clip(0, 4)
o["late"] = 1 - o.on_time


def features(o: pd.DataFrame) -> pd.DataFrame:
    x = pd.DataFrame(index=o.index)
    hour = o.minute_of_day / 60
    drive = o.drive_minutes / 60
    x["log_typical"] = np.log(o.reference_fee_cents / 5000)
    x["log_typical_sq"] = x.log_typical ** 2
    x["pickup_today"] = (o.pickup_day_offset <= 0).astype(float)
    x["pickup_later"] = (o.pickup_day_offset >= 2).astype(float)
    x["hour"] = (hour - 13) / 5
    x["today_late_hour"] = x.pickup_today * np.clip(hour - 12, 0, 6) / 6
    x["long_drive"] = np.clip(drive - 3, 0, 6) / 6
    x["very_long_drive"] = np.clip(drive - 5, 0, 4) / 4
    x["short_drive"] = (drive < 0.75).astype(float)
    x["today_long_drive"] = x.pickup_today * x.long_drive
    x["time_to_last_pickup"] = np.log(np.clip(o.hours_won_to_last_pickup, 1, 96) / 24)
    x["tight"] = (o.hours_won_to_last_pickup < 8).astype(float)
    x["room"] = np.log(np.clip(o.hours_ready_to_deadline, 2, 120) / 24)
    for name, d in (("monday", 0), ("thursday", 3), ("friday", 4)):
        x[name] = (o.day == d).astype(float)
    x["private_pickup"] = o.private_pickup.astype(float)
    x["private_delivery"] = o.private_delivery.astype(float)
    x["premium"] = o.premium.astype(float)
    x["electric"] = o.electric.astype(float)
    x["trade_in"] = (o.legs > 1).astype(float)
    x["has_note"] = o.has_note.astype(float)
    x["home_pickup"] = np.log1p(o.drivers_home_pickup) / 5
    x["home_delivery"] = np.log1p(o.drivers_home_delivery) / 5
    x["drivers"] = np.log(o.n_drivers / 777)
    x["won_so_far"] = o.orders_won_so_far / 300
    x["won_today"] = o.orders_won_today / 80
    x["open_gigs"] = np.clip(o.open_gigs_at_win, 0, 120) / 40
    return x


x = features(o)
seeds = o.seed.to_numpy(); us = sorted(set(seeds)); pl = np.zeros(len(o)); pc = np.zeros(len(o))
for k in range(4):
    te = np.isin(seeds, us[k::4]); tr = ~te
    pl[te] = LogisticRegression(C=1.0, max_iter=3000).fit(x[tr], o.late[tr]).predict_proba(x[te])[:, 1]
    pc[te] = Ridge(alpha=1.0).fit(x[tr], o.cost_ratio[tr]).predict(x[te])
print(f"{len(o):,} orders of {o.world_id.nunique()} weeks; late {o.late.mean():.4f}; cost/typical {o.cost_ratio.mean():.3f}")
print(f"CV by seed: late AUC {roc_auc_score(o.late, pl):.3f}; cost/typical R2 {1 - ((o.cost_ratio - pc) ** 2).mean() / o.cost_ratio.var():.3f}")
d = o.assign(q=pd.qcut(pl, 10, labels=False), p=pl).groupby("q").agg(pred=("p", "mean"), late=("late", "mean"), cost=("cost_ratio", "mean"))
print("tenths of predicted late risk:\n", d.round(3).T.to_string())
d = o.assign(q=pd.qcut(pc, 10, labels=False), p=pc).groupby("q").agg(pred=("p", "mean"), cost=("cost_ratio", "mean"), late=("late", "mean"))
print("tenths of predicted cost/typical:\n", d.round(3).T.to_string())
print("late orders in the riskiest tenth: %.2f" % (o.late[pl >= np.quantile(pl, 0.9)].sum() / o.late.sum()))
late = LogisticRegression(C=1.0, max_iter=3000).fit(x, o.late); c = Ridge(alpha=1.0).fit(x, o.cost_ratio)
print("late:", f"base {late.intercept_[0]:+.2f}", ", ".join(f"{n} {v:+.2f}" for n, v in zip(x.columns, late.coef_[0])))
print("cost:", f"base {c.intercept_:+.3f}", ", ".join(f"{n} {v:+.3f}" for n, v in zip(x.columns, c.coef_)))
r = lambda d: {k: round(float(v), 4) for k, v in d.items()}
json.dump({"about": "What a won order costs to serve, over its typical fee, and the chance that it arrives late, from what the desk sees when it quotes. Fitted by analysis/ml/fit_order.py on the real orders of the saved weeks.",
           "meanCost": round(float(o.cost_ratio.mean()), 4), "meanLate": round(float(o.late.mean()), 4),
           "cost": r({"base": c.intercept_, **dict(zip(x.columns, c.coef_))}), "late": r({"base": late.intercept_[0], **dict(zip(x.columns, late.coef_[0]))})},
          open("order_model.json", "w"), indent=1)
