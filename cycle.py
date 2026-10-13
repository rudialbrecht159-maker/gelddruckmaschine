"""GELDDRUCKMASCHINE one-shot paper-trading cycle. SIMULATED ONLY - never places real orders.
Run: cd /workspace/gelddruckmaschine && .venv/bin/python cycle.py"""
import json, os, time, sqlite3, shutil, traceback, datetime as dt, requests
import numpy as np, pandas as pd
import hl, sim
from strategies import STRATS
try:
    from research2.candidates import breakout1h_filtered as _bf; STRATS.setdefault("breakout1h_filtered", _bf)
except Exception as _e: print("research2 import failed:", _e)
try:
    from research4.candidate import funding_fade_trend as _fft; STRATS.setdefault("funding_fade_trend", _fft)
except Exception as _e: print("research4 import failed:", _e)
BASE = os.path.dirname(os.path.abspath(__file__)); os.chdir(BASE)
STORE = os.environ.get("GDM_STORE") or (open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".store_path")).read().strip() if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".store_path")) else None)
CFG = json.load(open("config.json")); STATE_F = "state/state.json"; DB = "state/paper.db"; LOG_F = "logs/execution.log"
PORTFOLIOS = [
    dict(name="shadow", strat=CFG["shadow_strategy"], state="state/shadow_breakout1h.json", db="state/shadow_breakout1h.db", log="logs/shadow_breakout1h.log", primary=False),
    *[dict(name=t["version"], strat=t, state=f"state/{t['version']}.json", db=f"state/{t['version']}.db", log=f"logs/{t['version']}.log", primary=False, role=t.get("role", "TEST"))
      for t in CFG.get("test_strategies", [])],
    dict(name="active", strat=CFG["active_strategy"], state="state/state.json", db="state/paper.db", log="logs/execution.log", primary=True)]
now_ms = lambda: int(time.time() * 1000)
iso = lambda ms: dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

def db():
    con = sqlite3.connect(DB)
    con.execute("create table if not exists trades(id integer primary key, coin, side, strategy, open_ts, close_ts, entry, exit, qty, notional_usd, lev, fees_eur, funding_eur, pnl_eur, reason)")
    con.execute("create table if not exists exec_log(ts, status, msg)")
    con.execute("create table if not exists runs(ts, trigger, status, duration_s, equity_eur, actions, problems)")
    con.execute("create table if not exists equity(ts, equity_eur, balance_eur, upnl_eur)")
    return con

CUR_PF = {}
def load_state():
    if os.path.exists(STATE_F): return json.load(open(STATE_F))
    b = float(CUR_PF.get("start_balance", CFG["start_balance_eur"]))
    return dict(created=iso(now_ms()), balance_eur=b, peak_equity_eur=b, day=None, day_start_equity_eur=b, positions={},
                last_bar_processed={}, halted=False, halt_reason=None, fees_eur=0.0, funding_eur=0.0, realized_eur=0.0,
                fx_eurusd=None, last_data_ok=None, cycles=0)

def get_fx(st):
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=EUR&to=USD", timeout=10).json()
        st["fx_eurusd"] = float(r["rates"]["USD"]); st["fx_date"] = r["date"]
    except Exception as e:
        if not st.get("fx_eurusd"): raise RuntimeError(f"no EURUSD rate available: {e}")
    return st["fx_eurusd"]

import sys
def trigger_source():
    for i, a in enumerate(sys.argv):
        if a == "--trigger" and i + 1 < len(sys.argv): return sys.argv[i + 1]
    if os.environ.get("GDM_TRIGGER"): return os.environ["GDM_TRIGGER"]
    return "manual (tty)" if sys.stdin.isatty() else "non-interactive (likely hourly routine)"

