"""research2 candidate strategies. Same interface as ../strategies.py: fn(df_1h, **params) -> DataFrame
with le/se/lx/sx/atr/stop_atr/tp_atr. df_1h needs columns t,o,h,l,c,v (t = bar open, ms UTC).
All features use only bars closed at or before bar i (signal at close of i, execute at open of i+1).
4h features are built from COMPLETE 4h blocks of 1h bars and become visible only on the 1h bar that closes the block."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from strategies import atr, rsi, _out, breakout  # read-only reuse
H4 = 4 * 3600_000

def _h4(df):
    """Return 4h OHLC frame (complete blocks only) + index of the 1h row on which each block closes."""
    b = df.t // H4
    g = df.groupby(b)
    agg = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(), "n": g.size(), "last_i": g.apply(lambda x: x.index[-1])})
    return agg[agg.n == 4].reset_index(drop=True)

def _map(df, h4, series):
    s = pd.Series(np.nan, index=df.index, dtype=float)
    s.loc[h4.last_i.values] = series.values
    return s.ffill()

def trend4h_dir(df, fast=50, slow=200):
    h4 = _h4(df)
    d = np.sign(h4.c.ewm(span=fast).mean() - h4.c.ewm(span=slow).mean())
    d[h4.index < slow] = 0  # warm-up
    return _map(df, h4, d).fillna(0)

def trend4h_on1h(df, fast=10, slow=200, stop_atr=3.0):
    """trend-4h-v1 replicated on the 1h timeline (signals only at 4h closes, ATR from 4h bars)."""
    h4 = _h4(df)
    up = (h4.c.ewm(span=fast).mean() > h4.c.ewm(span=slow).mean())
    a4 = atr(h4[["o", "h", "l", "c"]].assign(c=h4.c))
    nan = pd.Series(np.nan, index=df.index)
    def ev(x):
        s = nan.copy(); s.loc[h4.last_i.values] = x.astype(float).values; return s.fillna(0).astype(bool)
    o = pd.DataFrame(index=df.index)
    o["le"] = ev(up & ~up.shift(1, fill_value=False)); o["se"] = ev(~up & up.shift(1, fill_value=True))
    o["lx"] = ev(~up); o["sx"] = ev(up)
    o["atr"] = _map(df, h4, a4); o["stop_atr"] = stop_atr; o["tp_atr"] = np.nan
    o.loc[_map(df, h4, pd.Series(h4.index, dtype=float)).fillna(0) < slow, ["le", "se"]] = False
    return o

def breakout1h_filtered(df, n=48, exit_n=24, stop_atr=2.0, vol_mult=1.5):
    d4 = trend4h_dir(df)
    hh, ll = df.h.rolling(n).max().shift(1), df.l.rolling(n).min().shift(1)
    xl, xh = df.l.rolling(exit_n).min().shift(1), df.h.rolling(exit_n).max().shift(1)
    vok = df.v > vol_mult * df.v.rolling(48).mean().shift(1)
    return _out(df, (df.c > hh) & vok & (d4 > 0), (df.c < ll) & vok & (d4 < 0), df.c < xl, df.c > xh, stop_atr)

def pullback_mtf(df, lo=40, hi=60, stop_atr=2.0, tp_atr=3.0):
    d4 = trend4h_dir(df); r = rsi(df.c, 14)
    le = (d4 > 0) & (r > lo) & (r.shift(1) <= lo)
    se = (d4 < 0) & (r < hi) & (r.shift(1) >= hi)
    return _out(df, le, se, d4 < 0, d4 > 0, stop_atr, tp_atr)

def squeeze_breakout(df, bb=20, pct=0.2, look=500, ch=20, exit_n=10, stop_atr=2.0):
    m, sd = df.c.rolling(bb).mean(), df.c.rolling(bb).std()
    w = 4 * sd / m
    thr = w.rolling(look).quantile(pct).shift(1)
    sq = (w < thr).rolling(6).max().astype(bool)
    hh, ll = df.h.rolling(ch).max().shift(1), df.l.rolling(ch).min().shift(1)
    xl, xh = df.l.rolling(exit_n).min().shift(1), df.h.rolling(exit_n).max().shift(1)
    return _out(df, sq & (df.c > hh), sq & (df.c < ll), df.c < xl, df.c > xh, stop_atr)

def momentum_mtf(df, look=24, thr=0.03, stop_atr=2.5):
    d4 = trend4h_dir(df); r = df.c / df.c.shift(look) - 1
    return _out(df, (r > thr) & (d4 > 0), (r < -thr) & (d4 < 0), r < 0, r > 0, stop_atr)

def breakout1h_v1(df):
    return breakout(df, n=168, exit_n=84, stop_atr=1.5)

CANDIDATES = {"A_breakout1h_v1": breakout1h_v1, "B_trend4h_v1": trend4h_on1h, "C_breakout1h_filtered": breakout1h_filtered,
              "D_pullback_mtf": pullback_mtf, "E_squeeze_breakout": squeeze_breakout, "F_momentum_mtf": momentum_mtf}
