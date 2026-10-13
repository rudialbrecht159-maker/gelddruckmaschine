"""Shared cost / risk model used by BOTH the backtester and the live paper engine."""
TAKER_FEE = 0.00045     # Hyperliquid base-tier taker
SLIPPAGE = 0.0003       # 3 bps adverse beyond half-spread (conservative for small size)
HALF_SPREAD = {"BTC": 0.00001, "ETH": 0.00002, "SOL": 0.00005, "AVAX": 0.0001, "SUI": 0.0001}
import json as _j, os as _o
def _lev_cap():
    try: c = _j.load(open(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)), "config.json")))
    except Exception: c = {}
    hard = min(float(c.get("leverage_hard_max", 5.0)), 5.0)          # absolute ceiling, never above 5x
    return max(1.0, min(float(c.get("leverage_cap", 3.0)), hard))   # default 3x
MAX_LEV = _lev_cap()
RISK_PER_TRADE = 0.01
MAINT_MARGIN = 1 / (2 * 20)   # HL: maint = 1/(2*maxLev); use 20x-tier worst case -> 2.5% (conservative for alts)

def fill_price(px, side, coin, spread_frac=None):
    """side +1 buy, -1 sell. Adverse fill."""
    hs = spread_frac / 2 if spread_frac is not None else HALF_SPREAD.get(coin, 0.0001)
    return px * (1 + side * (hs + SLIPPAGE))

def size_position(equity, entry, stop):
    """Notional so that a stop-out (incl. 2x fees + slippage) loses ~1% of equity; capped at 3x leverage."""
    dist = abs(entry - stop) / entry + 2 * TAKER_FEE + 2 * SLIPPAGE
    notional = equity * RISK_PER_TRADE / dist
    notional = min(notional, equity * MAX_LEV)
    return notional

def liq_price(entry, side, lev):
    """Isolated-margin liquidation approx: equity in position = margin - loss hits maint margin."""
    return entry * (1 - side * (1 / lev - MAINT_MARGIN))
MIN_NOTIONAL_USD = 10.0      # Hyperliquid minimum order value
BT_EURUSD = 1.12             # fixed FX used only in backtests (account in EUR)
