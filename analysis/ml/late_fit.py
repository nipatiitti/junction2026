"""Can an order's lateness and margin be told from what the desk sees when it quotes? Real server orders (orders.csv.gz)."""
import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.metrics import roc_auc_score
o = pd.read_csv("orders.csv.gz")
wk = o.groupby("world_id").agg(n=("on_time", "size"), ot=("on_time", "mean"))
good = wk[(wk.ot >= 0.93) & (wk.n.between(250, 520))].index          # weeks that look like a ranked, tuned desk
o = o[o.world_id.isin(good)].reset_index(drop=True)
cost = o[["fee_paid_cents", "release_fee_cents", "failed_visit_cents", "fine_cents", "waiting_cents", "late_refund_cents", "undelivered_penalty_cents"]].sum(axis=1)
o["margin"] = (o.revenue_cents - cost) / 100
o["cost_ratio"] = cost / o.reference_fee_cents
o["late"] = 1 - o.on_time
o["hour"] = o.minute_of_day / 60
o["log_ref"] = np.log(o.reference_fee_cents)
o["mult"] = o.price_cents / o.list_price_cents
cols = ["day", "hour", "drive_minutes", "legs", "private_pickup", "private_delivery", "premium", "electric", "has_note", "log_ref",
        "hours_ready_to_deadline", "pickup_day_offset", "hours_won_to_last_pickup", "n_drivers", "drivers_home_pickup", "drivers_home_delivery",
        "drivers_home_60km_pickup", "orders_won_so_far", "orders_won_today", "open_gigs_at_win", "booked_gigs_at_win", "active_today", "active_today_near_pickup"]
print(len(o), "orders of", o.world_id.nunique(), "weeks; late", o.late.mean().round(4), "; mean margin", o.margin.mean().round(1), "; cost/typical", o.cost_ratio.mean().round(3))
seeds = o.seed.to_numpy(); us = sorted(set(seeds)); pl = np.zeros(len(o)); pc = np.zeros(len(o))
for k in range(4):
    te = np.isin(seeds, us[k::4]); tr = ~te
    kw = dict(n_estimators=250, learning_rate=0.05, num_leaves=24, min_child_samples=200, subsample=0.5, subsample_freq=1, colsample_bytree=0.8, verbose=-1, n_jobs=4)
    pl[te] = lgb.LGBMClassifier(**kw).fit(o.loc[tr, cols], o.late[tr]).predict_proba(o.loc[te, cols])[:, 1]
    pc[te] = lgb.LGBMRegressor(**kw).fit(o.loc[tr, cols], o.cost_ratio[tr].clip(0, 4)).predict(o.loc[te, cols])
print("late: AUC %.3f" % roc_auc_score(o.late, pl), "| cost/typical: CV R2 %.3f" % (1 - ((o.cost_ratio.clip(0, 4) - pc) ** 2).mean() / o.cost_ratio.clip(0, 4).var()))
d = o.assign(q=pd.qcut(pl, 10, labels=False)).groupby("q").agg(n=("late", "size"), pred=("late", "mean"), margin=("margin", "mean"), cost=("cost_ratio", "mean"), mult=("mult", "mean"), drive=("drive_minutes", "median"), today=("pickup_day_offset", lambda v: (v == 0).mean()))
print("by tenth of predicted late risk:\n", d.round(3).to_string())
d = o.assign(q=pd.qcut(pc, 10, labels=False)).groupby("q").agg(n=("late", "size"), pred_cost=("cost_ratio", "mean"), margin=("margin", "mean"), late=("late", "mean"), mult=("mult", "mean"))
print("by tenth of predicted cost/typical:\n", d.round(3).to_string())
print("share of late orders in the riskiest tenth: %.2f, riskiest fifth: %.2f" % (o.late[pl >= np.quantile(pl, 0.9)].sum() / o.late.sum(), o.late[pl >= np.quantile(pl, 0.8)].sum() / o.late.sum()))
print("orders with negative margin: %.3f; their total: %.0f EUR a week" % ((o.margin < 0).mean(), o.margin[o.margin < 0].sum() / o.world_id.nunique()))
