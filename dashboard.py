"""Builds static mobile-friendly dashboard.html (+ dashboard.png via headless Chrome). SIMULATED DATA ONLY."""
import json, os, subprocess, html
def svg_curve(pts, w=640, h=180):
    if len(pts) < 2: pts = pts * 2 if pts else [50, 50]
    lo, hi = min(pts), max(pts); hi = hi if hi > lo else lo + 0.01
    xy = " ".join(f"{i*(w-10)/(len(pts)-1)+5:.1f},{h-10-(v-lo)/(hi-lo)*(h-30):.1f}" for i, v in enumerate(pts))
    col = "#16c784" if pts[-1] >= pts[0] else "#ea3943"
    return f'<svg viewBox="0 0 {w} {h}" width="100%"><polyline fill="none" stroke="{col}" stroke-width="2" points="{xy}"/><text x="5" y="14" fill="#8a94a6" font-size="11">€{hi:.2f}</text><text x="5" y="{h-2}" fill="#8a94a6" font-size="11">€{lo:.2f}</text></svg>'
def build(st, con, cfg):
    eq = [r[0] for r in con.execute("select equity_eur from equity order by rowid")]
    start = cfg["start_balance_eur"]; e = st["equity_eur"]; pnl = e - start
    trades = con.execute("select coin,side,strategy,open_ts,close_ts,entry,exit,lev,fees_eur,funding_eur,pnl_eur,reason from trades order by id desc").fetchall()
    wins = sum(1 for t in trades if t[10] > 0); wr = f"{wins/len(trades)*100:.0f}%" if trades else "–"
    import numpy as np
    arr = np.array([start] + eq); mdd = float(np.max(1 - arr / np.maximum.accumulate(arr))) * 100
    c = lambda v: "pos" if v >= 0 else "neg"
    pos_rows = "".join(f"<tr><td>{k}</td><td class='{'pos' if p['side']>0 else 'neg'}'>{'LONG' if p['side']>0 else 'SHORT'}</td><td>{p['entry']:.6g}</td><td>{p.get('mark',0):.6g}</td><td>{p['qty']:.5g}<br><small>${p['notional_usd']:.2f}</small></td><td>{p['lev']:.2f}x</td><td>{p['stop']:.6g}</td><td>{p['liq']:.6g}</td><td class='{c(p.get('upnl_eur',0))}'>€{p.get('upnl_eur',0):.3f}</td><td>€{p['fees_eur']:.3f}/€{p['funding_eur']:.3f}</td></tr>" for k, p in st["positions"].items()) or "<tr><td colspan=10>No open positions (flat)</td></tr>"
    tr_rows = "".join(f"<tr><td>{t[0]}</td><td>{t[1]}</td><td>{t[3][5:16]}</td><td>{t[4][5:16]}</td><td>{t[5]:.6g}</td><td>{t[6]:.6g}</td><td>{t[7]:.2f}x</td><td>€{t[8]:.3f}</td><td>€{t[9]:.3f}</td><td class='{c(t[10])}'>€{t[10]:.3f}</td><td>{t[11]}</td></tr>" for t in trades) or "<tr><td colspan=11>No closed trades yet</td></tr>"
    mk_rows = "".join(f"<tr><td>{k}</td><td>{m['mid']:.6g}</td><td>{m['spread_bps']:.2f}</td><td>{m['funding_1h']*100:.4f}%</td><td>{m['oi']:.4g}</td><td>${m['dayVlm']/1e6:.1f}M</td><td><small>{html.escape(st['last_signals'].get(k,''))}</small></td></tr>" for k, m in st.get("market", {}).items())
    runs = con.execute("select ts,trigger,status,duration_s,equity_eur,actions,problems from runs order by rowid desc limit 30").fetchall()
    run_rows = "".join(f"<tr><td>{r[0]}</td><td>{html.escape(str(r[1]))}</td><td>{r[2]}</td><td>{r[3]}s</td><td>€{r[4]:.4f}</td><td>{r[5]}</td><td>{r[6]}</td></tr>" for r in runs) or "<tr><td colspan=7>none</td></tr>"
    bt = ""
    if os.path.exists("results/backtest_report.json"):
        for r in json.load(open("results/backtest_report.json"))["results"]:
            t = r["oos_total"]; bt += f"<tr><td>{r['strategy']}</td><td>{r['tf']}</td><td class='{c(t['net_ret_pct'])}'>{t['net_ret_pct']}%</td><td>{t['maxdd_pct']}%</td><td>{t['win_rate']}%</td><td>{t['pf']}</td><td>{t['sharpe']}</td><td>{t['trades']}</td><td>{'✅' if r['passed'] else '–'}</td></tr>"
    url = open("state/dashboard_url.txt").read().strip() if os.path.exists("state/dashboard_url.txt") else "not set"
    shadow = ""
    if os.path.exists("state/shadow_breakout1h.json") and cfg.get("shadow_strategy"):
        import sqlite3
        ss = json.load(open("state/shadow_breakout1h.json")); sc = sqlite3.connect("state/shadow_breakout1h.db"); sa = cfg["shadow_strategy"]
        seq = [r[0] for r in sc.execute("select equity_eur from equity order by rowid")]; str_ = sc.execute("select coin,side,open_ts,close_ts,entry,exit,lev,fees_eur,funding_eur,pnl_eur,reason from trades order by id desc").fetchall()
        sp = ss["equity_eur"] - start; sw = sum(1 for t in str_ if t[9] > 0)
        spos = "".join(f"<tr><td>{k}</td><td class='{'pos' if p['side']>0 else 'neg'}'>{'LONG' if p['side']>0 else 'SHORT'}</td><td>{p['entry']:.6g}</td><td>{p.get('mark',0):.6g}</td><td>${p['notional_usd']:.2f}</td><td>{p['lev']:.2f}x</td><td>{p['stop']:.6g}</td><td class='{c(p.get('upnl_eur',0))}'>€{p.get('upnl_eur',0):.3f}</td></tr>" for k, p in ss["positions"].items()) or "<tr><td colspan=8>No open positions (flat)</td></tr>"
        strs = "".join(f"<tr><td>{t[0]}</td><td>{t[1]}</td><td>{t[2][5:16]}</td><td>{t[3][5:16]}</td><td>{t[4]:.6g}</td><td>{t[5]:.6g}</td><td class='{c(t[9])}'>€{t[9]:.3f}</td><td>{t[10]}</td></tr>" for t in str_) or "<tr><td colspan=8>No closed trades yet</td></tr>"
        sig = "".join(f"<li>{k}: {html.escape(v)}</li>" for k, v in ss.get("last_signals", {}).items())
        shadow = f"""<h2 style="color:#a78bfa">SHADOW portfolio — {sa['version']} (separate virtual €{start:.0f}, NOT the active strategy)</h2>
<div class=card style="border:1px dashed #a78bfa"><div class=grid><div class=card>Equity (sim)<b>€{ss['equity_eur']:.4f}</b></div><div class=card>Net P&L<b class={c(sp)}>€{sp:+.4f} ({sp/start*100:+.2f}%)</b></div>
<div class=card>Realized / uPnL<b>€{ss['realized_eur']:+.3f} / €{ss['upnl_eur']:+.3f}</b></div><div class=card>Fees / Funding<b>€{ss['fees_eur']:.3f} / €{ss['funding_eur']:.3f}</b></div>
<div class=card>Trades / Win<b>{len(str_)} / {f"{sw/len(str_)*100:.0f}%" if str_ else "–"}</b></div><div class=card>Status<b>{ss['last_status']}{' HALTED' if ss['halted'] else ''}</b><small>{ss['last_cycle']}</small></div></div>
{svg_curve([start]+seq, h=120)}<small>{json.dumps(sa['params'])} — {html.escape(sa['evidence'])}</small>
<div class=scroll><table><tr><th>Mkt</th><th>Side</th><th>Entry</th><th>Mark</th><th>Size</th><th>Lev</th><th>Stop</th><th>uPnL</th></tr>{spos}</table></div>
<div class=scroll><table><tr><th>Mkt</th><th>Side</th><th>Open</th><th>Close</th><th>Entry</th><th>Exit</th><th>Net</th><th>Reason</th></tr>{strs}</table></div><ul style="font-size:12px;color:#8a94a6">{sig}</ul></div>"""
    a = cfg["active_strategy"]; status_col = "#16c784" if st["last_status"] == "OK" and not st["halted"] else "#f0b90b"
    page = f"""<!doctype html><html><head><meta charset=utf-8><meta http-equiv="refresh" content="120"><meta name=viewport content="width=device-width,initial-scale=1"><title>GELDDRUCKMASCHINE (SIMULATED)</title>
<style>body{{background:#0b0e11;color:#eaecef;font:14px -apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:12px;max-width:1000px;margin:auto}}
.banner{{background:#f0b90b;color:#000;font-weight:700;text-align:center;padding:6px;border-radius:6px}}h1{{font-size:20px;margin:12px 0 4px}}h2{{font-size:15px;color:#8a94a6;margin:18px 0 6px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px}}.card{{background:#181a20;border-radius:8px;padding:10px}}.card b{{display:block;font-size:18px;margin-top:4px}}
.pos{{color:#16c784}}.neg{{color:#ea3943}}table{{width:100%;border-collapse:collapse;font-size:12px}}td,th{{padding:5px;border-bottom:1px solid #2b3139;text-align:left}}th{{color:#8a94a6}}.scroll{{overflow-x:auto;background:#181a20;border-radius:8px}}small{{color:#8a94a6}}</style></head><body>
<div class=banner>⚠ SIMULATED PAPER TRADING — virtual €{start:.0f}, no real money, no real orders</div>
<h1>GELDDRUCKMASCHINE</h1><div><span style="color:{status_col}">●</span> Status: {st['last_status']}{' / HALTED' if st['halted'] else ''} · last cycle {st['last_cycle']} · last good data {st['last_data_ok']} · cycles {st['cycles']}<br><small>Public URL: {html.escape(url)}</small></div>
<div class=grid style="margin-top:10px"><div class=card>Start<b>€{start:.2f}</b></div><div class=card>Equity (sim)<b>€{e:.4f}</b></div><div class=card>Net P&L<b class={c(pnl)}>€{pnl:+.4f}</b></div><div class=card>Return<b class={c(pnl)}>{pnl/start*100:+.3f}%</b></div>
<div class=card>Realized<b class={c(st['realized_eur'])}>€{st['realized_eur']:+.4f}</b></div><div class=card>Unrealized<b class={c(st['upnl_eur'])}>€{st['upnl_eur']:+.4f}</b></div><div class=card>Fees / Funding<b>€{st['fees_eur']:.3f} / €{st['funding_eur']:.3f}</b></div>
<div class=card>Win rate<b>{wr}</b><small>{len(trades)} trades</small></div><div class=card>Max DD<b>{mdd:.2f}%</b></div><div class=card>Open positions<b>{len(st['positions'])}/{cfg['max_positions']}</b></div></div>
<h2>Equity curve (simulated, per cycle)</h2><div class=card>{svg_curve([start]+eq)}</div>
<h2>Active positions</h2><div class=scroll><table><tr><th>Mkt</th><th>Side</th><th>Entry</th><th>Mark</th><th>Size</th><th>Lev</th><th>Stop</th><th>Liq≈</th><th>uPnL</th><th>Fees/Fund</th></tr>{pos_rows}</table></div>
<h2>Market data (Hyperliquid public API) & latest signals</h2><div class=scroll><table><tr><th>Mkt</th><th>Mid $</th><th>Spread bps</th><th>Funding/h</th><th>OI</th><th>24h vol</th><th>Signal</th></tr>{mk_rows}</table></div>
<h2>Risk</h2><div class=card>Drawdown from peak {st['risk']['dd']*100:.2f}% (halt at 10%) · daily loss {st['risk']['daily_loss']*100:.2f}% (stop at 3%) · max lev {cfg['max_leverage']}x · risk/trade 1% · blocks: {html.escape('; '.join(st['risk']['blocks']) or 'none')}<br>Data problems: {html.escape('; '.join(st['last_problems']) or 'none')} · EURUSD {st['fx_eurusd']} (ECB {st.get('fx_date')})</div>
<h2>Active strategy</h2><div class=card><b>{a['version']}</b> {json.dumps(a['params'])}<br><small>{html.escape(a['evidence'])}</small></div>
<h2>Trade history (active)</h2><div class=scroll><table><tr><th>Mkt</th><th>Side</th><th>Open</th><th>Close</th><th>Entry</th><th>Exit</th><th>Lev</th><th>Fees</th><th>Fund</th><th>Net</th><th>Reason</th></tr>{tr_rows}</table></div>
{shadow}
<h2>Run history (last 30 cycles, UTC)</h2><div class=scroll><table><tr><th>Time</th><th>Trigger</th><th>Status</th><th>Dur</th><th>Equity</th><th>Actions</th><th>Problems</th></tr>{run_rows}</table></div>
<h2>Strategy research — walk-forward out-of-sample backtest (after fees, slippage, funding)</h2><div class=scroll><table><tr><th>Strategy</th><th>TF</th><th>Net</th><th>MaxDD</th><th>Win</th><th>PF</th><th>Sharpe</th><th>Trades</th><th>Pass</th></tr>{bt}</table></div>
<p><small>Page auto-reloads every 2 min; data updates once per hourly cycle. All figures are hypothetical simulation results. Backtests are not a guarantee of future performance. Generated {st['last_cycle']}.</small></p></body></html>"""
    open("dashboard.html", "w").write(page)
    os.makedirs("public", exist_ok=True)
    summary = dict(simulated=True, note="SIMULATED paper trading, virtual money only", generated=st["last_cycle"], active=dict(strategy=a["version"], equity_eur=round(e, 4), start_eur=start,
        positions={k: dict(side=p["side"], entry=p["entry"], mark=p.get("mark"), notional_usd=round(p["notional_usd"], 2), lev=p["lev"], upnl_eur=round(p.get("upnl_eur", 0), 4)) for k, p in st["positions"].items()},
        trades=len(trades), realized_eur=round(st["realized_eur"], 4), status=st["last_status"], halted=st["halted"]), equity_curve=[round(x, 4) for x in eq[-500:]])
    if shadow: summary["shadow"] = dict(strategy=sa["version"], equity_eur=round(ss["equity_eur"], 4), positions=list(ss["positions"]), trades=len(str_), status=ss["last_status"])
    json.dump(summary, open("public/data.json", "w"), indent=1)
    os.makedirs("public", exist_ok=True)
    open("public/index.html.tmp", "w").write(page); os.replace("public/index.html.tmp", "public/index.html")
    try:
        subprocess.run(["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--window-size=430,1800",
                        f"--screenshot={os.path.abspath('dashboard.png')}", "file://" + os.path.abspath("dashboard.html")], capture_output=True, timeout=60)
        import shutil; shutil.copyfile("dashboard.png", "public/dashboard.png")
    except Exception as ex: print("screenshot failed", ex)
