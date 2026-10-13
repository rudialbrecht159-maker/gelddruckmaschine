"""Adapter: research3/hf_candidate.signal(...) -> engine signal frame (le/se/lx/sx/atr/stop_atr/reason). Read-only use of research3."""
import os, sys, pandas as pd, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "research3"))
import hf_candidate
def zscore5m(df, coin=None, position_side=0, **_):
    r = hf_candidate.signal(df[["t", "o", "h", "l", "c", "v"]], coin, position_side)
    a = r["action"]; row = dict(le=a == "open_long", se=a == "open_short", lx=a == "close", sx=a == "close", tp_atr=np.nan, reason=f"{a}: {r['reason']} (z={r['z']})")
    if r["stop"] is not None:   # engine stop = entry -/+ stop_atr*atr; encode candidate's absolute stop distance
        row.update(atr=abs(float(df.c.iloc[-1]) - r["stop"]) / 1.0, stop_atr=1.0)
    else: row.update(atr=r["atr"] if r["atr"] is not None else np.nan, stop_atr=1.0)
    return pd.DataFrame([row], index=[df.index[-1]])
