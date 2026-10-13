# Trading Session Mode: design, security, test evidence (2026-10-13). SIMULATED only

## Control channel (static GitHub Pages cannot send commands securely)
- A static page can only send commands by embedding a write credential in the browser. That would be public, so it is **rejected**. The dashboard only *generates* commands/links and holds no credentials.
- **Recommended:** `workflow_dispatch` on a code repo. Only users with write access (the owner) can trigger it, from the GitHub web UI or the GitHub mobile app ("Run workflow" with inputs action/capital/minutes/strategy), or with `gh workflow run`. Authentication is GitHub's login + 2FA. Nothing is stored in the page.
- **Alternative:** an issue/comment command parsed by a workflow, with `github.event.sender.login == github.repository_owner` checked. Workable, but there is more room for parsing mistakes and spoofing. Not chosen.
- Dashboard deep link (after activation): `https://github.com/<owner>/<code-repo>/actions/workflows/session.yml` → "Run workflow".

## Execution
- **Box:** `session.py` runs fine on the box, but the box **freezes when no agent session/routine is active** (HF uptime ≈ 39%). So a session started from the iPad and left alone is **not guaranteed to run** on the box. A watchdog resume (hourly routine) catches it up later: stops are checked against candles since the last check, and gaps fill at the open.
- **GitHub Actions** (`.github/workflows/session.yml`, ready, NOT pushed): a single job loops every 60 s for up to ~6 h (job limit). Free on standard runners for public repos.
  - `concurrency: trading-session` → one session at a time.
  - State is committed every 5 min and on job end. A crashed or timed-out job can be restarted and resumes from the committed state.
  - Control (stop/close_all) is a separate dispatch that commits `sessions/control.json`, which the running loop reads each minute through `git show origin/main:...`.
  - **ToS:** long-running loop jobs are a grey zone ("serverless application", "disproportionate burden"). Occasional sessions of ≤ 3 h are lower risk than a 24/7 loop.
  - **Not tested:** whether Hyperliquid is reachable from runners. It can't be tested without activating.
- **Safety:**
  - Same engine/limits as `cycle.py` (1% risk, 3% daily, 10% DD halt, max 2 pos, 3x, $10 min).
  - STOP = no new entries; positions are managed by normal exits and stops.
  - Emergency `close_all` closes at market (mid + spread/slippage + fee).
  - Data stale → no entries.
  - One-session lock (flock + current.json); an engine error is trapped per loop.

## What the user must approve to make it independent of the iPad
1. Create a **public code repo** (e.g. `gelddruckmaschine`) containing this project code + state (no secrets exist; code becomes public).
2. Push `.github/workflows/session.yml` there (the gh token already has `workflow` scope) and accept the GitHub Actions ToS grey-zone risk.
3. Optionally, one `workflow_dispatch` test run (few minutes) to verify Hyperliquid reachability from runners.
4. Decide the single writer: sessions run in Actions, while the hourly portfolios stay on the box (separate state → no conflict).

## Test evidence (box, real Hyperliquid data, all times UTC)
- **S1** `20261013-183456`: €50, 10 min, breakout-1h-v1.
  - START 18:34:56. **kill -9 at 18:38:26**, resume 18:40:06 (loops continued 4→5).
  - Timeout 18:45:06 → `stopping` → flat → **ENDED 18:45:11**.
  - Report: 0 trades, €50.00 → €50.00, 10 loops, 50 market evaluations, all "no entry".
- **S2** `20261013-184546`: €200, 5 min, funding-fade-4h-x1.
  - A second start while running was **refused** ("one session at a time").
  - Opened BTC LONG $65.2 notional at 0.29x at 18:46:07.
  - **STOP** 18:47:46 → status "Beenden – offene Positionen werden verwaltet" with block "no new entries"; the position stayed open and was managed.
  - **kill -9 at 18:48:44**, resume 18:49:54 in `stopping`; the position was re-checked against live mid/stop.
  - **close_all** → emergency close 18:51:01 at 83,074.07 → **ENDED 18:51:16**.
  - Report: 1 trade, gross −€0.009, fees €0.0525, net −€0.0615, €200 → €199.9385, 5.5 min actual vs 5 planned.
- Public `session.json` published at start, on events and every 5 min. Verified on GitHub Pages: S2 ended, 1 trade, −0.0615.
