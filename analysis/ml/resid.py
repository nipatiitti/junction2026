import json, numpy as np, pandas as pd, lightgbm as lgb
import fit_dealer as fd
m = json.load(open("dealer_model.json")); fd.PLACES = m["places"]; theta = np.array(m["theta"])
f = pd.read_csv("quote_flips.csv", dtype={"options_offered": str}); f = f[f.flip_ratio.notna()].reset_index(drop=True)
X, names = fd.static_features(f); f["mu"] = X @ theta + m["base"]; f["e"] = np.log(f.flip_ratio) - f.mu
f["lvl"] = f.groupby(["seed", "day"]).e.transform("mean"); f["r"] = f.e - f.lvl
sd = lambda x: (np.sqrt((x**2).mean()), 1.4826*np.median(np.abs(x - np.median(x))))
for src, p in f.groupby("source"):
    print(src, len(p), "resid rmse/robust sd %.3f %.3f" % sd(p.r.to_numpy()), "| seed-day level sd %.3f" % p.groupby(["seed","day"]).lvl.first().std())
p2 = f[f.source == "probe2"].copy()
print("by seed:", {s: tuple(round(v,3) for v in sd(g.r.to_numpy())) for s, g in p2.groupby("seed")})
for col, bins in (("dealer_late", [-1,0,1,2,4,8,99]), ("dealer_on_time", [-1,0,4,9,25]), ("dealer_lost", [-1,5,20,50,999]), ("dealer_won", [-1,5,20,50,999])):
    g = p2.groupby(pd.cut(p2[col], bins)).r.agg(["size","mean", lambda x: np.sqrt((x**2).mean())]); print(col); print(g.round(3).to_string())
for col in ("option", "day"):
    print(p2.groupby(col).r.agg(["size","mean","std"]).round(3).to_string())
# the three dealer groups of the probing desk (x0.85, x1, x1.2): does the limit react to the group?
# same request, several options: is the noise shared within a request?
w = p2.pivot_table(index=["seed","request_id"], columns="option", values="r")
print("corr of residuals across options of one request:\n", w.corr().round(2).to_string(), "\n n pairs", w.dropna(thresh=2).shape[0])
# can any feature explain the residual? grouped CV by seed
feat = pd.DataFrame(X.toarray(), columns=[f"f{i}" for i in range(len(names))])
keep = [f"f{i}" for i, n in enumerate(names) if not n.startswith("lane:")]
for tag, part in (("probe2", f.source == "probe2"), ("all", f.source != "x")):
    idx = np.where(part)[0]; seeds = f.seed.to_numpy()[idx]; us = sorted(set(seeds)); pred = np.zeros(len(idx))
    for k in range(4):
        te = np.isin(seeds, us[k::4]); tr = ~te
        mdl = lgb.LGBMRegressor(n_estimators=200, learning_rate=0.03, num_leaves=8, min_child_samples=40, verbose=-1)
        mdl.fit(feat.iloc[idx[tr]][keep], f.r.to_numpy()[idx[tr]]); pred[te] = mdl.predict(feat.iloc[idx[te]][keep])
    r = f.r.to_numpy()[idx]; print(tag, "GBDT on residual, CV R2 by seed: %.3f" % (1 - ((r - pred)**2).mean() / (r**2).mean()))
