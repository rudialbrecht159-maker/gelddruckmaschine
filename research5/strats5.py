import os, sys, numpy as np, pandas as pd
R = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(R, "..")
for p in (ROOT, f"{ROOT}/research2", f"{ROOT}/research3", f"{ROOT}/research4"): sys.path.insert(0, p)
import sim
from strategies import trend, breakout, atr, _out
from candidates import breakout1h_filtered, trend4h_dir, trend4h_on1h, _h4
from strats import zrev
from rules import funding_fade, adx
def rt(coin): return 2 * (sim.TAKER_FEE + sim.SLIPPAGE + sim.HALF_SPREAD.get(coin, 1e-4))
# ---- existing (fixed params) ----
def s1_trend4h(df, coin): return trend(df, fast=10, slow=200, stop_atr=3.0)
def s2_breakout1h(df, coin): return breakout(df, n=168, exit_n=84, stop_atr=1.5)
def s3_breakout1h_filtered(df, coin): return breakout1h_filtered(df, n=48, exit_n=24, stop_atr=2.0, vol_mult=1.5)
def s4_zscore5m(df, coin): return zrev(df, coin)
def s5_funding_fade4h(df, coin): return funding_fade(df, coin=coin)
# ---- new (preregistered) ----
def n1_bbrev_1h(df, coin, k=5.0):
    a = atr(df); d4 = trend4h_dir(df); m, sd = df.c.rolling(20).mean(), df.c.rolling(20).std()
    ap = a / df.c; vg = ap < ap.rolling(500).quantile(0.7).shift(1); g = (2 * a / df.c) >= k * rt(coin)
    return _out(df, (d4 > 0) & (df.c < m - 2*sd) & vg & g, (d4 < 0) & (df.c > m + 2*sd) & vg & g, df.c > m, df.c < m, 2.0)
def n2_donchian_adx_4h(df, coin, k=5.0):
    a = atr(df); hh, ll = df.h.rolling(20).max().shift(1), df.l.rolling(20).min().shift(1)
    xl, xh = df.l.rolling(10).min().shift(1), df.h.rolling(10).max().shift(1); ax = adx(df) > 25; g = (2 * a / df.c) >= k * rt(coin)
    return _out(df, (df.c > hh) & ax & g, (df.c < ll) & ax & g, df.c < xl, df.c > xh, 2.0)
def n3_zmom_1h(df, coin, k=5.0):
    a = atr(df); d4 = trend4h_dir(df); r1 = df.c.pct_change(); z = (df.c / df.c.shift(6) - 1) / (r1.rolling(168).std() * np.sqrt(6))
    g = (1.5 * a / df.c) >= k * rt(coin)
    return _out(df, (z > 2) & (d4 > 0) & g, (z < -2) & (d4 < 0) & g, d4 < 0, d4 > 0, 1.5, 3.0)
# ---- 4h strategy evaluated on 1h timeline (for multi-TF portfolio) ----
def on1h(fn4):
    def f(df, coin):
        h4 = _h4(df); g = df.groupby(df.t // 14400_000)
        h4 = h4.assign(t=g.t.first().loc[(df.t // 14400_000).loc[h4.last_i].values].values, v=g.v.sum().loc[(df.t // 14400_000).loc[h4.last_i].values].values,
                       fund4=df.fund4.loc[h4.last_i].values).reset_index(drop=True)
        s4 = fn4(h4[["t", "o", "h", "l", "c", "v", "fund4"]], coin)
        o = pd.DataFrame(False, index=df.index, columns=["le", "se", "lx", "sx"])
        for k_ in ("le", "se", "lx", "sx"): o.loc[h4.last_i.values, k_] = s4[k_].values.astype(bool)
        o["atr"] = pd.Series(s4["atr"].values, index=h4.last_i.values).reindex(df.index).ffill()
        o["stop_atr"] = float(s4["stop_atr"].iloc[-1]); o["tp_atr"] = np.nan; return o
    return f
EXISTING = {"S1 trend-4h-v1 (aktiv)": ("4h", s1_trend4h), "S2 breakout-1h-v1 (Schatten)": ("1h", s2_breakout1h),
            "S3 test-breakout1h-filtered": ("1h", s3_breakout1h_filtered), "S4 test-hf-zscore-5m": ("5m", s4_zscore5m),
            "S5 funding-fade-4h-x1": ("4h", s5_funding_fade4h)}
NEW = {"N1 bbrev_1h": ("1h", n1_bbrev_1h), "N2 donchian_adx_4h": ("4h", n2_donchian_adx_4h), "N3 zmom_1h": ("1h", n3_zmom_1h)}
MAX_HOLD = {"N1 bbrev_1h": 24, "N3 zmom_1h": 12}
