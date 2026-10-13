"""GELDDRUCKMASCHINE phase evaluator (research5). Pure function, no I/O side effects except optional file writes.

evaluate(trades, equity, start_ts, start_equity=50.0, now_ts=None, phases=None, min_trades=30, max_dd=0.10) -> dict
  trades : list of dicts, each with at least  t_out (close time, ms UTC or ISO str), net (EUR, after fees+funding)
           optional: strategy, coin, exit_reason, gross, fees, funding (EUR)  -> used for cause analysis
  equity : list of (ts, equity_eur) mark-to-market points (any frequency), or dicts {"t":..,"equity":..}
  start_ts: portfolio start (ms or ISO). Phases are relative to it (default PHASES):
           P1 = day 0-7, P2 = day 7-21, P3 = day 21-35, then monthly reviews M1.. (30 days each)
  Criteria are evaluated CUMULATIVELY from start to the phase end (trade count needs the whole sample):
    net_positive : equity_end - start_equity > 0 (after fees/funding)
    min_trades   : closed trades >= min_trades
    max_dd       : max drawdown of the equity curve < max_dd
    robust_net   : net - best single trade > 0  (result not carried by one outlier)
  Status per completed phase:
    PASS          all four ok                                     -> action "continue"
    INCONCLUSIVE  only min_trades (or, in P1/P2, robust_net) fails -> "continue" (P1/P2) / "extend" (P3+)
    FAIL          net_positive or max_dd fails (any phase), robust_net fails (P3+) -> "pause" + cause analysis
  Phases not yet ended are reported as "running" with interim numbers.
render_md(result) -> German markdown.   CLI: python phases.py trades.json equity.json START_ISO [out_prefix]
"""
import json, sys, datetime as dt
DAY = 86400_000
PHASES = [("P1", 0, 7), ("P2", 7, 21), ("P3", 21, 35)] + [(f"M{k}", 35 + 30*(k-1), 35 + 30*k) for k in range(1, 13)]

def _ms(x):
    if isinstance(x, (int, float)): return int(x)
    return int(dt.datetime.fromisoformat(str(x).replace("Z", "+00:00")).timestamp() * 1000)
def _iso(ms): return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def _group(trs, key):
    g = {}
    for t in trs:
        k = str(t.get(key, "?")); e = g.setdefault(k, dict(trades=0, net_eur=0.0, wins=0))
        e["trades"] += 1; e["net_eur"] += t["net"]; e["wins"] += t["net"] > 0
    return {k: dict(trades=v["trades"], net_eur=round(v["net_eur"], 2), win_pct=round(100 * v["wins"] / v["trades"], 1)) for k, v in sorted(g.items(), key=lambda kv: kv[1]["net_eur"])}

def causes(trs):
    gross = sum(t.get("gross", t["net"]) for t in trs); fees = sum(t.get("fees", 0) for t in trs); fund = sum(t.get("funding", 0) for t in trs)
    best = max((t["net"] for t in trs), default=0.0); net = sum(t["net"] for t in trs)
    c = dict(by_strategy=_group(trs, "strategy"), by_coin=_group(trs, "coin"), by_exit_reason=_group(trs, "exit_reason"),
             gross_eur=round(gross, 2), fees_eur=round(fees, 2), funding_eur=round(fund, 2),
             cost_share_of_gross=round((fees + fund) / gross, 2) if gross > 0 else None, best_trade_eur=round(best, 2),
             best_trade_share_of_net=round(best / net, 2) if net > 0 else None)
    notes = []
    if gross <= 0: notes.append("Bruttoergebnis ≤ 0: die Signale selbst haben keinen Vorteil (nicht nur Kosten).")
    elif fees + fund >= gross: notes.append("Kosten (Gebühren+Funding) ≥ Brutto-Gewinn: Kosten fressen den Vorteil auf.")
    if c["by_strategy"]: k, v = next(iter(c["by_strategy"].items())); notes.append(f"Schwächste Strategie: {k} ({v['net_eur']} € in {v['trades']} Trades).") if v["net_eur"] < 0 else None
    if c["by_coin"]: k, v = next(iter(c["by_coin"].items())); notes.append(f"Schwächster Coin: {k} ({v['net_eur']} €).") if v["net_eur"] < 0 else None
    st = {k: v for k, v in c["by_exit_reason"].items() if k.startswith("stop")}
    if st: notes.append(f"Stop-Ausstiege: {sum(v['trades'] for v in st.values())} Trades, {round(sum(v['net_eur'] for v in st.values()), 2)} €.")
    if net > 0 and best >= net: notes.append("Gesamtgewinn hängt an einem einzelnen Trade.")
    c["notes"] = [n for n in notes if n]; return c

