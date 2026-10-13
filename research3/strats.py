import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sim
from strategies import atr, _out
def rt_cost(coin, fee=None):
    f = sim.TAKER_FEE if fee is None else fee
    return 2 * (f + sim.SLIPPAGE + sim.HALF_SPREAD.get(coin, 1e-4))
def burst(df, coin, n=12, vmult=2.0, fast=240, slow=720, stop_atr=1.5, tp_atr=3.0, k=3.0):
    a = atr(df); tr = np.sign(df.c.ewm(span=fast).mean() - df.c.ewm(span=slow).mean())
    tr[df.index < slow] = 0
    hh, ll = df.h.rolling(n).max().shift(1), df.l.rolling(n).min().shift(1)
    vok = df.v > vmult * df.v.rolling(48).mean().shift(1)
    gate = (tp_atr * a / df.c) >= k * rt_cost(coin)
    return _out(df, (df.c > hh) & vok & (tr > 0) & gate, (df.c < ll) & vok & (tr < 0) & gate, df.c < ll, df.c > hh, stop_atr, tp_atr)
def zrev(df, coin, n=48, z=2.5, stop_atr=2.0, k=3.0):
    a = atr(df); m, sd = df.c.rolling(n).mean(), df.c.rolling(n).std(); zz = (df.c - m) / sd
    ap = a / df.c; vg = ap < ap.rolling(288).quantile(0.8).shift(1)
    gate = ((df.c - m).abs() / df.c) >= k * rt_cost(coin)
    return _out(df, (zz < -z) & vg & gate, (zz > z) & vg & gate, zz > 0, zz < 0, stop_atr)
def impulse(df, coin, mult=2.0, vmult=3.0, fast=60, slow=180, stop_atr=1.5, tp_atr=2.0, k=3.0):
    a = atr(df); tr = np.sign(df.c.ewm(span=fast).mean() - df.c.ewm(span=slow).mean()); tr[df.index < slow] = 0
    big = (df.h - df.l) > mult * a.shift(1); vok = df.v > vmult * df.v.rolling(60).mean().shift(1)
    gate = (tp_atr * a / df.c) >= k * rt_cost(coin); up = df.c > df.o
    return _out(df, big & vok & up & (tr > 0) & gate, big & vok & ~up & (tr < 0) & gate, tr < 0, tr > 0, stop_atr, tp_atr)
IDEAS = {"H1_burst5m": ("5m", burst, {}), "H2_zrev5m": ("5m", zrev, {}),
         "H3_burst15m": ("15m", burst, dict(fast=80, slow=240)), "H4_impulse1m": ("1m", impulse, {})}