def main(pf=None):
    global STATE_F, DB, LOG_F, CUR_PF
    pf = pf or PORTFOLIOS[-1]; CUR_PF = pf; STATE_F, DB, LOG_F = pf["state"], pf["db"], pf["log"]
    os.makedirs("state", exist_ok=True); os.makedirs("logs", exist_ok=True)
    st = load_state(); con = db(); log = []; t0 = now_ms(); st["cycles"] += 1
    strat = pf["strat"]; tf = strat["tf"]; ivms = hl.IV_MS[tf]
    fn = STRATS[strat["name"]] if strat else None
    fx = get_fx(st)
    # ---------- 1. market data + validation ----------
    data, problems = {}, []
    ctx = hl.asset_ctxs()
    for c in hl.COINS:
        try:
            cs = hl.candles(c, tf, t0 - strat.get("history_bars", 1000) * ivms)
            cs = [x for x in cs if x["t"] + ivms <= t0]           # closed bars only
            h1 = hl.candles(c, "1h", t0 - 3 * 86400_000)            # intrabar path for stop checks
            bk = hl.book(c)
            age_bar = (t0 - (cs[-1]["t"] + ivms)) / 60000
            ok = age_bar <= ivms / 60000 + CFG["stale_candle_grace_min"] and (t0 - bk["time"]) / 1000 <= CFG["stale_book_sec"] and c in ctx
            if not ok: problems.append(f"{c}: stale data (bar age {age_bar:.0f}m, book age {(t0-bk['time'])/1000:.0f}s)")
            if bk["spread_bps"] > CFG["max_spread_bps"]: problems.append(f"{c}: spread {bk['spread_bps']:.1f}bps too wide"); ok = False
            data[c] = dict(df=pd.DataFrame(cs), h1=h1, book=bk, ctx=ctx.get(c), ok=ok)
        except Exception as e:
            problems.append(f"{c}: fetch error {e}"); data[c] = dict(ok=False)
    if any(d["ok"] for d in data.values()): st["last_data_ok"] = iso(t0)
    try:
        cj = {c: d["df"].tail(300)[["t","o","h","l","c","v"]].values.tolist() for c, d in data.items() if d.get("ok")}
        old = json.load(open(f"state/candles_{tf}.json")) if os.path.exists(f"state/candles_{tf}.json") else {}
        old.update(cj); json.dump(dict(old, _fetched=iso(t0)), open(f"state/candles_{tf}.json", "w"))
    except Exception as e: problems.append(f"candle export failed: {e}")
    # ---------- 2. manage open positions: funding, stops (gap-aware), signal exits ----------
    for c, p in list(st["positions"].items()):
        d = data.get(c, {})
        if "h1" not in d: log.append(f"{c}: no data, position kept, cannot check stop"); continue
        s = p["side"]; exit_px = why = None
        # actual hourly funding since last accrual
        try:
            fh = hl.funding_history(c, p["fund_ts"] + 1)
            for ts, rate in sorted(fh.items()):
                f_usd = p["qty"] * d["ctx"]["oracle"] * rate * s; p["funding_eur"] += f_usd / fx; st["balance_eur"] -= f_usd / fx
                st["funding_eur"] += f_usd / fx; p["fund_ts"] = ts
        except Exception as e: log.append(f"{c}: funding fetch failed {e}")
        for k in [x for x in d["h1"] if x["t"] + 3600_000 > p["checked_ts"]]:
            lo, hi, op = float(k["l"]), float(k["h"]), float(k["o"])
            if ((lo if s > 0 else hi) - p["stop"]) * s <= 0:
                gap = (op - p["stop"]) * s <= 0 and k["t"] >= p["checked_ts"]
                exit_px, why = (op, "stop_gap") if gap else (p["stop"], "stop"); break
        if exit_px is None and p.get("tp"):   # take-profit only where the strategy defines a target
            for k in [x for x in d["h1"] if x["t"] + 3600_000 > p["checked_ts"]]:
                if ((float(k["h"]) if s > 0 else float(k["l"])) - p["tp"]) * s >= 0: exit_px, why = p["tp"], "tp"; break
        p["checked_ts"] = t0
        if exit_px is None and (d["book"]["mid"] - p["stop"]) * s <= 0: exit_px, why = d["book"]["mid"], "stop"
        if exit_px is None and p.get("tp") and (d["book"]["mid"] - p["tp"]) * s >= 0: exit_px, why = d["book"]["mid"], "tp"
        if exit_px is None and pf.get("force_close"): exit_px, why = d["book"]["mid"], "emergency_close"
        if exit_px is None and d["ok"] and len(d["df"]):
            sig = (fn(d["df"], coin=c, position_side=s, **strat["params"]) if strat.get("adapter") else fn(d["df"], **strat["params"])).iloc[-1]
            if (s > 0 and sig["lx"]) or (s < 0 and sig["sx"]): exit_px, why = d["book"]["mid"], "signal_exit"
        if exit_px is not None:
            if (exit_px - p["liq"]) * s <= 0: why = "liquidated"
            close_pos(st, con, c, p, exit_px, why, fx, d["book"]); log.append(f"CLOSED {c} {why} @ {exit_px}")
    # ---------- 3. risk state ----------
    upnl = sum(((data[c]["book"]["mid"] if "book" in data.get(c, {}) else p["entry"]) - p["entry"]) * p["qty"] * p["side"] / fx for c, p in st["positions"].items())
    equity = st["balance_eur"] + upnl
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    if st["day"] != day: st["day"], st["day_start_equity_eur"] = day, equity
    st["peak_equity_eur"] = max(st["peak_equity_eur"], equity)
    dd = 1 - equity / st["peak_equity_eur"]; dloss = 1 - equity / st["day_start_equity_eur"]
    if dd >= CFG["max_drawdown_halt"] and not st["halted"]: st["halted"], st["halt_reason"] = True, f"max drawdown {dd:.1%} reached {iso(t0)}"
    block = []
    if st["halted"]: block.append("HALTED: " + st["halt_reason"])
    if pf.get("no_entries"): block.append(pf.get("no_entries_reason", "no new entries"))
    if st.get("phase_action") == "pause": block.append(f"PHASE PAUSE: {st.get('phase_note', 'phase failed')}")
    if dloss >= CFG["daily_loss_stop"]: block.append(f"daily loss {dloss:.1%} >= 3%")
    if not strat: block.append("no validated strategy")
    # ---------- 4. entries ----------
    signals = {}
    for c in hl.COINS:
        d = data[c]
        if not d.get("ok"): signals[c] = "no data / stale -> no entry"; continue
        df = d["df"]; last_t = int(df.t.iloc[-1])
        sig = (fn(df, coin=c, position_side=0, **strat["params"]) if strat.get("adapter") else fn(df, **strat["params"])).iloc[-1]
        side = 1 if sig["le"] else -1 if sig["se"] else 0
        fresh = st["last_bar_processed"].get(c) != last_t
        signals[c] = f"bar {iso(last_t + ivms)} close {fmtp(df.c.iloc[-1])}: " + {1: "LONG entry", -1: "SHORT entry", 0: "no entry"}[side] + (f" [{sig['reason']}]" if "reason" in sig.index else "") + ("" if fresh else " (bar already processed)")
        st["last_bar_processed"][c] = last_t
        if not side or not fresh: continue
        why_not = list(block)
        if c in st["positions"]: why_not.append("already in position (no averaging)")
        if len(st["positions"]) >= CFG["max_positions"]: why_not.append("max positions")
        if why_not: signals[c] += " BLOCKED: " + "; ".join(why_not); continue
        bk = d["book"]; a = float(sig["atr"]) if strat.get("adapter") else float(sim_atr(df))
        entry = sim.fill_price(bk["ask"] if side > 0 else bk["bid"], side, c, spread_frac=0)
        stop = entry - side * (float(sig["stop_atr"]) if strat.get("adapter") else strat["params"]["stop_atr"]) * a
        if not (np.isfinite(stop) and (entry - stop) * side > 0):   # every trade MUST have a valid stop-loss
            signals[c] += " BLOCKED: invalid stop-loss"; log.append(f"SKIPPED {c}: invalid stop {stop}"); continue
        tp = None
        if "tp" in sig.index and pd.notna(sig["tp"]): tp = float(sig["tp"])
        elif "tp_atr" in sig.index and pd.notna(sig["tp_atr"]): tp = entry + side * float(sig["tp_atr"]) * a
        elif strat["params"].get("tp_atr"): tp = entry + side * float(strat["params"]["tp_atr"]) * a
        if tp is not None and (tp - entry) * side <= 0: tp = None
        notional_eur = sim.size_position(equity, entry, stop)
        used = sum(p["notional_usd"] / fx for p in st["positions"].values())
        notional_eur = min(notional_eur, CFG["max_total_notional_x_equity"] * equity - used)
        if notional_eur * fx < sim.MIN_NOTIONAL_USD:
            msg = f"SKIPPED {c}: 1%-risk size ${notional_eur*fx:.2f} < Hyperliquid min ${sim.MIN_NOTIONAL_USD:.0f}"
            signals[c] += " BLOCKED: " + msg; log.append(msg)
            st.setdefault("min_order_skips", []).insert(0, dict(ts=iso(t0), coin=c, side="LONG" if side > 0 else "SHORT", size_usd=round(notional_eur * fx, 2), min_usd=sim.MIN_NOTIONAL_USD))
            st["min_order_skips"] = st["min_order_skips"][:100]; st["min_order_skips_total"] = st.get("min_order_skips_total", 0) + 1; continue
        lev = notional_eur / equity  # isolated margin model: margin = notional / max(lev,1)
        fee = notional_eur * sim.TAKER_FEE; st["balance_eur"] -= fee; st["fees_eur"] += fee
        qty = notional_eur * fx / entry
        st["positions"][c] = dict(side=side, entry=entry, stop=stop, qty=qty, notional_usd=notional_eur * fx, lev=round(lev, 3),
                                  liq=sim.liq_price(entry, side, max(lev, 1.0001)), margin_eur=notional_eur / max(lev, 1), open_ts=t0, checked_ts=t0,
                                  fund_ts=t0, fees_eur=fee, funding_eur=0.0, strategy=strat["version"], tp=tp, risk_eur=equity * sim.RISK_PER_TRADE,
                                  book_at_entry=bk)
        log.append(f"OPENED {c} {'LONG' if side>0 else 'SHORT'} {qty:.6g} @ {entry:.6g} stop {stop:.6g}{f' tp {tp:.6g}' if tp else ''} lev {lev:.2f}x")
    # ---------- 5. persist ----------
    upnl = sum(((data[c]["book"]["mid"] if "book" in data.get(c, {}) else p["entry"]) - p["entry"]) * p["qty"] * p["side"] / fx for c, p in st["positions"].items())
    for c, p in st["positions"].items():
        if "book" in data.get(c, {}): p["mark"] = data[c]["book"]["mid"]; p["upnl_eur"] = (p["mark"] - p["entry"]) * p["qty"] * p["side"] / fx
    equity = st["balance_eur"] + upnl
    st["peak_equity_eur"] = max(st["peak_equity_eur"], equity)
    status = "OK" if not problems else "DEGRADED"
    st.update(last_cycle=iso(t0), last_status=status, last_problems=problems, last_signals=signals, last_actions=log, equity_eur=equity,
              upnl_eur=upnl, risk=dict(dd=dd, daily_loss=dloss, blocks=block),
              market={c: dict(mid=d["book"]["mid"], spread_bps=d["book"]["spread_bps"], funding_1h=d["ctx"]["funding"], oi=d["ctx"]["oi"], dayVlm=d["ctx"]["dayVlm"]) for c, d in data.items() if "book" in d})
    con.execute("insert into equity values(?,?,?,?)", (iso(t0), equity, st["balance_eur"], upnl))
    con.execute("insert into exec_log values(?,?,?)", (iso(t0), status, json.dumps(dict(problems=problems, actions=log, signals=signals))))
    con.execute("insert into runs values(?,?,?,?,?,?,?)", (iso(t0), trigger_source(), status, round((now_ms()-t0)/1000, 1), equity, len(log), len(problems)))
    con.commit()
    try:   # research5 phase evaluator (plug-in); action 'pause' blocks new entries from the next cycle on
        import plugins
        r = plugins.phase_eval(con, st["created"], float(CUR_PF.get("start_balance", CFG["start_balance_eur"])))
        if r:
            if r["action"] == "pause" and st.get("phase_action") != "pause": log.append(f"PHASE PAUSE: {r['recommendation']}")
            st.update(phase=r, phase_action=r["action"], phase_note=r["recommendation"])
    except Exception as e: problems.append(f"phase eval failed: {e}")
    json.dump(st, open(STATE_F + ".tmp", "w"), indent=1); os.replace(STATE_F + ".tmp", STATE_F)
    with open(LOG_F, "a") as f: f.write(f"{iso(t0)} {status} trigger={trigger_source()!r} equity={equity:.4f} actions={log} problems={problems}\n")
    print(f"[{pf['name']} {strat['version']}]", end=" ")
    if not pf["primary"]:
        print(f"{iso(t0)} {status} equity €{equity:.4f} | positions {list(st['positions'])} | actions {log or 'none'}"); return
    import dashboard; dashboard.build(st, con, CFG)
    mirror()
    print(f"{iso(t0)} {status} equity €{equity:.4f} | positions {list(st['positions'])} | actions {log or 'none'}")
    for c, s in signals.items(): print(f"  {c}: {s}")
    if problems: print("  PROBLEMS:", problems)

