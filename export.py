"""Exports SAFE public data (no paths/tokens) to public/data.json + copies web/index.html. SIMULATED data only."""
import json, os, re, sqlite3, shutil, datetime as dt
from zoneinfo import ZoneInfo
BER = ZoneInfo("Europe/Berlin")
def next_run(now):
    b = now.astimezone(BER).replace(second=0, microsecond=0)
    n = b.replace(minute=7)
    if n <= b: n += dt.timedelta(hours=1)
    return n.astimezone(dt.timezone.utc)
EXIT_RULES = {"trend": "stop 3×ATR, or exit when EMA trend flips (closed 4h bar)", "breakout": "stop ATR-based, or exit on opposite Donchian exit-channel break (closed bar)",
    "breakout1h_filtered": "stop 2×ATR, or opposite 24-bar channel break (closed 1h bar)", "funding_fade_trend": "stop ATR-based, exit when 4h trend flips or time exit after max hold (closed 4h bar)",
    "zscore5m": "stop 2×ATR, or exit when z-score crosses 0 (closed 5m bar)"}
def pstats(pf, cfg):
    st = json.load(open(pf["state"])); con = sqlite3.connect(pf["db"]); start = cfg["start_balance_eur"]
    eq = con.execute("select ts, equity_eur from equity order by rowid").fetchall()
    tr = [dict(zip(("coin","side","strategy","open_ts","close_ts","entry","exit","qty","notional_usd","lev","fees_eur","funding_eur","pnl_eur","reason"), r))
          for r in con.execute("select coin,side,strategy,open_ts,close_ts,entry,exit,qty,notional_usd,lev,fees_eur,funding_eur,pnl_eur,reason from trades order by id")]
    for t in tr:
        t["gross_eur"] = round(t["pnl_eur"] + t["fees_eur"] + t["funding_eur"], 4)
        t["hold_min"] = round((dt.datetime.strptime(t["close_ts"], "%Y-%m-%d %H:%M:%SZ") - dt.datetime.strptime(t["open_ts"], "%Y-%m-%d %H:%M:%SZ")).total_seconds() / 60, 1)
    peak, mdd = start, 0.0
    for _, v in eq: peak = max(peak, v); mdd = max(mdd, 1 - v / peak)
    w = [t for t in tr if t["pnl_eur"] > 0]; gl = -sum(t["pnl_eur"] for t in tr if t["pnl_eur"] <= 0)
    logs = con.execute("select ts, status, msg from exec_log order by rowid desc limit 60").fetchall()
    n_runs, n_ev, last_ev, rejected = 0, 0, None, []
    for ts, _, msg in con.execute("select ts, status, msg from exec_log order by rowid"):
        m = json.loads(msg); n_runs += 1; n_ev += len(m["signals"]); last_ev = ts
        for c, s in m["signals"].items():
            if "BLOCKED" in s: rejected.append(dict(ts=ts, coin=c, kind="rejected: blocked", reason=s.split("BLOCKED:", 1)[1].strip(), text=s.split(" BLOCKED")[0]))
            elif "already processed" in s: continue
            elif "no entry" in s:
                mm = re.search(r"\[(.*)\]", s); rejected.append(dict(ts=ts, coin=c, kind="rejected: no entry", reason=mm.group(1) if mm else "entry condition not met on new closed bar", text=s))
            elif "entry" in s: rejected.append(dict(ts=ts, coin=c, kind="ACCEPTED", reason="valid signal, risk checks passed", text=s))
        for a in m["actions"]:
            if a.startswith("SKIPPED"): rejected.append(dict(ts=ts, coin=a.split()[1].strip(":"), kind="rejected: skipped", reason=a, text=a))
    s = pf["strat"]
    pos = [dict(coin=k, side="LONG" if p["side"] > 0 else "SHORT", entry=p["entry"], mark=p.get("mark"), stop=p["stop"], liq=p["liq"], qty=p["qty"],
                notional_usd=round(p["notional_usd"], 2), lev=p["lev"], upnl_eur=round(p.get("upnl_eur", 0), 4), fees_eur=round(p["fees_eur"], 4),
                funding_eur=round(p["funding_eur"], 4), risk_eur=round(p.get("risk_eur", 0), 4),
                stop_loss_eur=round(abs(p["entry"] - p["stop"]) * p["qty"] / (st.get("fx_eurusd") or 1.12), 4),
                est_exit_cost_eur=round(p["notional_usd"] / (st.get("fx_eurusd") or 1.12) * (0.00045 + 0.0003 + 0.0001), 4),
                exit_rule=EXIT_RULES.get(pf["strat"]["name"], "strategy stop / signal exit"), open_ts=dt.datetime.fromtimestamp(p["open_ts"]/1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")) for k, p in st["positions"].items()]
    return dict(id=pf["name"], role=pf.get("role") or ("ACTIVE" if pf["primary"] else "SHADOW"), strategy=s["version"], tf=s["tf"], params=s["params"], evidence=s.get("evidence", ""),
                start_eur=start, equity_eur=round(st["equity_eur"], 4), balance_eur=round(st["balance_eur"], 4), realized_eur=round(st["realized_eur"], 4),
                upnl_eur=round(st["upnl_eur"], 4), fees_eur=round(st["fees_eur"], 4), funding_eur=round(st["funding_eur"], 4),
                ret_pct=round((st["equity_eur"] / start - 1) * 100, 3), maxdd_pct=round(mdd * 100, 3), trades=len(tr),
                win_rate=round(len(w) / len(tr) * 100, 1) if tr else None, pf=round(sum(t["pnl_eur"] for t in w) / gl, 2) if gl > 0 else None,
                halted=st["halted"], halt_reason=st["halt_reason"], status=st["last_status"], last_cycle=st["last_cycle"], last_data_ok=st["last_data_ok"],
                risk=st["risk"], problems=st["last_problems"], signals=st["last_signals"], actions=st["last_actions"],
                positions=pos, trade_history=tr, evals=dict(cycles=n_runs, market_evaluations=n_ev, last=last_ev), rejected=rejected[::-1][:150], equity_curve=[[t, round(v, 4)] for t, v in eq[-1000:]], _logs=logs)
def unsci(t):
    def r(m):
        v = float(m.group(0)); return f"{v:,.1f}" if v >= 1000 else f"{v:.4g}"
    return re.sub(r"\d+(?:\.\d+)?e[+-]\d+", r, t)
def feed(ports):
    ev = []
    for p in ports:
        for ts, status, msg in p.pop("_logs"):
            m = json.loads(msg); tag = f"{p['role']} {p['strategy']}"
            ev.append(dict(ts=ts, kind="data", port=tag, text=("Market data fetched & validated (5 markets)" if not m["problems"] else "Data issues: " + "; ".join(m["problems"]))), )
            for c, s in m["signals"].items():
                kind = "skip" if "BLOCKED" in s else "signal" if "entry" in s and "no entry" not in s else "eval"
                ev.append(dict(ts=ts, kind=kind, port=tag, coin=c, text=unsci(s)))
            for a in m["actions"]:
                ev.append(dict(ts=ts, kind="entry" if a.startswith("OPENED") else "exit" if a.startswith("CLOSED") else "skip", port=tag, text=a))
    ev.sort(key=lambda e: e["ts"], reverse=True)
    return ev[:300]
def markers(ports):
    mk = {}
    for p in ports:
        for t in p["trade_history"]:
            mk.setdefault(t["coin"], []).append(dict(ts=t["open_ts"], type="entry", side=t["side"], price=t["entry"], port=p["role"]))
            mk.setdefault(t["coin"], []).append(dict(ts=t["close_ts"], type="exit", side=t["side"], price=t["exit"], port=p["role"], reason=t["reason"], pnl=t["pnl_eur"]))
        for q in p["positions"]: mk.setdefault(q["coin"], []).append(dict(ts=q["open_ts"], type="entry", side=q["side"], price=q["entry"], port=p["role"]))
    return mk
def signal_markers(ports):
    out = {}
    for p in ports:
        con = sqlite3.connect(p["_db"])
        for ts, msg in con.execute("select ts, msg from exec_log"):
            for c, s in json.loads(msg)["signals"].items():
                mm = re.match(r"bar (\S+ \S+) close [^:]+: (LONG|SHORT) entry", s)
                if mm: out.setdefault(c, []).append(dict(bar=mm.group(1), side=mm.group(2), port=p["role"], blocked="BLOCKED" in s, tf=p["tf"]))
    return {c: list({(x["bar"], x["port"]): x for x in v}.values()) for c, v in out.items()}
def reliability(now):
    P = lambda x: dt.datetime.strptime(x, "%Y-%m-%d %H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    runs = [(P(t), trig) for t, trig in sqlite3.connect("state/paper.db").execute("select ts, trigger from runs")]
    sched = [t for t, trig in runs if "routine" in trig]
    win0 = now - dt.timedelta(hours=24)
    first = min(sched) if sched else now
    start = max(win0, first - dt.timedelta(minutes=59))
    slots, b = [], next_run(start - dt.timedelta(minutes=1))
    while b <= now - dt.timedelta(minutes=10):   # slot counts once it is 10 min past
        slots.append(b); b += dt.timedelta(hours=1)
    rows = []
    for sl in slots:
        hit = [t for t in sched if sl - dt.timedelta(minutes=5) <= t < sl + dt.timedelta(minutes=55)]
        rows.append(dict(slot=sl.strftime("%Y-%m-%d %H:%M:%SZ"), run=hit[0].strftime("%Y-%m-%d %H:%M:%SZ") if hit else None, delay_min=round((hit[0] - sl).total_seconds() / 60, 1) if hit else None))
    ok = [r for r in rows if r["run"]]; d = [r["delay_min"] for r in ok]
    # HF uptime: minutes with a loop heartbeat (gap <= 90 s) / elapsed minutes since first loop within window
    ts = []
    if os.path.exists("logs/hf_runner.log"):
        for l in open("logs/hf_runner.log"):
            if "loop=" in l:
                t = P(l[:20])
                if t >= win0: ts.append(t)
    up = None
    if len(ts) > 1:
        cov = sum(min((b - a).total_seconds(), 60) for a, b in zip(ts, ts[1:]) if (b - a).total_seconds() <= 90) + 60
        up = round(min(100, cov / max(60, (now - ts[0]).total_seconds()) * 100), 1)
    gaps = [dict(from_=a.strftime("%H:%M:%SZ"), to=b.strftime("%H:%M:%SZ"), min=round((b - a).total_seconds() / 60, 1)) for a, b in zip(ts, ts[1:]) if (b - a).total_seconds() > 90]
    return dict(window="last 24h (tracking since first scheduled run %s)" % (first.strftime("%Y-%m-%d %H:%M:%SZ") if sched else "n/a"),
                expected=len(rows), actual=len(ok), missed=len(rows) - len(ok), late_over_10min=sum(1 for x in d if x > 10),
                avg_delay_min=round(sum(d) / len(d), 1) if d else None, max_delay_min=max(d) if d else None, slots=rows,
                manual_runs_24h=sum(1 for t, trig in runs if t >= win0 and "routine" not in trig),
                hf_uptime_pct=up, hf_loops_24h=len(ts), hf_since=ts[0].strftime("%Y-%m-%d %H:%M:%SZ") if ts else None, hf_gaps=gaps[-20:])

def build(PORTFOLIOS, cfg):
    now = dt.datetime.now(dt.timezone.utc)
    ports = []
    for pf in PORTFOLIOS:
        if os.path.exists(pf["state"]):
            p = pstats(pf, cfg); p["_db"] = pf["db"]; ports.append(p)
    order = {"ACTIVE": 0, "SHADOW": 1, "TEST": 2}; ports.sort(key=lambda p: order.get(p["role"], 9))
    sigm = signal_markers(ports)
    for p in ports: p.pop("_db")
    meta = json.load(open("state/run_meta.json")) if os.path.exists("state/run_meta.json") else {}
    candles = {}
    for tf in ("1h", "4h"):
        f = f"state/candles_{tf}.json"
        if os.path.exists(f):
            d = json.load(open(f)); candles[tf] = {k: v for k, v in d.items() if not k.startswith("_")}; candles[tf + "_fetched"] = d.get("_fetched")
    act = next((p for p in ports if p["role"] == "ACTIVE"), ports[0])
    data = dict(simulated=True, disclaimer="SIMULATED paper trading with virtual money. No real orders, no wallet, no exchange account.",
                generated=now.strftime("%Y-%m-%d %H:%M:%SZ"), generated_ms=int(now.timestamp() * 1000),
                run=dict(last_run=meta.get("last_run"), last_run_ms=meta.get("last_run_ms"), trigger=meta.get("trigger"), status=meta.get("status"), errors=meta.get("errors", []),
                         next_scheduled=next_run(now).strftime("%Y-%m-%d %H:%M:%SZ"), schedule="hourly at :07 Europe/Berlin (external routine)", stale_after_min=75,
                         history=meta.get("history", [])[:30]),
                status_panel=dict(market_analysis=dict(ts=act["last_cycle"], result=f"{len(act['signals'])} markets evaluated; data issues: {len(act['problems'])}"),
                                  risk_check=dict(ts=act["last_cycle"], result=("blocks: " + "; ".join(act["risk"]["blocks"])) if act["risk"]["blocks"] else f"all limits OK (DD {act['risk']['dd']*100:.2f}% / 10%, daily {act['risk']['daily_loss']*100:.2f}% / 3%)"),
                                  execution=dict(ts=act["last_cycle"], result="; ".join(act["actions"]) or "no orders (no qualifying signal)")),
                limits=dict(max_leverage=cfg["max_leverage"], risk_per_trade=cfg["risk_per_trade"], daily_loss_stop=cfg["daily_loss_stop"], max_drawdown_halt=cfg["max_drawdown_halt"], max_positions=cfg["max_positions"], min_notional_usd=10),
                reliability=reliability(now), philosophy=["No trade quota: zero trades is a valid outcome.", "Trade only on a valid, pre-defined signal on closed bars with fresh data.", "Expected edge must be positive after fees, spread, slippage and funding; otherwise stay flat.", "Every trade obeys 1% risk, 3x cap, $10 minimum, max 2 positions, 3% daily stop and 10% drawdown halt.", "Strategies are compared in separate portfolios; nothing is promoted to ACTIVE without out-of-sample evidence."],
                portfolios=ports, feed=feed(ports), markers=markers(ports), signal_markers=sigm, candles=candles,
                market={c: v for c, v in json.load(open("state/state.json")).get("market", {}).items()})
    os.makedirs("public", exist_ok=True)
    json.dump(data, open("public/data.json.tmp", "w"), separators=(",", ":")); os.replace("public/data.json.tmp", "public/data.json")
    shutil.copyfile("web/index.html", "public/index.html")
