"""research5 unified backtest framework (SIMULATED). One shared €50 account per run, live limits:
1% risk, 3x cap, $10 min, max 2 positions, 3% daily stop, 10% DD halt. Signals at bar close -> act next bar.
Fee modes: 'taker' (0.045% both sides + slippage + half-spread) or 'maker' (entry = post-only limit at signal close,
filled only if next bar trades THROUGH the limit by 1 bp, else missed; maker fee 0.015%, no slippage; exits taker)."""
import os, sys, json, numpy as np, pandas as pd
R = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(R, ".."); sys.path.insert(0, ROOT)
import sim
COINS = ["BTC", "ETH", "SOL", "AVAX", "SUI"]
MS = {"5m": 300_000, "15m": 900_000, "1h": 3600_000, "4h": 14400_000}
SRC = {"5m": "research3/data", "15m": "research3/data", "1h": "data", "4h": "research4/data"}
TAKER, MAKER = 0.00045, 0.00015

def _fund(coin):
    fs = {}
    for d in ("data", "research4/data", "research3/data"):
        p = f"{ROOT}/{d}/{coin}_funding.json"
        if os.path.exists(p): fs.update({(int(k)//3600_000)*3600_000: v for k, v in json.load(open(p)).items()})
    return pd.Series(fs).sort_index()

def load(tf, coins=COINS):
    dfs = {}
    for c in coins:
        df = pd.DataFrame(json.load(open(f"{ROOT}/{SRC[tf]}/{c}_{tf}.json"))); fs = _fund(c); ms = MS[tf]
        if ms >= 3600_000:
            hrs = fs.reindex(range(int(df.t.min()), int(df.t.max()) + ms, 3600_000)).fillna(0.0)
            cs = np.concatenate([[0], np.cumsum(hrs.values)]); idx = ((df.t - df.t.min()) // 3600_000).astype(int).values; k = ms // 3600_000
            df["fund_bar"] = cs[np.minimum(idx + k, len(hrs))] - cs[idx]
        else:
            first = (df.t % 3600_000) < ms; df["fund_bar"] = np.where(first, ((df.t // 3600_000) * 3600_000).map(fs).fillna(0.0), 0.0)
        df["fund4"] = fs.reindex(df.t + ms - 3600_000, method="ffill").values if ms >= 3600_000 else fs.reindex((df.t // 3600_000) * 3600_000, method="ffill").values
        dfs[c] = df.set_index("t")
    common = sorted(set.intersection(*[set(d.index) for d in dfs.values()]))
    return {c: d.loc[common].reset_index() for c, d in dfs.items()}

def run(dfs, sigsets, i0, i1, fee_mode="taker", risk=0.01, start=50.0, max_pos=2, dd_halt=True, cost_mult=1.0, max_hold=None):
    coins = list(dfs); T = dfs[coins[0]].t.values
    O, H, L, C, F = ({c: dfs[c][k].values for c in coins} for k in ("o", "h", "l", "c", "fund_bar"))
    sigsets = [(nm, {c: {k: sg[k].values for k in ("le", "se", "lx", "sx", "atr", "stop_atr", "tp_atr")} for c, sg in ss.items()}) for nm, ss in sigsets]
    fee_t = TAKER * cost_mult; slip = sim.SLIPPAGE * cost_mult
    eq = start; pos = {}; pend = []; trades = []; curve = []; peak = start; halted = False; day = None; day_start = start; missed = skipped = 0
    def px_fill(px, side, c): return px * (1 + side * (sim.HALF_SPREAD.get(c, 1e-4) * cost_mult + slip))
    def close(c, px, i, why):
        nonlocal eq
        p = pos.pop(c); s = p["side"]; xp = px if why == "liquidated" else px_fill(px, -s, c)
        pnl = -p["margin"] if why == "liquidated" else (xp - p["entry"]) * p["qty"] * s
        fee = p["qty"] * xp * fee_t; eq += pnl - fee
        trades.append(dict(strategy=p["strat"], coin=c, side=s, t_in=int(T[p["i"]]), t_out=int(T[i]), bars=i - p["i"], exit_reason=why, gross=pnl,
                           fees=p["fee"] + fee, funding=p["fund"], net=pnl - fee - p["fee"] - p["fund"], notional=p["qty"] * p["entry"]))
    for i in range(i0, i1):
        d = T[i] // 86400_000
        if d != day: day = d; day_start = eq + sum((C[c][i-1] - p["entry"]) * p["qty"] * p["side"] for c, p in pos.items())
        for a in pend:
            if a[0] == "close" and a[1] in pos: close(a[1], O[a[1]][i], i, "signal")
        for a in pend:
            if a[0] != "open": continue
            _, c, side, sname, at, sa, ta, ref = a
            if c in pos or len(pos) >= max_pos or halted: continue
            if fee_mode == "maker":
                lim = ref
                if not ((L[c][i] <= lim * (1 - 1e-4)) if side > 0 else (H[c][i] >= lim * (1 + 1e-4))): missed += 1; continue
                entry, fr = lim, MAKER * cost_mult
            else: entry, fr = px_fill(O[c][i], side, c), fee_t
            stop = entry - side * sa * at; dist = abs(entry - stop) / entry + fr + fee_t + 2 * slip
            used = sum(p["qty"] * p["entry"] for p in pos.values()); notional = min(eq * risk / dist, eq * sim.MAX_LEV - used)
            if notional * sim.BT_EURUSD < sim.MIN_NOTIONAL_USD: skipped += 1; continue
            lev = max(notional / eq, 1.0001); fee = notional * fr; eq -= fee
            pos[c] = dict(strat=sname, side=side, entry=entry, stop=stop, tp=entry + side * ta * at if not np.isnan(ta) else None, qty=notional / entry,
                          margin=notional / lev, liq=sim.liq_price(entry, side, lev), i=i, fee=fee, fund=0.0)
        pend = []
        for c in list(pos):
            p = pos[c]; s = p["side"]; w = L[c][i] if s > 0 else H[c][i]; px = why = None
            if (w - p["stop"]) * s <= 0: px, why = (O[c][i], "stop_gap") if (O[c][i] - p["stop"]) * s <= 0 else (p["stop"], "stop")
            elif p["tp"] is not None and ((H[c][i] if s > 0 else L[c][i]) - p["tp"]) * s >= 0: px, why = p["tp"], "tp"
            if px is not None:
                if (px - p["liq"]) * s <= 0: px, why = p["liq"], "liquidated"
                close(c, px, i, why)
        for c, p in pos.items():
            f = p["qty"] * C[c][i] * F[c][i] * p["side"]; eq -= f; p["fund"] += f
        mtm = eq + sum((C[c][i] - p["entry"]) * p["qty"] * p["side"] for c, p in pos.items()); curve.append(mtm); peak = max(peak, mtm)
        if dd_halt and mtm < peak * 0.9: halted = True
        block = halted or mtm < day_start * 0.97
        if i < i1 - 1:
            for c in list(pos):
                if max_hold and i - pos[c]["i"] + 1 >= max_hold.get(pos[c]["strat"], 10**9): pend.append(("close", c))
            for sname, sigs in sigsets:
                for c in coins:
                    sg = sigs[c]
                    if c in pos:
                        p = pos[c]
                        if p["strat"] == sname and ((p["side"] > 0 and sg["lx"][i]) or (p["side"] < 0 and sg["sx"][i])): pend.append(("close", c))
                    elif not block and not np.isnan(sg["atr"][i]):
                        side = 1 if sg["le"][i] else (-1 if sg["se"][i] else 0)
                        if side: pend.append(("open", c, side, sname, sg["atr"][i], sg["stop_atr"][i], sg["tp_atr"][i], C[c][i]))
    for c in list(pos): close(c, C[c][i1-1], i1-1, "end")
    if curve: curve[-1] = eq
    return dict(equity=eq, trades=trades, curve=np.array(curve), t=T[i0:i1], halted=halted, missed=missed, skipped=skipped, t0=int(T[i0]), t1=int(T[i1-1]))

from statistics import NormalDist
_N = NormalDist(); rng = np.random.default_rng(5)
def metrics(r, n_trials=173, start=50.0):
    tr = r["trades"]; nets = np.array([t["net"] for t in tr]); cv = np.concatenate([[start], r["curve"]]); pk = np.maximum.accumulate(cv)
    ts = pd.Series(cv[1:], index=pd.to_datetime(r["t"], unit="ms")); dr = ts.resample("1D").last().dropna().pct_change().dropna().values
    n = len(dr); sr = dr.mean() / dr.std() if n > 10 and dr.std() > 0 else 0.0; dsr = 0.0
    if n > 10 and dr.std() > 0:
        z = (dr - dr.mean()) / dr.std(); sk, ku = (z**3).mean(), (z**4).mean(); em = 0.5772156649
        sr0 = np.sqrt(1/n) * ((1-em) * _N.inv_cdf(1 - 1/n_trials) + em * _N.inv_cdf(1 - 1/(n_trials*np.e)))
        dsr = _N.cdf((sr - sr0) * np.sqrt(n - 1) / np.sqrt(max(1e-9, 1 - sk*sr + (ku-1)/4*sr**2)))
    w, l = nets[nets > 0], nets[nets <= 0]; days = (r["t1"] - r["t0"]) / 86400_000
    return dict(net_pct=round((r["equity"]/start - 1)*100, 2), net_eur=round(r["equity"] - start, 2), gross_eur=round(sum(t["gross"] for t in tr), 2),
                fees_eur=round(sum(t["fees"] for t in tr), 2), funding_eur=round(sum(t["funding"] for t in tr), 2), maxdd_pct=round(float(np.max(1 - cv/pk))*100, 2),
                trades=len(tr), trades_per_month=round(len(tr) / days * 30.44, 1) if days else 0, win_pct=round(len(w)/len(nets)*100, 1) if len(nets) else None,
                pf=round(w.sum() / -l.sum(), 2) if l.sum() < 0 else None, sharpe=round(sr*np.sqrt(365), 2), dsr=round(dsr, 3),
                p_le0=round(float((rng.choice(nets, (4000, len(nets))).sum(1) <= 0).mean()), 3) if len(nets) else None, halted=r["halted"], missed_maker=r["missed"], skipped_min=r["skipped"],
                days=round(days, 1))
def daily_returns(r, start=50.0):
    ts = pd.Series(r["curve"], index=pd.to_datetime(r["t"], unit="ms")).resample("1D").last().dropna()
    return pd.concat([pd.Series([start], index=[ts.index[0] - pd.Timedelta(days=1)]), ts]).pct_change().dropna()