def _maxdd(points, start_equity):
    peak, mdd = start_equity, 0.0
    for _, e in points: peak = max(peak, e); mdd = max(mdd, 1 - e / peak if peak > 0 else 0)
    return mdd

def evaluate(trades, equity, start_ts, start_equity=50.0, now_ts=None, phases=None, min_trades=30, max_dd=0.10):
    s0 = _ms(start_ts); now = _ms(now_ts) if now_ts is not None else int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    trs = sorted([{**t, "t_out": _ms(t["t_out"])} for t in trades], key=lambda t: t["t_out"])
    pts = sorted([(_ms(p["t"]), float(p["equity"])) if isinstance(p, dict) else (_ms(p[0]), float(p[1])) for p in equity])
    res = dict(start=_iso(s0), evaluated_at=_iso(now), start_equity=start_equity, criteria=dict(net_positive="Netto > 0 nach Gebühren", min_trades=f">= {min_trades} Trades",
               max_dd=f"MaxDD < {max_dd:.0%}", robust_net="Netto minus bester Trade > 0"), phases=[], action="continue", current_phase=None)
    for name, a, b in (phases or PHASES):
        p0, p1 = s0 + a * DAY, s0 + b * DAY
        if p0 > now: break
        end = min(p1, now); tr = [t for t in trs if t["t_out"] <= end]; ep = [p for p in pts if p[0] <= end]
        eq_end = ep[-1][1] if ep else start_equity + sum(t["net"] for t in tr)
        net = eq_end - start_equity; best = max((t["net"] for t in tr), default=0.0); mdd = _maxdd([(s0, start_equity)] + ep, start_equity)
        chk = dict(net_positive=net > 0, min_trades=len(tr) >= min_trades, max_dd=mdd < max_dd, robust_net=(net - max(best, 0)) > 0)
        running = p1 > now
        early = name in ("P1", "P2")
        hard = [k for k in (("net_positive", "max_dd") if early else ("net_positive", "max_dd", "robust_net")) if not chk[k]]
        if running: status, act = "running", "continue"
        elif not tr and not hard[1:]: status, act, hard = "INCONCLUSIVE", "continue" if early else "extend", []  # no trades yet: not a failure
        elif hard: status, act = "FAIL", "pause"
        elif not chk["min_trades"] or not chk["robust_net"]: status, act = "INCONCLUSIVE", "continue" if early else "extend"
        else: status, act = "PASS", "continue"
        ph = dict(phase=name, window=f"{_iso(p0)} → {_iso(p1)}", status=status, action=act, checks=chk, failed=hard + [k for k in ("min_trades", "robust_net") if not chk[k] and k not in hard],
                  net_eur=round(net, 2), net_pct=round(100 * net / start_equity, 2), trades=len(tr), trades_in_phase=sum(1 for t in tr if t["t_out"] > p0),
                  maxdd_pct=round(100 * mdd, 2), best_trade_eur=round(best, 2), net_minus_best_eur=round(net - max(best, 0), 2))
        if status == "FAIL": ph["cause_analysis"] = causes(tr)
        res["phases"].append(ph); res["current_phase"] = name
        if status != "running": res["action"] = act
        if status == "FAIL": break  # pause: later phases are not evaluated
    last = res["phases"][-1] if res["phases"] else None
    res["recommendation"] = _recommend(res, last)
    return res