def fmtp(v):
    return f"{v:,.1f}" if v >= 1000 else f"{v:.3f}" if v >= 10 else f"{v:.4f}"

def sim_atr(df):
    from strategies import atr; return atr(df).iloc[-1]

def close_pos(st, con, c, p, px, why, fx, bk):
    s = p["side"]
    xp = px if why == "liquidated" else sim.fill_price(px, -s, c, spread_frac=bk["spread_bps"] / 1e4)
    pnl_usd = (xp - p["entry"]) * p["qty"] * s
    pnl_eur = -p["margin_eur"] if why == "liquidated" else pnl_usd / fx
    fee = p["qty"] * xp / fx * sim.TAKER_FEE
    st["balance_eur"] += pnl_eur - fee; st["fees_eur"] += fee; st["realized_eur"] += pnl_eur - fee - p["fees_eur"] - p["funding_eur"]
    con.execute("insert into trades(coin,side,strategy,open_ts,close_ts,entry,exit,qty,notional_usd,lev,fees_eur,funding_eur,pnl_eur,reason) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (c, "LONG" if s > 0 else "SHORT", p["strategy"], iso(p["open_ts"]), iso(now_ms()), p["entry"], xp, p["qty"], p["notional_usd"], p["lev"],
                 p["fees_eur"] + fee, p["funding_eur"], pnl_eur - fee - p["fees_eur"] - p["funding_eur"], why))
    del st["positions"][c]

