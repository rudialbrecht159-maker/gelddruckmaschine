import json, numpy as np, pandas as pd
import framework as fw
from strats5 import EXISTING, NEW, MAX_HOLD, on1h, s1_trend4h, s5_funding_fade4h
data = {tf: fw.load(tf) for tf in ("5m", "1h", "4h")}
out = {}; dr = {}
def ts(x): return pd.to_datetime(x, unit="ms").strftime("%Y-%m-%d")
for name, (tf, fn) in {**EXISTING, **NEW}.items():
    d = data[tf]; n = len(d["BTC"]); half = n // 2; warm = {"5m": 400, "1h": 300, "4h": 250}[tf]
    sig = {c: fn(d[c], c) for c in d}; mh = {name: MAX_HOLD[name]} if name in MAX_HOLD else None
    res = {"tf": tf, "oos": f"{ts(d['BTC'].t[half])}→{ts(d['BTC'].t[n-1])}"}
    if tf == "5m": half = warm; res["oos"] = f"{ts(d['BTC'].t[warm])}→{ts(d['BTC'].t[n-1])} (gesamt, zu kurz für IS/OOS)"
    else: res["is"] = fw.metrics(fw.run(d, [(name, sig)], warm, half, max_hold=mh))
    r = fw.run(d, [(name, sig)], half, n, max_hold=mh); res["oos_taker"] = fw.metrics(r)
    res["oos_maker"] = fw.metrics(fw.run(d, [(name, sig)], half, n, fee_mode="maker", max_hold=mh))
    res["oos_nohalt"] = fw.metrics(fw.run(d, [(name, sig)], half, n, dd_halt=False, max_hold=mh))
    res["oos_2xcost"] = fw.metrics(fw.run(d, [(name, sig)], half, n, cost_mult=2.0, max_hold=mh))["net_pct"]
    b = [half + (n - half) * j // 4 for j in range(5)]
    res["folds"] = [fw.metrics(fw.run(d, [(name, sig)], b[j], b[j+1], max_hold=mh))["net_pct"] for j in range(4)]
    o = res["oos_taker"]; folds_ok = sum(f >= 0 for f in res["folds"])
    if o["net_pct"] <= 0 or o["gross_eur"] <= 0: v = "DISCARD"
    elif o["pf"] and o["pf"] >= 1.2 and o["trades"] >= 30 and folds_ok >= 3 and not o["halted"]: v = "KEEP"
    else: v = "REWORK/OBSERVE"
    res["verdict"] = v; res["folds_ok"] = folds_ok; out[name] = res
    print(name, tf, v, json.dumps({k: o[k] for k in ("net_pct", "gross_eur", "fees_eur", "maxdd_pct", "trades", "win_pct", "pf", "sharpe", "dsr", "p_le0", "halted")}), "maker", res["oos_maker"]["net_pct"], res["oos_maker"]["missed_maker"], "nohalt", res["oos_nohalt"]["net_pct"], res["oos_nohalt"]["trades"], "folds", res["folds"], flush=True)
json.dump(out, open("results_strategies.json", "w"), indent=1, default=str)