def _recommend(res, last):
    if not last: return "Noch keine Phase begonnen."
    done = [p for p in res["phases"] if p["status"] != "running"]
    if done and done[-1]["status"] == "FAIL":
        return f"PAUSE: Phase {done[-1]['phase']} nicht bestanden ({', '.join(done[-1]['failed'])}). Keine neuen Einstiege; Ursachen prüfen, Strategie überarbeiten oder verwerfen."
    if done and done[-1]["status"] == "INCONCLUSIVE" and done[-1]["action"] == "extend":
        return f"VERLÄNGERN: {done[-1]['phase']} ohne harten Fehler, aber nur {done[-1]['trades']} Trades (<30). Weiter beobachten, keine Aussage über einen Vorteil möglich."
    if done and done[-1]["status"] == "PASS": return f"WEITER: {done[-1]['phase']} bestanden. Weiterhin Paper-Trading; bestanden heißt nicht statistisch belegt."
    return f"WEITER: aktuelle Phase {last['phase']} läuft (Zwischenstand {last['net_eur']} €, {last['trades']} Trades, MaxDD {last['maxdd_pct']} %)."

def render_md(r, title="Phasenbewertung"):
    yn = lambda b: "✅" if b else "❌"
    L = [f"# {title} (SIMULIERT, Paper-Trading)", f"Start: {r['start']} · Bewertet: {r['evaluated_at']} · Startkapital: {r['start_equity']} €", "",
         f"**Empfehlung:** {r['recommendation']}  ", f"**Aktion:** `{r['action']}`", "",
         "| Phase | Zeitraum | Status | Netto € | Trades | MaxDD % | Netto − bester Trade € | Netto>0 | ≥30 Trades | DD<10 % | Robust |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in r["phases"]:
        c = p["checks"]; L.append(f"| {p['phase']} | {p['window']} | {p['status']} | {p['net_eur']} | {p['trades']} | {p['maxdd_pct']} | {p['net_minus_best_eur']} | {yn(c['net_positive'])} | {yn(c['min_trades'])} | {yn(c['max_dd'])} | {yn(c['robust_net'])} |")
    for p in r["phases"]:
        if "cause_analysis" in p:
            ca = p["cause_analysis"]; L += ["", f"## Ursachenanalyse {p['phase']}", f"Brutto {ca['gross_eur']} € · Gebühren {ca['fees_eur']} € · Funding {ca['funding_eur']} € · Kostenanteil am Brutto: {ca['cost_share_of_gross']}", ""]
            L += [f"- {n}" for n in ca["notes"]]
            for key, lab in (("by_strategy", "Strategie"), ("by_coin", "Coin"), ("by_exit_reason", "Ausstiegsgrund")):
                L += ["", f"| {lab} | Trades | Netto € | Gewinnquote % |", "|---|---|---|---|"] + [f"| {k} | {v['trades']} | {v['net_eur']} | {v['win_pct']} |" for k, v in ca[key].items()]
    L += ["", "Hinweis: Kriterien werden kumuliert ab Start bewertet. In P1/P2 gelten <30 Trades oder ein Ergebnis, das an einem Trade hängt, als INCONCLUSIVE (kein Fehler); ab P3 führt Letzteres zur Pause."]
    return "\n".join(L)

if __name__ == "__main__":
    tr, eq, st = json.load(open(sys.argv[1])), json.load(open(sys.argv[2])), sys.argv[3]
    r = evaluate(tr, eq, st); pre = sys.argv[4] if len(sys.argv) > 4 else "phase_report"
    json.dump(r, open(pre + ".json", "w"), indent=1, ensure_ascii=False); open(pre + ".md", "w").write(render_md(r)); print(r["action"], "-", r["recommendation"])
