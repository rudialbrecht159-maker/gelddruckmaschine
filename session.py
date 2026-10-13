"""GELDDRUCKMASCHINE Trading Session Mode (SIMULATED paper trading only, never real orders).
A session = separate paper portfolio with user-chosen virtual capital + duration, running ONE existing strategy through the
same engine and limits as cycle.py (1% risk, 3% daily stop, 10% DD halt, max 2 positions, 3x cap, $10 min).
Loop every 60 s: control check -> engine (stops/exits/funding/signals/entries) -> state + public/session.json.
STOP / timeout: no new entries, open positions managed by normal exits (stops stay) -> auto-end when flat -> final report.
close_all: emergency close all open positions at market (mid + costs), then end.
Usage:
  start : python session.py start --capital 50 --minutes 10 --strategy breakout-1h-v1 [--publish] [--control-cmd CMD]
  stop  : python session.py stop            (writes control file; graceful)
  kill  : python session.py close_all       (emergency close at market)
  resume: python session.py resume          (crash recovery: continues current session from saved state)
Control can also come from --control-cmd (stdout JSON {"action": "stop"|"close_all"|"none"}), e.g. reading a committed file in Actions."""
import argparse, json, os, sys, time, fcntl, subprocess, traceback, datetime as dt
BASE = os.path.dirname(os.path.abspath(__file__)); os.chdir(BASE); sys.path.insert(0, BASE)
SDIR = "sessions"; CUR = f"{SDIR}/current.json"; CTRL = f"{SDIR}/control.json"; LOCK = f"{SDIR}/session.lock"
STATUS_STOP = "Beenden – offene Positionen werden verwaltet"
iso = lambda t=None: dt.datetime.fromtimestamp(t if t is not None else time.time(), dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

def strategies(CFG):
    out = {CFG["active_strategy"]["version"]: dict(CFG["active_strategy"], _role="ACTIVE (validated OOS, weak)"),
           CFG["shadow_strategy"]["version"]: dict(CFG["shadow_strategy"], _role="SHADOW (robust family, short OOS)")}
    for t in CFG.get("test_strategies", []): out[t["version"]] = dict(t, _role=t.get("role", "TEST"))
    if CFG.get("hf_strategy"): out[CFG["hf_strategy"]["version"]] = dict(CFG["hf_strategy"], _role="EXPERIMENTAL (backtest negative)")
    return out

def pf_for(ss):
    import cycle
    st = strategies(cycle.CFG)[ss["strategy"]]
    if st.get("module"):   # hf plug-in style
        import importlib; fn = getattr(importlib.import_module(st["module"]), st["func"]); cycle.STRATS[st["name"]] = fn
    d = f"{SDIR}/{ss['id']}"
    return dict(name=f"session-{ss['id']}", strat={k: v for k, v in st.items() if not k.startswith("_")}, state=f"{d}/state.json", db=f"{d}/paper.db",
                log=f"{d}/engine.log", primary=False, role="SESSION", start_balance=ss["capital_eur"])

def save(ss):
    json.dump(ss, open(f"{SDIR}/{ss['id']}/session.json.tmp", "w"), indent=1); os.replace(f"{SDIR}/{ss['id']}/session.json.tmp", f"{SDIR}/{ss['id']}/session.json")
    json.dump(dict(id=ss["id"], status=ss["status"]), open(CUR, "w"))

def slog(ss, msg):
    with open(f"{SDIR}/{ss['id']}/session.log", "a") as f: f.write(f"{iso()} {msg}\n")

def read_control(args, ss):
    """Control = {"action","ts"}; ignored unless issued at/after this session's start (stale files from old sessions never act)."""
    cands = []
    if os.path.exists(CTRL):
        try: cands.append(json.load(open(CTRL)))
        except Exception: pass
    if args.control_cmd:
        try: cands.append(json.loads(subprocess.run(args.control_cmd, shell=True, capture_output=True, text=True, timeout=30).stdout or "{}"))
        except Exception as e: print("control-cmd failed", e)
    acts = [c.get("action") for c in cands if c.get("action") in ("stop", "close_all") and str(c.get("ts", "")).replace("T", " ")[:19] >= ss["started"][:19]]
    return "close_all" if "close_all" in acts else ("stop" if acts else None)

def snapshot(ss, pf):
    """Build public session view from the engine's own state/db (real logged data only)."""
    import export, cycle
    cfg = dict(cycle.CFG, start_balance_eur=ss["capital_eur"])
    if not os.path.exists(pf["state"]): return {}
    p = export.pstats(pf, cfg); logs = p.pop("_logs", [])
    p["feed"] = [dict(ts=ts, status=stt, **json.loads(m)) for ts, stt, m in logs[:30]]
    return p

def report(ss, snap):
    tr = snap.get("trade_history", [])
    return dict(start_capital_eur=ss["capital_eur"], end_capital_eur=snap.get("equity_eur"), net_pnl_eur=round(snap.get("equity_eur", ss["capital_eur"]) - ss["capital_eur"], 4),
                return_pct=round((snap.get("equity_eur", ss["capital_eur"]) / ss["capital_eur"] - 1) * 100, 4), trades=len(tr),
                wins=sum(1 for t in tr if t["pnl_eur"] > 0), gross_pnl_eur=round(sum(t["gross_eur"] for t in tr), 4), fees_eur=snap.get("fees_eur"), funding_eur=snap.get("funding_eur"),
                planned_minutes=ss["minutes"], actual_minutes=round((time.time() - ss["started_ts"]) / 60, 1), started=ss["started"], ended=iso(),
                stop_reason=ss.get("stop_reason"), loops=ss["loops"], market_evaluations=snap.get("evals", {}).get("market_evaluations"),
                rejected_or_no_entry=len(snap.get("rejected", [])), engine_errors=ss["errors"], strategy=ss["strategy"], simulated=True)

def publish(ss, snap, force=False):
    pub = dict(simulated=True, disclaimer="SIMULATED paper-trading session with virtual money only.", generated=iso(), session={k: v for k, v in ss.items() if k not in ("pid",)}, portfolio=snap)
    os.makedirs("public", exist_ok=True); json.dump(pub, open("public/session.json.tmp", "w"), separators=(",", ":")); os.replace("public/session.json.tmp", "public/session.json")
    if ss.get("publish") and (force or time.time() - ss.get("last_pub_ts", 0) >= ss.get("publish_every_s", 300)):
        ss["last_pub_ts"] = time.time()
        r = subprocess.run(["bash", "publish.sh", "session"], capture_output=True, text=True, timeout=120)
        out = (r.stdout.strip().splitlines() or [""])[-1]; open("logs/publish.log", "a").write(f"{iso()} [session] {out}\n")

def run(ss, args):
    lockf = open(LOCK, "w")
    try: fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError: print("another session process holds the lock -> exit"); return 2
    import cycle
    pf = pf_for(ss); ss["pid"] = os.getpid(); slog(ss, f"RUN pid={os.getpid()} status={ss['status']} (resume={ss['loops'] > 0})")
    while True:
        t0 = time.time(); ss["loops"] += 1; ss["last_loop"] = iso(t0); ss["heartbeat_ts"] = t0
        act = read_control(args, ss); event = False
        if ss["status"] == "running":
            if act in ("stop", "close_all"): ss.update(status="stopping", stop_reason=f"user {act}", stop_requested=iso()); event = True
            elif t0 >= ss["ends_ts"]: ss.update(status="stopping", stop_reason="timeout", stop_requested=iso()); event = True
        if ss["status"] == "stopping" and act == "close_all" and not ss.get("force_close"): ss["force_close"] = True; event = True
        if event: slog(ss, f"STATE -> {ss['status']} ({ss.get('stop_reason')}){' FORCE CLOSE' if ss.get('force_close') else ''}")
        pf.update(no_entries=ss["status"] != "running", no_entries_reason=f"session {STATUS_STOP}", force_close=bool(ss.get("force_close")))
        ss["status_text"] = {"running": "Läuft – Analyse aktiv", "stopping": STATUS_STOP}.get(ss["status"], ss["status"])
        try:
            n0 = len(json.load(open(pf["state"]))["positions"]) if os.path.exists(pf["state"]) else 0
            cycle.main(pf)
            st = json.load(open(pf["state"])); n1 = len(st["positions"])
            if n1 != n0 or st["last_actions"]: event = True; slog(ss, f"ACTIONS {st['last_actions']}")
            if st["last_problems"]: slog(ss, f"DATA PROBLEMS {st['last_problems']} -> no new entries this loop")
        except Exception as e:
            ss["errors"] += 1; slog(ss, f"ENGINE ERROR {type(e).__name__}: {e}"); open(pf["log"], "a").write(f"{iso()} ERROR {traceback.format_exc()}\n"); st = None
        snap = snapshot(ss, pf)
        if ss["status"] == "stopping" and st is not None and not st["positions"]:
            ss.update(status="ended", status_text="Beendet", ended=iso()); ss["report"] = report(ss, snap); event = True
            slog(ss, f"ENDED report={json.dumps(ss['report'])}")
        save(ss); publish(ss, snap, force=event)
        if ss["status"] == "ended":
            if os.path.exists(CTRL): os.remove(CTRL)
            return 0
        time.sleep(max(1, args.loop_s - (time.time() - t0)))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["start", "stop", "close_all", "resume", "status"])
    ap.add_argument("--capital", type=float, default=50.0); ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--strategy", default="breakout-1h-v1"); ap.add_argument("--publish", action="store_true")
    ap.add_argument("--control-cmd", default=None); ap.add_argument("--loop-s", type=float, default=60)
    a = ap.parse_args(); os.makedirs(SDIR, exist_ok=True)
    cur = json.load(open(CUR)) if os.path.exists(CUR) else None
    if a.cmd in ("stop", "close_all"):
        json.dump(dict(action=a.cmd, ts=iso(), by="box"), open(CTRL, "w")); print("control written:", a.cmd); return 0
    if a.cmd == "status":
        print(json.dumps(json.load(open(f"{SDIR}/{cur['id']}/session.json")) if cur else {}, indent=1)[:3000]); return 0
    if a.cmd == "resume":
        if not cur or cur["status"] == "ended": print("no session to resume"); return 0
        ss = json.load(open(f"{SDIR}/{cur['id']}/session.json")); ss["resumes"] = ss.get("resumes", 0) + 1; return run(ss, a)
    # start
    if cur and cur["status"] != "ended": print(f"session {cur['id']} still {cur['status']} -> refuse (one session at a time)"); return 3
    import cycle
    if a.strategy not in strategies(cycle.CFG): print("unknown strategy; choose:", list(strategies(cycle.CFG))); return 4
    if not (1 <= a.minutes <= 1440): print("duration must be 1 min .. 24 h"); return 5
    if a.capital <= 0: print("capital must be > 0"); return 6
    if os.path.exists(CTRL): os.remove(CTRL)
    now = time.time(); sid = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    os.makedirs(f"{SDIR}/{sid}", exist_ok=True)
    s = strategies(cycle.CFG)[a.strategy]
    ss = dict(id=sid, capital_eur=a.capital, minutes=a.minutes, strategy=a.strategy, strategy_role=s["_role"], strategy_tf=s["tf"], status="running",
              started=iso(now), started_ts=now, ends_at=iso(now + a.minutes * 60), ends_ts=now + a.minutes * 60, loops=0, errors=0, resumes=0,
              publish=a.publish, publish_every_s=300, host=os.environ.get("GDM_HOST", "box"),
              limits=dict(risk_per_trade=0.01, daily_loss_stop=0.03, max_drawdown_halt=0.10, max_positions=2, max_leverage=3, min_notional_usd=10))
    save(ss); slog(ss, f"START capital=€{a.capital} minutes={a.minutes} strategy={a.strategy}"); return run(ss, a)

if __name__ == "__main__":
    sys.exit(main())
