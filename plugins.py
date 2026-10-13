"""Plug-in point (research5 / later research rounds). Nothing here changes risk limits.
- Strategy modules (config.plugins.strategy_modules): module with STRATEGIES = {version: dict(name, tf, params, fn, [adapter, history_bars, role, verdict])}
  -> registered into strategies.STRATS and selectable in sessions if listed in config.session.strategies.
- Phase module (config.plugins.phases_module): exposes evaluate(trades, equity, start_ts, start_equity, ...) (research5/phases.py).
Missing modules are ignored (logged), so the engine never breaks because research code is absent."""
import importlib, json, os
BASE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(BASE, "config.json")))

def load_strategy_plugins(STRATS):
    extra = {}
    for m in CFG.get("plugins", {}).get("strategy_modules", []):
        try: mod = importlib.import_module(m)
        except Exception as e: continue   # not present -> fine
        for v, d in getattr(mod, "STRATEGIES", {}).items():
            STRATS.setdefault(d["name"], d["fn"]); extra[v] = {k: x for k, x in d.items() if k != "fn"} | {"version": v}
    return extra

def _phases():
    try: return importlib.import_module(CFG.get("plugins", {}).get("phases_module", "research5.phases"))
    except Exception: return None

def phase_eval(con, start_ts, start_equity):
    """Run research5 phase evaluator on a portfolio's own trades/equity (real logged data). Returns dict or None."""
    ph = _phases()
    if not ph: return None
    trs = [dict(t_out=r[0], net=r[1], coin=r[2], strategy=r[3], exit_reason=r[4], fees=r[5], funding=r[6], gross=r[1] + r[5] + r[6])
           for r in con.execute("select close_ts, pnl_eur, coin, strategy, reason, fees_eur, funding_eur from trades")]
    eq = [dict(t=r[0], equity=r[1]) for r in con.execute("select ts, equity_eur from equity")]
    r = ph.evaluate(trs, eq, start_ts, start_equity=start_equity)
    # Decision (docs/DECISIONS.md): pass rules unchanged; low-frequency strategies with <30 trades are shown as
    # 'unentschieden/verlängern' (INCONCLUSIVE), never as passed.
    r["label_de"] = {"pause": "PAUSE (Phase nicht bestanden)", "extend": "UNENTSCHIEDEN / VERLÄNGERN", "continue": "WEITER"}[r["action"]]
    return r