def mirror():
    if not STORE: return
    if os.environ.get("GDM_NO_MIRROR"): return
    try:
        os.makedirs(STORE, exist_ok=True)
        for f in ["state/state.json", "state/paper.db", "logs/execution.log", "dashboard.html", "dashboard.png", "config.json", "results/backtest_report.md", "results/backtest_report.json", "results/review.md", "results/test_results.json", "state/dashboard_url.txt", "state/shadow_breakout1h.json", "state/shadow_breakout1h.db", "logs/shadow_breakout1h.log", "state/test-breakout1h-filtered.json", "state/test-breakout1h-filtered.db", "logs/test-breakout1h-filtered.log", "state/funding-fade-4h-x1.json", "state/funding-fade-4h-x1.db", "logs/funding-fade-4h-x1.log"]:
            if os.path.exists(f): os.makedirs(os.path.join(STORE, os.path.dirname(f)), exist_ok=True); shutil.copyfile(f, os.path.join(STORE, f))
    except Exception as e: print("mirror failed", e)

def hf_portfolios():
    h = CFG.get("hf_strategy")
    if not h: return []
    v = h["version"]; return [dict(name=v, strat=h, state=f"state/{v}.json", db=f"state/{v}.db", log=f"logs/{v}.log", primary=False, role="EXPERIMENTAL")]

