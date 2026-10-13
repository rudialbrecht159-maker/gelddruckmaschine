import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sim
from strategies import atr, _out
D1 = 86400_000
def rt_cost(coin): return 2 * (sim.TAKER_FEE + sim.SLIPPAGE + sim.HALF_SPREAD.get(coin, 1e-4))
def gate(df, a, stop_atr, coin, k=5.0): return (stop_atr * a / df.c) >= k * rt_cost(coin)
def daily_close(df):
    """daily close known at the 4h bar closing the UTC day, ffilled; NaN before."""
    last = ((df.t + 4 * 3600_000) % D1) == 0
    blk = df.t // D1; cnt = blk.map(blk.value_counts())
    s = df.c.where(last & (cnt == 6)); return s
def adx(df, n=14):
    up, dn = df.h.diff(), -df.l.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0); mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([df.h - df.l, (df.h - df.c.shift()).abs(), (df.l - df.c.shift()).abs()], axis=1).max(axis=1)
    atr_ = tr.ewm(alpha=1/n).mean(); pdi = 100 * pd.Series(pdm, df.index).ewm(alpha=1/n).mean() / atr_; mdi = 100 * pd.Series(mdm, df.index).ewm(alpha=1/n).mean() / atr_
    return (100 * (pdi - mdi).abs() / (pdi + mdi)).ewm(alpha=1/n).mean()
def tsmom(df, coin=None, s=42, l=180, stop_atr=3.0, k=5.0, **_):
    a = atr(df); r1, r2 = df.c / df.c.shift(s) - 1, df.c / df.c.shift(l) - 1
    L, S = (r1 > 0) & (r2 > 0), (r1 < 0) & (r2 < 0); g = gate(df, a, stop_atr, coin, k)
    return _out(df, L & ~L.shift(1, fill_value=False) & g, S & ~S.shift(1, fill_value=False) & g, r1 < 0, r1 > 0, stop_atr)
def trend_adx(df, coin=None, fast=20, slow=100, dema=50, adx_min=20, stop_atr=2.5, k=5.0, **_):
    a = atr(df); up = df.c.ewm(span=fast).mean() > df.c.ewm(span=slow).mean()
    dc = daily_close(df).dropna(); de = dc.ewm(span=dema).mean()
    reg = np.sign(dc - de).reindex(df.index).ffill().fillna(0); reg[df.index.to_series().map(lambda i: (dc.index <= i).sum()) < dema] = 0
    ax = adx(df) > adx_min; g = gate(df, a, stop_atr, coin, k)
    cu, cd = up & ~up.shift(1, fill_value=False), ~up & up.shift(1, fill_value=True)
    return _out(df, cu & (reg > 0) & ax & g, cd & (reg < 0) & ax & g, ~up, up, stop_atr)
def funding_fade(df, coin=None, win=540, q=0.9, hold=42, stop_atr=3.0, k=5.0, **_):
    a = atr(df); fr = df["fund4"].rolling(18).mean()
    hi, lo = fr.rolling(win).quantile(q).shift(1), fr.rolling(win).quantile(1-q).shift(1)
    tr = df.c.ewm(span=50).mean() > df.c.ewm(span=200).mean(); g = gate(df, a, stop_atr, coin, k)
    le = (fr < lo) & tr & g; se = (fr > hi) & ~tr & g
    # time exit: hold bars since the most recent entry signal (deterministic, engine-independent approximation)
    since_l = le.astype(int).groupby((le).cumsum()).cumcount(); since_s = se.astype(int).groupby((se).cumsum()).cumcount()
    return _out(df, le, se, (~tr) | (since_l >= hold), tr | (since_s >= hold), stop_atr)
def xsmom(dfs, look=84, top=2, stop_atr=3.0, k=5.0):
    """dfs: {coin: df} aligned. Returns {coin: sigframe}. Decisions only on bars closing 00 UTC."""
    cs = list(dfs); R = pd.DataFrame({c: dfs[c].c / dfs[c].c.shift(look) - 1 for c in cs})
    T = dfs[cs[0]].t; day = ((T + 4 * 3600_000) % D1) == 0
    rk = R.rank(axis=1, ascending=False); n = len(cs); out = {}
    for c in cs:
        df = dfs[c]; a = atr(df); g = gate(df, a, stop_atr, c, k)
        le = day & (rk[c] == 1) & (R[c] > 0) & g; se = day & (rk[c] == n) & (R[c] < 0) & g
        out[c] = _out(df, le, se, day & (rk[c] > top), day & (rk[c] <= n - top), stop_atr)
    return out
