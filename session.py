"""GELDDRUCKMASCHINE Trading Session engine (SIMULATED paper trading only – virtual money, public data, never real orders).
One session = separate paper portfolio (virtual capital, one strategy) run through the SAME engine/limits as cycle.py.
Loop: market tick every loop_s (60 s); between ticks the control channel is polled every control_poll_s (5 s).
Control channel (fastest secure path): the dispatch of the `trading-session` workflow itself. Its run-name encodes the action
("stop", "close_all CONFIRMED"), so the engine sees a STOP as soon as GitHub has created the run (no runner start needed).
Read-only GitHub API call with the job's GITHUB_TOKEN (actions: read). Fallback: store/control.json (committed by the control job / box).
STOP/timeout/limit breach: no new entries, open positions managed by their normal exits (stops stay) -> auto-end when flat.
close_all: emergency close at market, then end.  Job budget reached: state saved, status 'paused' -> next START resumes.
Usage: python session.py start --capital 200 --minutes 15 --strategy funding-fade-4h-x1 [--sync]
       python session.py stop | close_all | resume | status"""
import argparse, json, os, sys, time, fcntl, subprocess, traceback, threading, urllib.request, datetime as dt
BASE = os.path.dirname(os.path.abspath(__file__)); os.chdir(BASE); sys.path.insert(0, BASE)
os.environ.setdefault("GDM_TRIGGER", "session")
SDIR = "store/sessions"; CUR = f"{SDIR}/current.json"; CTRL = "store/control.json"; LOCK = f"{SDIR}/session.lock"
CFGJ = json.load(open("config.json")); SC = CFGJ["session"]
STATUS_TXT = {"running": "Läuft – Analyse aktiv", "stopping": "Beenden – offene Positionen werden verwaltet", "ended": "Beendet",
              "paused": "Pausiert – GitHub-Job-Limit erreicht, START setzt fort"}
