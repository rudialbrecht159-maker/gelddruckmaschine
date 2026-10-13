"""research4 EXPERIMENTAL candidate: R3 funding-extreme fade with 4h trend filter (SIMULATED / paper only).
Confidence: LOW-MODERATE. Positive on core IS and OOS and in all BTC phases, but FAILED the hold-out markets (see report.md).

Plug-in for cycle.py adapter path (strategy dict: name="funding_fade_trend", tf="4h", adapter=true, history_bars>=800, params={}):
    funding_fade_trend(df, coin=None, position_side=0, **params) -> DataFrame (index = df.index; engine uses .iloc[-1])
      df: CLOSED 4h candles, columns t,o,h,l,c(,v), oldest first, >= 760 rows (540-bar funding window + 18 + 200 EMA).
          Optional column "fund4" = last hourly funding rate known at bar close; if absent, fetched read-only from the
          public Hyperliquid fundingHistory API (needs `coin`).
      columns: le, se, lx, sx (bool), atr, stop_atr (=3.0), tp_atr (NaN), reason (str)
    Exit: trend flip or 42 bars (7 days) after the latest entry signal; stop 3 ATR (engine). No look-ahead: features use bars <= i.
"""
import os, sys, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
from rules import funding_fade
PARAMS = dict(win=540, q=0.9, hold=42, stop_atr=3.0, k=5.0); MIN_BARS = 760

def _attach_funding(df, coin):
    import hl
    f = hl.funding_history(coin, int(df.t.iloc[0]) - 3600_000)
    fs = pd.Series({(int(k)//3600_000)*3600_000: v for k, v in f.items()}).groupby(level=0).last().sort_index()
    return df.assign(fund4=fs.reindex(df.t + 3*3600_000, method="ffill").values)

def funding_fade_trend(df, coin=None, position_side=0, **params):
    df = df.reset_index(drop=True)
    p = {**PARAMS, **{k: v for k, v in params.items() if k in PARAMS}}
    if len(df) < MIN_BARS:
        o = pd.DataFrame([dict(le=False, se=False, lx=False, sx=False, atr=np.nan, stop_atr=p["stop_atr"], tp_atr=np.nan, reason=f"need {MIN_BARS} bars, got {len(df)}")]); return o
    if "fund4" not in df: df = _attach_funding(df, coin)
    o = funding_fade(df, coin=coin, **p)
    fr = df.fund4.rolling(18).mean().iloc[-1]; hi = df.fund4.rolling(18).mean().rolling(p["win"]).quantile(p["q"]).shift(1).iloc[-1]
    lo = df.fund4.rolling(18).mean().rolling(p["win"]).quantile(1 - p["q"]).shift(1).iloc[-1]
    o["reason"] = ""; o.loc[o.index[-1], "reason"] = f"3d funding {fr:.2e} (p10 {lo:.2e} / p90 {hi:.2e}), trend {'up' if df.c.ewm(span=50).mean().iloc[-1] > df.c.ewm(span=200).mean().iloc[-1] else 'down'}"
    return o
