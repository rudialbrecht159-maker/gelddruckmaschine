"""ONE state store + ONE export (SIMULATED paper trading only).
Store (git-versioned in the code repo, the single source of truth):
  store/sessions/<id>/{session.json,state.json,paper.db,engine.log,session.log}   Actions session engine
  store/sessions/current.json                                                     pointer to the current session
  store/box/portfolios.json                                                       hourly box portfolios (written by box_feed.py)
  store/control.json                                                              fallback control file
Export: public/data.json – built ONLY by build() from the store; bot reports, dashboard and README all read this one file.
Every writer (Actions session job, box hourly feed) calls build() after merging the latest store, so whichever commit is
newest contains a complete, consistent view."""
import json, os, sqlite3, time, datetime as dt
from zoneinfo import ZoneInfo
BASE = os.path.dirname(os.path.abspath(__file__))
ST = os.path.join(BASE, "store"); SDIR = os.path.join(ST, "sessions"); OUT = os.path.join(BASE, "public", "data.json")
BER = ZoneInfo("Europe/Berlin")
def now_iso(): return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
def _ts(s): return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()
def _j(p, d=None):
    try: return json.load(open(p))
    except Exception: return d

def cfg(): return json.load(open(os.path.join(BASE, "config.json")))

def session_summary(ss):
    """Display-bug fix: durations/strategy are computed from the session record itself (never from config/box/other sessions)."""
    end = ss.get("ended_ts") or ss.get("heartbeat_ts") or ss["started_ts"]
    return dict(id=ss["id"], status=ss["status"], status_text=ss.get("status_text"), strategy=ss["strategy"], strategy_role=ss.get("strategy_role"),
                capital_eur=ss["capital_eur"], planned_min=ss.get("minutes") or None, unlimited=not ss.get("minutes"),
                actual_min=round((end - ss["started_ts"]) / 60, 1), started=ss["started"], ended=ss.get("ended"), stop_reason=ss.get("stop_reason"),
                net_eur=(ss.get("report") or {}).get("net_pnl_eur"), trades=(ss.get("report") or {}).get("trades"), errors=ss.get("errors", 0),
                resumes=ss.get("resumes", 0), jobs=ss.get("jobs", []), stop_ack=ss.get("stop_ack"), report=ss.get("report"))

def heatmap(closes):
    hm = {}
    for t in closes:
        h = dt.datetime.fromtimestamp(_ts(t["close_ts"]), BER).hour; e = hm.setdefault(f"{t['coin']}|{h}", dict(coin=t["coin"], hour=h, w=0, l=0, net=0.0))
        e["w" if t["pnl_eur"] > 0 else "l"] += 1; e["net"] = round(e["net"] + t["pnl_eur"], 4)
    tot = len(closes); w = sum(1 for t in closes if t["pnl_eur"] > 0)
    return dict(cells=list(hm.values()), wins=w, losses=tot - w, win_pct=round(100 * w / tot, 1) if tot else None, net_eur=round(sum(t["pnl_eur"] for t in closes), 4), tz="Europe/Berlin")

def backtests(c):
    r = _j(os.path.join(BASE, "research5", "results_strategies.json"), {}) or {}
    rows = []
    for k, v in r.items():
        o = v.get("oos_taker", {})
        rows.append(dict(name=k, tf=v.get("tf"), oos=v.get("oos"), net_pct=o.get("net_pct"), pf=o.get("pf"), maxdd_pct=o.get("maxdd_pct"), trades=o.get("trades"),
                         trades_per_month=o.get("trades_per_month"), win_pct=o.get("win_pct"), dsr=o.get("dsr"), cost2x=v.get("oos_2xcost"), folds=v.get("folds"),
                         skipped_min=o.get("skipped_min"), verdict=v.get("verdict")))
    return dict(source="research5/backtest_report.md (SIMULIERT, Backtest, kein Live-Ergebnis)", rows=rows)

