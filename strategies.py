"""Deterministic signal generators. All signals use ONLY data up to and including the closed bar i;
execution happens at the open of bar i+1 (no look-ahead)."""
import numpy as np, pandas as pd

def atr(df, n=14):
    pc = df.c.shift(1)
    tr = pd.concat([df.h - df.l, (df.h - pc).abs(), (df.l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def rsi(s, n=14):
    d = s.diff(); up = d.clip(lower=0).ewm(alpha=1/n).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1/n).mean()
    return 100 - 100 / (1 + up / dn)

def _out(df, le, se, lx, sx, stop_atr, tp_atr=None):
    o = pd.DataFrame(index=df.index)
    o["le"], o["se"], o["lx"], o["sx"] = le.fillna(False), se.fillna(False), lx.fillna(False), sx.fillna(False)
    o["atr"] = atr(df); o["stop_atr"] = stop_atr; o["tp_atr"] = tp_atr if tp_atr else np.nan
    return o

def trend(df, fast=20, slow=100, stop_atr=3.0):
    f, s = df.c.ewm(span=fast).mean(), df.c.ewm(span=slow).mean()
    up = f > s
    return _out(df, up & ~up.shift(1, fill_value=False), ~up & up.shift(1, fill_value=True), ~up, up, stop_atr)

def momentum(df, look=48, thr=0.03, stop_atr=2.5):
    r = df.c / df.c.shift(look) - 1
    return _out(df, r > thr, r < -thr, r < 0, r > 0, stop_atr)

def breakout(df, n=48, exit_n=24, stop_atr=2.0):
    hh, ll = df.h.rolling(n).max().shift(1), df.l.rolling(n).min().shift(1)
    xl, xh = df.l.rolling(exit_n).min().shift(1), df.h.rolling(exit_n).max().shift(1)
    return _out(df, df.c > hh, df.c < ll, df.c < xl, df.c > xh, stop_atr)

def meanrev(df, n=14, lo=25, hi=75, stop_atr=2.5, tp_atr=2.0):
    r = rsi(df.c, n)
    return _out(df, r < lo, r > hi, r > 50, r < 50, stop_atr, tp_atr)

def funding(df, q=0.95, win=24*30, stop_atr=2.5, hold_exit=0.5):
    """Contrarian: when smoothed funding is extreme (crowded longs) -> short, and vice versa."""
    fr = df["fund"].rolling(8).mean()
    hi, lo = fr.rolling(win).quantile(q).shift(1), fr.rolling(win).quantile(1-q).shift(1)
    med = fr.rolling(win).median().shift(1)
    return _out(df, fr < lo, fr > hi, fr > med, fr < med, stop_atr)

STRATS = {"trend": trend, "momentum": momentum, "breakout": breakout, "meanrev": meanrev, "funding": funding}
GRIDS = {
    "trend": [dict(fast=f, slow=s, stop_atr=a) for f in (10, 20, 50) for s in (100, 200) for a in (2.0, 3.0)],
    "momentum": [dict(look=l, thr=t, stop_atr=a) for l in (24, 48, 96) for t in (0.02, 0.05) for a in (2.0, 3.0)],
    "breakout": [dict(n=n, exit_n=n//2, stop_atr=a) for n in (24, 48, 96, 168) for a in (1.5, 2.5)],
    "meanrev": [dict(n=n, lo=l, hi=100-l, stop_atr=a, tp_atr=t) for n in (7, 14) for l in (20, 25, 30) for a in (2.0, 3.0) for t in (1.5, 3.0)],
    "funding": [dict(q=q, win=w, stop_atr=a) for q in (0.9, 0.95, 0.98) for w in (24*14, 24*30) for a in (2.0, 3.0)],
}
