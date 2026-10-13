"""Public Hyperliquid info API client (read-only market data). No keys, no orders."""
import time, json, requests
URL = "https://api.hyperliquid.xyz/info"
COINS = ["BTC", "ETH", "SOL", "AVAX", "SUI"]
IV_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3600_000, "4h": 14400_000}

def post(body, retries=3):
    for i in range(retries):
        try:
            r = requests.post(URL, json=body, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception:
            if i == retries - 1: raise
            time.sleep(2 * (i + 1))

def candles(coin, interval, start_ms, end_ms=None):
    end_ms = end_ms or int(time.time() * 1000)
    out = {}
    s = start_ms
    while s < end_ms:
        d = post({"type": "candleSnapshot", "req": {"coin": coin, "interval": interval, "startTime": s, "endTime": end_ms}})
        if not d: break
        for c in d: out[c["t"]] = c
        last = d[-1]["t"]
        if last + IV_MS[interval] <= s or len(d) < 2: break
        s = last + IV_MS[interval]
        if len(d) < 4000: break
    rows = [out[k] for k in sorted(out)]
    return [{"t": c["t"], "o": float(c["o"]), "h": float(c["h"]), "l": float(c["l"]), "c": float(c["c"]), "v": float(c["v"])} for c in rows]

def funding_history(coin, start_ms):
    out = {}; s = start_ms
    while True:
        d = post({"type": "fundingHistory", "coin": coin, "startTime": s})
        if not d: break
        for f in d: out[f["time"]] = float(f["fundingRate"])
        if len(d) < 500: break
        s = d[-1]["time"] + 1
        time.sleep(0.2)
    return out  # time_ms -> hourly rate

def asset_ctxs():
    meta, ctxs = post({"type": "metaAndAssetCtxs"})
    res = {}
    for u, c in zip(meta["universe"], ctxs):
        if u["name"] in COINS:
            res[u["name"]] = {"mark": float(c["markPx"]), "oracle": float(c["oraclePx"]), "funding": float(c["funding"]),
                              "oi": float(c["openInterest"]), "dayVlm": float(c["dayNtlVlm"]), "maxLev": u.get("maxLeverage")}
    return res

def book(coin):
    d = post({"type": "l2Book", "coin": coin})
    bid = float(d["levels"][0][0]["px"]); ask = float(d["levels"][1][0]["px"])
    mid = (bid + ask) / 2
    depth = sum(float(l["px"]) * float(l["sz"]) for side in d["levels"] for l in side[:10])
    return {"time": d["time"], "bid": bid, "ask": ask, "mid": mid, "spread_bps": (ask - bid) / mid * 1e4, "depth10_usd": depth}
