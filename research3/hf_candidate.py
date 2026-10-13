"""research3 HF candidate: H2 zrev5m (5m z-score mean reversion, vol gate, economic gate k=3). SIMULATED / paper only.
CONFIDENCE: VERY LOW. Pre-registered selection rule NOT met (backtest net negative after costs, see report.md).
Usable as an observation-only paper test.

Interface:
    signal(candles, coin, position_side=0) -> dict
      candles: list of dicts or DataFrame with t,o,h,l,c,v of CLOSED 5m bars for `coin`, oldest first, >= MIN_BARS rows.
               Do NOT include the still-forming bar. Call it every minute: it is idempotent and only changes when a new 5m bar closes.
      position_side: +1 long open, -1 short open, 0 flat (for this coin, this strategy)
      returns {"bar_t": ms open of last closed bar, "action": "open_long"|"open_short"|"close"|"hold"|"none",
               "stop": absolute stop price for opens (else None), "atr": float, "z": float, "reason": str}
      Execution assumption (as in backtest): act at the next 5m bar's open, i.e. immediately on receipt.
      Risk sizing, $10 min, 3x cap, max 2 positions, daily stop and DD halt are the engine's job (sim.size_position etc.).
"""
import pandas as pd, numpy as np
from strats import zrev
INTERVAL = "5m"; MIN_BARS = 340   # 288 vol-gate window + 48 SMA + ATR warm-up
PARAMS = dict(n=48, z=2.5, stop_atr=2.0, k=3.0)

def signal(candles, coin, position_side=0):
    df = pd.DataFrame(candles)[["t", "o", "h", "l", "c", "v"]].astype({"o": float, "h": float, "l": float, "c": float, "v": float}).reset_index(drop=True)
    if len(df) < MIN_BARS: return dict(bar_t=None, action="none", stop=None, atr=None, z=None, reason=f"need {MIN_BARS} closed bars, got {len(df)}")
    if (df.t.diff().dropna() != 300_000).any(): return dict(bar_t=int(df.t.iloc[-1]), action="none", stop=None, atr=None, z=None, reason="gap in candles -> no signal")
    s = zrev(df, coin, **PARAMS).iloc[-1]; last = df.iloc[-1]
    m, sd = df.c.rolling(48).mean().iloc[-1], df.c.rolling(48).std().iloc[-1]; z = float((last.c - m) / sd)
    base = dict(bar_t=int(last.t), atr=float(s["atr"]), z=round(z, 3), stop=None)
    if position_side > 0: return {**base, "action": "close" if s["lx"] else "hold", "reason": "z crossed above 0" if s["lx"] else "holding long"}
    if position_side < 0: return {**base, "action": "close" if s["sx"] else "hold", "reason": "z crossed below 0" if s["sx"] else "holding short"}
    if s["le"]: return {**base, "action": "open_long", "stop": float(last.c - PARAMS["stop_atr"] * s["atr"]), "reason": "z<-2.5, vol gate ok, move>=3x cost"}
    if s["se"]: return {**base, "action": "open_short", "stop": float(last.c + PARAMS["stop_atr"] * s["atr"]), "reason": "z>2.5, vol gate ok, move>=3x cost"}
    return {**base, "action": "none", "reason": "no setup"}