def post_steps():
    import subprocess
    if os.environ.get("GDM_NO_WATCHDOG"): return
    import sys as _s
    for name, cmd in (("watchdog", ["bash", "watchdog.sh"]), ("box_feed", [_s.executable, "box_feed.py"]), ("publish", ["bash", "publish.sh"])):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=200)
            out = (r.stdout.strip().splitlines() or [r.stderr.strip()[-200:]])[-1]
            print(f"  {name}:", out)
            if name == "publish": open("logs/publish.log", "a").write(f"{iso(now_ms())} rc={r.returncode} {out}\n")
        except Exception as e: print(f"  {name} failed (non-fatal)", e)

if __name__ == "__main__":
    t_start = now_ms(); errors = []; status = "OK"
    try:
        for _pf in PORTFOLIOS:
            try: main(_pf)
            except Exception as e:
                tb = traceback.format_exc(); errors.append(f"{_pf['name']}: {type(e).__name__}: {e}")
                open(_pf["log"], "a").write(f"{iso(now_ms())} ERROR trigger={trigger_source()!r} {tb}\n"); print(f"{_pf['name']} failed:", tb[-400:])
                status = "ERROR" if _pf["primary"] else ("DEGRADED" if status == "OK" else status)
    finally:
        try:
            for pf in PORTFOLIOS:
                if os.path.exists(pf["state"]) and json.load(open(pf["state"])).get("last_status") == "DEGRADED" and status == "OK": status = "DEGRADED"
        except Exception: pass
        meta = dict(last_run=iso(t_start), last_run_ms=t_start, finished=iso(now_ms()), trigger=trigger_source(), status=status, errors=errors)
        hist = json.load(open("state/run_meta.json")).get("history", []) if os.path.exists("state/run_meta.json") else []
        meta["history"] = ([dict((k, meta[k]) for k in ("last_run", "trigger", "status", "errors"))] + hist)[:50]
        json.dump(meta, open("state/run_meta.json", "w"), indent=1)
        try:
            import export; export.build(PORTFOLIOS + hf_portfolios(), CFG)
        except Exception: open("logs/execution.log", "a").write(f"{iso(now_ms())} ERROR export {traceback.format_exc()}\n"); print("export failed", traceback.format_exc()[-300:])
        post_steps()
    if status == "ERROR": raise SystemExit(1)
