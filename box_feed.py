"""Hourly box portfolios -> the ONE store (code repo store/box/portfolios.json) -> ONE export (public/data.json).
Called by cycle.py post_steps on the box (Rudi's existing hourly routine; no new schedule). SIMULATED paper trading only.
Never contains secrets: only portfolio stats derived from the paper engine's own logs."""
import json, os, sys, shutil, subprocess, datetime as dt
BOX = os.path.dirname(os.path.abspath(__file__)); os.chdir(BOX); sys.path.insert(0, BOX)
REPO = os.environ.get("GDM_CODE_REPO", "/workspace/gdm-code")

def main():
    if not os.path.isdir(os.path.join(REPO, ".git")): print("box_feed: code repo clone missing -> skip"); return 0
    import cycle, export
    ports = []
    for pf in cycle.PORTFOLIOS + cycle.hf_portfolios():
        if not os.path.exists(pf["state"]): continue
        p = export.pstats(pf, cycle.CFG); p.pop("_logs", None)
        p["rejected"] = p["rejected"][:20]; p["equity_curve"] = p["equity_curve"][-400:]; ports.append(p)
    hf = json.load(open("state/hf_heartbeat.json")) if os.path.exists("state/hf_heartbeat.json") else {}
    rm = json.load(open("state/run_meta.json")) if os.path.exists("state/run_meta.json") else {}
    out = dict(simulated=True, exported=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"), portfolios=ports,
               run_meta={k: rm.get(k) for k in ("last_run", "finished", "trigger", "status", "errors")}, hf={k: hf.get(k) for k in ("ts", "loops", "status", "strategy", "errors")})
    g = lambda *a: subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True, timeout=90)
    g("fetch", "-q", "origin", "main"); g("merge", "-q", "--no-edit", "-X", "theirs", "origin/main")   # get latest sessions first
    os.makedirs(os.path.join(REPO, "store", "box"), exist_ok=True)
    json.dump(out, open(os.path.join(REPO, "store", "box", "portfolios.json"), "w"), separators=(",", ":"))
    try: cand = dict(tf="4h", fetched=None, coins={k: v[-150:] for k, v in json.load(open("state/candles_4h.json")).items() if not k.startswith("_")})
    except Exception: cand = None
    r = subprocess.run([sys.executable, "-c", f"import sys;sys.path.insert(0,{REPO!r});import store,json;store.build(extra_candles=json.loads(sys.stdin.read()) or None)"],
                       input=json.dumps(cand), capture_output=True, text=True, cwd=REPO, timeout=60)
    if r.returncode: print("box_feed: build failed", r.stderr[-300:]); return 1
    shutil.copyfile(os.path.join(REPO, "public", "data.json"), "public/data.json")    # Pages copy = identical export
    if os.path.exists(os.path.join(REPO, "web", "index.html")): shutil.copyfile(os.path.join(REPO, "web", "index.html"), "public/index.html")
    s = subprocess.run(["bash", os.path.join(REPO, "sync.sh"), "box hourly portfolios (SIMULATED)"], capture_output=True, text=True, timeout=150)
    print("box_feed:", "pushed" if s.returncode == 0 else "push failed", len(ports), "portfolios"); return 0

if __name__ == "__main__":
    sys.exit(main())
