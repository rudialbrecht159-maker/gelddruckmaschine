import json, numpy as np, pandas as pd
import framework as fw
from strats5 import s1_trend4h, s5_funding_fade4h
d = fw.load("4h"); n = len(d["BTC"]); half = n // 2; warm = 250
S = {"S1": {c: s1_trend4h(d[c], c) for c in d}, "S5": {c: s5_funding_fade4h(d[c], c) for c in d}}
out = {}
r1, r5 = (fw.run(d, [(k, S[k])], half, n) for k in ("S1", "S5"))
a, b = fw.daily_returns(r1), fw.daily_returns(r5); j = pd.concat([a, b], axis=1).dropna()
out["corr_daily_oos"] = round(float(j.corr().iloc[0, 1]), 3)
nz = j[(j != 0).any(axis=1)]; out["corr_daily_oos_active_days"] = round(float(nz.corr().iloc[0, 1]), 3)
combo = [("S5", S["S5"]), ("S1", S["S1"])]
for lab, i0, i1 in (("is", warm, half), ("oos", half, n)):
    out[lab] = fw.metrics(fw.run(d, combo, i0, i1)); out[lab + "_maker"] = fw.metrics(fw.run(d, combo, i0, i1, fee_mode="maker"))["net_pct"]
bnd = [half + (n - half) * k // 4 for k in range(5)]
out["folds"] = [fw.metrics(fw.run(d, combo, bnd[k], bnd[k+1]))["net_pct"] for k in range(4)]
r = fw.run(d, combo, half, n); out["by_strategy"] = {s: round(sum(t["net"] for t in r["trades"] if t["strategy"] == s), 2) for s in ("S1", "S5")}
out["n_by_strategy"] = {s: sum(t["strategy"] == s for t in r["trades"]) for s in ("S1", "S5")}
json.dump({"trades": r["trades"], "curve": r["curve"].tolist(), "t": r["t"].tolist()}, open("portfolio_oos_trades.json", "w"))
json.dump(out, open("results_portfolio.json", "w"), indent=1, default=str); print(json.dumps(out, default=str))