iso = lambda t=None: dt.datetime.fromtimestamp(t if t is not None else time.time(), dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
def pts(s): return dt.datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T")).timestamp()

def strategies():
    import cycle, plugins
    allv = {CFGJ["active_strategy"]["version"]: CFGJ["active_strategy"], CFGJ["shadow_strategy"]["version"]: CFGJ["shadow_strategy"]}
    for t in CFGJ.get("test_strategies", []): allv[t["version"]] = t
    if CFGJ.get("hf_strategy"): allv[CFGJ["hf_strategy"]["version"]] = CFGJ["hf_strategy"]
    allv.update(plugins.load_strategy_plugins(cycle.STRATS))
    return {v: allv[v] for v in SC["strategies"] if v in allv}   # only the configured session set is selectable

def pf_for(ss):
    import cycle
    st = strategies()[ss["strategy"]]
    if st.get("module"):
        import importlib; cycle.STRATS[st["name"]] = getattr(importlib.import_module(st["module"]), st["func"])
    d = f"{SDIR}/{ss['id']}"
    return dict(name=f"session-{ss['id']}", strat=st, state=f"{d}/state.json", db=f"{d}/paper.db", log=f"{d}/engine.log", primary=False, role="SESSION", start_balance=ss["capital_eur"])

def save(ss):
    p = f"{SDIR}/{ss['id']}/session.json"; json.dump(ss, open(p + ".tmp", "w"), indent=1); os.replace(p + ".tmp", p)
    json.dump(dict(id=ss["id"], status=ss["status"]), open(CUR, "w"))

def slog(ss, msg):
    line = f"{iso()} {msg}"
    with open(f"{SDIR}/{ss['id']}/session.log", "a") as f: f.write(line + "\n")
    ss.setdefault("log_tail", []).append(line[:400]); ss["log_tail"] = ss["log_tail"][-40:]; print(line, flush=True)

# ---------------- control channel ----------------
class Control:
    def __init__(s, ss):
        s.repo, s.tok = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN"); s.etag = None; s.cache = []; s.ss = ss
        s.calls = 0; s.errors = 0
    def runs(s):
        if not (s.repo and s.tok): return []
        rq = urllib.request.Request(f"https://api.github.com/repos/{s.repo}/actions/workflows/session.yml/runs?event=workflow_dispatch&per_page=10",
                                    headers={"Authorization": f"Bearer {s.tok}", "Accept": "application/vnd.github+json", **({"If-None-Match": s.etag} if s.etag else {})})
        s.calls += 1
        try:
            with urllib.request.urlopen(rq, timeout=8) as r: s.etag = r.headers.get("ETag"); s.cache = json.load(r)["workflow_runs"]
        except urllib.error.HTTPError as e:
            if e.code != 304: s.errors += 1
        except Exception: s.errors += 1
        return s.cache
    def poll(s):
        """-> (action, info) for the strongest valid command issued after session start, else (None, None)."""
        st0 = s.ss["started_ts"]; found = []
        for r in s.runs():
            t = r.get("display_title", ""); ts = pts(r["created_at"])
            if ts + 1 < st0 or str(r["id"]) == os.environ.get("GITHUB_RUN_ID"): continue
            a = "close_all" if t.startswith("close_all CONFIRMED") else "stop" if t.startswith("stop") else None
            if a: found.append((a, dict(source="workflow_dispatch", run_id=r["id"], dispatched=iso(ts), dispatched_ts=ts, url=r.get("html_url"))))
        try:
            c = json.load(open(CTRL))
            if c.get("action") in ("stop", "close_all") and pts(c["ts"]) >= st0 - 1: found.append((c["action"], dict(source="control-file", dispatched=iso(pts(c["ts"])), dispatched_ts=pts(c["ts"]))))
        except Exception: pass
        if not found: return None, None
        found.sort(key=lambda x: (x[0] != "close_all", x[1]["dispatched_ts"]))
        return found[0]

# ---------------- sync (Actions: commit store + data.json) ----------------
SYNC_LOCK = threading.Lock()
def sync(msg, wait=False):
    if not os.environ.get("GDM_SYNC"): return
    def _run():
        with SYNC_LOCK: subprocess.run(["bash", "sync.sh", msg], capture_output=True, text=True, timeout=120)
    th = threading.Thread(target=_run, daemon=True); th.start()
    if wait: th.join(130)

def snapshot(ss, pf):
    import export, cycle
    if not os.path.exists(pf["state"]): return {}
    p = export.pstats(pf, dict(cycle.CFG, start_balance_eur=ss["capital_eur"])); logs = p.pop("_logs", [])
    p["feed"] = [dict(ts=ts, status=stt, **json.loads(m)) for ts, stt, m in logs[:30]]
    json.dump(p, open(f"{SDIR}/{ss['id']}/snapshot.json", "w"), separators=(",", ":"))
    return p

def candles(ss):
    tf = strategies()[ss["strategy"]]["tf"]
    try: d = json.load(open(f"state/candles_{tf}.json")); return dict(tf=tf, fetched=d.get("_fetched"), coins={k: v[-150:] for k, v in d.items() if not k.startswith("_")})
    except Exception: return None

def export_all(ss, pf):
    import store; snapshot(ss, pf); store.build(extra_candles=candles(ss))

def report(ss, snap):
    tr = snap.get("trade_history", []); eq = snap.get("equity_eur", ss["capital_eur"])
    return dict(start_capital_eur=ss["capital_eur"], end_capital_eur=eq, net_pnl_eur=round(eq - ss["capital_eur"], 4), return_pct=round((eq / ss["capital_eur"] - 1) * 100, 4),
                trades=len(tr), wins=sum(1 for t in tr if t["pnl_eur"] > 0), gross_pnl_eur=round(sum(t["gross_eur"] for t in tr), 4), fees_eur=snap.get("fees_eur"),
                funding_eur=snap.get("funding_eur"), planned_minutes=ss["minutes"] or "unbegrenzt", actual_minutes=round((time.time() - ss["started_ts"]) / 60, 1),
                started=ss["started"], ended=iso(), stop_reason=ss.get("stop_reason"), loops=ss["loops"], market_evaluations=snap.get("evals", {}).get("market_evaluations"),
                min_order_skips=snap.get("min_order_skips_total", 0), engine_errors=ss["errors"], resumes=ss.get("resumes", 0), jobs=len(ss.get("jobs", [])),
                stop_ack=ss.get("stop_ack"), strategy=ss["strategy"], simulated=True)

def tick(ss, pf, cfgd):
    import cycle, hl
    ss["loops"] += 1; ss["last_loop"] = iso()
    pf.update(no_entries=ss["status"] != "running", no_entries_reason=f"session {STATUS_TXT['stopping']}", force_close=bool(ss.get("force_close")))
    st = None
    try:
        n0 = len(json.load(open(pf["state"]))["positions"]) if os.path.exists(pf["state"]) else 0
        cycle.main(pf); st = json.load(open(pf["state"]))
        if hl.LAST_OK["ts"]: ss["last_data"] = iso(hl.LAST_OK["ts"])
        if len(st["positions"]) != n0 or st["last_actions"]: slog(ss, f"ACTIONS {st['last_actions']}")
        if st["last_problems"]: slog(ss, f"DATA PROBLEMS {st['last_problems']} -> no new entries this loop")
        r = st.get("risk", {}); why = None
        if st.get("halted"): why = f"Max-Drawdown-Limit: {st['halt_reason']}"
        elif r.get("daily_loss", 0) >= cfgd["daily_loss_stop"]: why = f"Tagesverlust-Limit {r['daily_loss']:.1%} ≥ {cfgd['daily_loss_stop']:.0%}"
        if why and ss["status"] == "running":
            ss.update(status="stopping", stop_reason=f"limit: {why}", stop_requested=iso())
            ss.setdefault("alerts", []).append(dict(level="red", ts=iso(), text=f"Limit verletzt – Bot automatisch gestoppt: {why}")); slog(ss, f"LIMIT BREACH -> stopping ({why})")
    except Exception as e:
        ss["errors"] += 1; slog(ss, f"ENGINE ERROR {type(e).__name__}: {e}"); open(pf["log"], "a").write(f"{iso()} ERROR {traceback.format_exc()}\n")
    return st

def run(ss, a):
    lockf = open(LOCK, "w")
    try: fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError: print("another session process holds the lock -> exit"); return 2
    import cycle
    pf = pf_for(ss); ctl = Control(ss); job0 = time.time(); budget = float(os.environ.get("GDM_JOB_BUDGET_MIN", SC["job_budget_min"])) * 60
    ss.setdefault("jobs", []).append(dict(run_id=os.environ.get("GITHUB_RUN_ID", "local"), host=os.environ.get("GDM_HOST", "box"), started=iso(job0)))
    if ss["status"] == "paused": ss["status"] = ss.pop("paused_from", "running")
    slog(ss, f"RUN job={ss['jobs'][-1]['run_id']} status={ss['status']} resume={ss['loops'] > 0}")
    next_tick = 0; last_sync = 0; seen = None
    while True:
        now = time.time(); ss["heartbeat"] = iso(now); ss["heartbeat_ts"] = now
        act, info = ctl.poll(); event = False
        if act and (act, info.get("run_id"), info.get("dispatched")) != seen:
            seen = (act, info.get("run_id"), info.get("dispatched"))
            if not ss.get("stop_ack") or (act == "close_all" and ss["stop_ack"]["action"] != "close_all"):
                ss["stop_ack"] = dict(action=act, acked=iso(now), latency_s=round(now - info["dispatched_ts"], 1), **{k: v for k, v in info.items() if k != "dispatched_ts"})
                slog(ss, f"CONTROL {act} acknowledged {ss['stop_ack']['latency_s']} s after dispatch ({info['source']})")
            if ss["status"] == "running": ss.update(status="stopping", stop_reason=f"user {act}", stop_requested=iso(now)); event = True
            if act == "close_all" and not ss.get("force_close"): ss["force_close"] = True; event = True
        if ss["status"] == "running" and ss.get("ends_ts") and now >= ss["ends_ts"]:
            ss.update(status="stopping", stop_reason="timeout", stop_requested=iso(now)); event = True
        ss["status_text"] = STATUS_TXT.get(ss["status"], ss["status"]); ss["control_api"] = dict(calls=ctl.calls, errors=ctl.errors, poll_s=a.poll_s)
        if event:
            slog(ss, f"STATE -> {ss['status']} ({ss.get('stop_reason')}){' FORCE CLOSE' if ss.get('force_close') else ''}")
            save(ss); export_all(ss, pf) if os.path.exists(pf["state"]) else None; sync(f"session {ss['status']} {iso()[11:19]} (SIMULATED)")
        if event and ss.get("force_close") or now >= next_tick:
            next_tick = now + a.loop_s; st = tick(ss, pf, cycle.CFG)
            if ss["status"] == "stopping" and st is not None and not st["positions"]:
                snap = snapshot(ss, pf); ss.update(status="ended", status_text="Beendet", ended=iso(), ended_ts=time.time()); ss["report"] = report(ss, snap)
                slog(ss, f"ENDED report={json.dumps(ss['report'])}")
            save(ss); export_all(ss, pf)
            if ss["status"] == "ended":
                if os.path.exists(CTRL): os.remove(CTRL)
                sync(f"session ended {iso()[11:19]} (SIMULATED)", wait=True); return 0
            if time.time() - last_sync >= SC["sync_every_s"] or event: last_sync = time.time(); sync(f"session state {iso()[11:19]} (SIMULATED)")
        if time.time() - job0 >= budget:
            ss.update(paused_from=ss["status"], status="paused", status_text=STATUS_TXT["paused"]); slog(ss, f"JOB BUDGET {budget/60:.0f} min reached -> paused (state saved; START/resume continues)")
            save(ss); export_all(ss, pf); sync(f"session paused {iso()[11:19]} (SIMULATED)", wait=True); return 10
        time.sleep(max(0.5, min(a.poll_s, next_tick - time.time())))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["start", "stop", "close_all", "resume", "status"])
    ap.add_argument("--capital", type=float, default=SC["capital_eur"]); ap.add_argument("--minutes", type=float, default=SC["duration_min"])
    ap.add_argument("--strategy", default=SC["strategy"]); ap.add_argument("--loop-s", type=float, default=SC["loop_s"]); ap.add_argument("--poll-s", type=float, default=SC["control_poll_s"])
    a = ap.parse_args(); os.makedirs(SDIR, exist_ok=True)
    cur = json.load(open(CUR)) if os.path.exists(CUR) else None
    if a.cmd in ("stop", "close_all"):
        json.dump(dict(action=a.cmd, ts=iso(), by="box"), open(CTRL, "w")); print("control written:", a.cmd); return 0
    if a.cmd == "status":
        print(json.dumps(json.load(open(f"{SDIR}/{cur['id']}/session.json")) if cur else {}, indent=1)[:3000]); return 0
    if a.cmd == "resume" or (cur and cur["status"] in ("running", "stopping", "paused")):
        if not cur or cur["status"] == "ended": print("no session to resume"); return 0
        ss = json.load(open(f"{SDIR}/{cur['id']}/session.json")); ss["resumes"] = ss.get("resumes", 0) + 1
        if a.cmd == "start": print(f"unfinished session {cur['id']} ({cur['status']}) -> resuming it; new start inputs ignored")
        return run(ss, a)
    if a.strategy not in strategies(): print("unknown strategy; choose:", list(strategies())); return 4
    if not (a.minutes == 0 or 1 <= a.minutes <= 1440): print("duration must be 0 (unbegrenzt) or 1..1440 min"); return 5
    if a.capital <= 0: print("capital must be > 0"); return 6
    if os.path.exists(CTRL): os.remove(CTRL)
    now = time.time(); sid = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S"); os.makedirs(f"{SDIR}/{sid}", exist_ok=True)
    s = strategies()[a.strategy]; v = CFGJ.get("strategy_verdicts", {}).get(a.strategy, {})
    ss = dict(id=sid, capital_eur=a.capital, minutes=a.minutes or 0, strategy=a.strategy, strategy_role=v.get("label_de", s.get("role", "")), strategy_tf=s["tf"], status="running",
              started=iso(now), started_ts=now, ends_at=iso(now + a.minutes * 60) if a.minutes else None, ends_ts=now + a.minutes * 60 if a.minutes else None,
              loops=0, errors=0, resumes=0, host=os.environ.get("GDM_HOST", "box"), alerts=[],
              limits=dict(risk_per_trade=CFGJ["risk_per_trade"], daily_loss_stop=CFGJ["daily_loss_stop"], max_drawdown_halt=CFGJ["max_drawdown_halt"],
                          max_positions=CFGJ["max_positions"], leverage_cap=__import__("sim").MAX_LEV, min_notional_usd=10))
    save(ss); slog(ss, f"START capital=€{a.capital} minutes={a.minutes or 'unbegrenzt'} strategy={a.strategy}"); return run(ss, a)

if __name__ == "__main__":
    sys.exit(main())