def build(extra_candles=None):
    c = cfg(); V = {k: v for k, v in c.get("strategy_verdicts", {}).items() if not k.startswith("_")}
    cur = _j(os.path.join(SDIR, "current.json"))
    sessions = []
    for d in sorted(os.listdir(SDIR)) if os.path.isdir(SDIR) else []:
        ss = _j(os.path.join(SDIR, d, "session.json"))
        if ss: sessions.append(ss)
    cur_ss = next((s for s in sessions if cur and s["id"] == cur["id"]), sessions[-1] if sessions else None)
    snap = _j(os.path.join(SDIR, cur_ss["id"], "snapshot.json"), {}) if cur_ss else {}
    box = _j(os.path.join(ST, "box", "portfolios.json"), {}) or {}
    ports = []
    for p in box.get("portfolios", []):
        v = V.get(p["strategy"], {}); p.update(source="box-hourly", verdict=v.get("verdict"), verdict_de=v.get("label_de"), code=v.get("code")); ports.append(p)
    if snap:
        v = V.get(cur_ss["strategy"], {}); ports.append(dict(snap, source="session", role="SESSION", verdict=v.get("verdict"), verdict_de=v.get("label_de"), code=v.get("code")))
    closes = []
    for p in box.get("portfolios", []):
        for t in p.get("trade_history", []): closes.append(dict(t, portfolio=p["id"], source="box-hourly"))
    for ss in sessions:
        sp = _j(os.path.join(SDIR, ss["id"], "snapshot.json"), {}) or {}
        for t in sp.get("trade_history", []): closes.append(dict(t, portfolio=f"session-{ss['id']}", source="session", session_capital=ss["capital_eur"]))
    closes.sort(key=lambda t: t["close_ts"], reverse=True)
    alerts = []
    if cur_ss:
        alerts += [dict(a, scope="session") for a in cur_ss.get("alerts", [])]
    for p in ports:
        if p.get("halted"): alerts.append(dict(level="red", scope=p["id"], ts=p.get("last_cycle"), text=f"Limit erreicht: {p.get('halt_reason')} – keine neuen Einstiege"))
        if p.get("phase_action") == "pause": alerts.append(dict(level="orange", scope=p["id"], ts=p.get("last_cycle"), text=f"Phasen-PAUSE: {(p.get('phase') or {}).get('recommendation')}"))
    rm = box.get("run_meta") or {}
    health = dict(now=now_iso(),
                  session=dict(heartbeat=cur_ss.get("heartbeat") if cur_ss else None, last_data=cur_ss.get("last_data") if cur_ss else None,
                               status=cur_ss["status"] if cur_ss else None, host=cur_ss.get("host") if cur_ss else None, ok_max_age_s=180),
                  box=dict(last_run=rm.get("last_run"), status=rm.get("status"), last_data=max([p.get("last_data_ok") or "" for p in box.get("portfolios", [])] or [""]) or None,
                           hf_heartbeat=(box.get("hf") or {}).get("ts"), ok_max_age_s=2 * 3600, exported=box.get("exported")))
    old = _j(OUT, {}) or {}
    candles = extra_candles or old.get("candles") or {}
    ph = [dict(portfolio=p["id"], strategy=p["strategy"], verdict_de=p.get("verdict_de"), **(p.get("phase") or {})) for p in ports if p.get("phase")]
    out = dict(simulated=True, label="PAPER TRADING · SIMULATION – virtuelles Geld, echte Hyperliquid-Marktdaten, keine echten Orders",
               generated=now_iso(), schema=2,
               config=dict(session={k: v for k, v in c["session"].items() if not k.startswith("_")}, leverage_cap=c.get("leverage_cap", 3), leverage_hard_max=c.get("leverage_hard_max", 5),
                           risk=dict(risk_per_trade=c["risk_per_trade"], daily_loss_stop=c["daily_loss_stop"], max_drawdown_halt=c["max_drawdown_halt"], max_positions=c["max_positions"], min_notional_usd=10),
                           verdicts=V),
               health=health, alerts=alerts, session=dict(cur_ss and session_summary(cur_ss) or {}, portfolio=snap or None, log=(cur_ss or {}).get("log_tail", [])),
               sessions=[session_summary(s) for s in sessions[::-1][:30]], portfolios=ports, closes=closes[:200], heatmap=heatmap(closes),
               backtests=backtests(c), phases=ph, candles=candles)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT + ".tmp", "w"), separators=(",", ":"), ensure_ascii=False); os.replace(OUT + ".tmp", OUT)
    return out

if __name__ == "__main__":
    o = build(); print("data.json", os.path.getsize(OUT), "bytes; sessions", len(o["sessions"]), "portfolios", len(o["portfolios"]), "closes", len(o["closes"]))
