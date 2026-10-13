# GELDDRUCKMASCHINE: execution architecture review (2026-10-13). Report only, nothing activated
All trading is SIMULATED, and the bot only needs **public** Hyperliquid market data. No exchange keys or wallet exist anywhere.

## 1. Measured facts about the current setup (box)
| Component | Observation (real logs, 2026-10-13) |
|---|---|
| Hourly routine → `cycle.py` | Scheduled :07 Berlin. Ran at 17:20, 18:29, 19:22 Berlin → **3/3 runs, 0 missed, delays 14 / 22 / 16 min (avg 17.4)**. |
| Box daemon `hf_runner.py` (60 s loop) | **The box freezes when no agent session/routine is active.** The process is paused, not killed (process age 7:36 after 13.5 min wall clock). Gaps: 7.1, 11.9, 6.6, 33.1 min → uptime ≈ 38% since start. One watchdog restart (heartbeat 390 s stale) at 19:23 Berlin. |
| Local web server | Survived ~2 h, but it also only runs while the box is awake. Not needed now that GitHub Pages is live. |
| Publishing | `git push` to the Pages repo works. Pages goes live ~15–60 s after a push. |
| Cost | €0 (box already provided). |

Conclusion: the box is reliable enough for an **hourly** 4h/1h strategy cycle (all runs happened, just late). It is **not** a 24/7 host for a 60 s loop.

## 2. GitHub Actions scheduled workflow (public repo)
Facts from the current GitHub docs (fetched 2026-10-13):
- **Cost:** standard GitHub-hosted runners are **free and unmetered for public repositories** (the 2,000 min/month quota applies only to private repos). Larger runners are always paid; do not use them.
- **Schedule:** POSIX cron, shortest interval **5 min**, optional IANA timezone. Docs: "*can be delayed during periods of high loads… High load times include the start of every hour. If the load is sufficiently high enough, some queued jobs may be dropped.*" → use an odd minute (e.g. `:07`, `:37`). Expect delays of minutes up to tens of minutes, and occasional dropped runs. The schedule is not guaranteed.
- **60-day rule:** "*In a public repository, scheduled workflows are automatically disabled when no repository activity has occurred in 60 days.*" Our hourly state commits count as activity, so this only bites if the bot stops committing. It can be re-enabled manually.
- **Terms (GitHub Additional Product Terms, Actions):** not allowed: cryptomining, disproportionate server burden, "don't use Actions as … part of a serverless application", and, on GitHub-hosted runners, "*any other activity unrelated to the production, testing, deployment, or publication of the software project associated with the repository*". "You may only access and use GitHub Actions to develop and test your application(s)."
  - **Assessment:** an hourly ~1-minute job that runs and tests our own open-source paper-trading software and publishes its dashboard is arguably "testing/publication of the software project". But it is a **grey zone**: a permanent scheduler for a bot is close to the "serverless application" example. A 5-minute HF loop (~8,600 runs/month) is much more likely to be seen as disproportionate. Risk: repo or Actions disabled. There is no financial risk, since no payment method is needed for public repos.
- **Network:** runners have unrestricted egress, so Hyperliquid's public API should work, but this is **not yet tested** from a runner. Runner IPs are US/Azure; the public info API is not geo-gated as far as we know, but verify with a single `workflow_dispatch` test.

### State storage via repo commits
- Each run: checkout → run cycle → commit `state/*.json`, the SQLite DBs and `public/*` back to the repo. Concurrent runs must be prevented with `concurrency: {group: cycle, cancel-in-progress: false}`.
- **Risks:**
  - Repo growth: binary SQLite rewrites each hour → ~1–3 MB/day. Switch to append-only JSONL or prune history.
  - Push races: retry with `git pull --rebase`.
  - All state becomes **public**. Fine here (no secrets), but the code would also be public.

### Security
- No secrets needed. Use the built-in `GITHUB_TOKEN` with `permissions: contents: write` only; no PAT on the runner.
- Pin actions by SHA. No `pull_request_target`. Disable Actions on forks' PRs (default).
- Nothing on the runner can trade: no keys exist, and the code has no order endpoints.

## 3. Comparison
| | Box hourly routine (now) | Box daemon 60 s | GitHub Actions hourly | GitHub Actions every 5 min |
|---|---|---|---|---|
| Cost | €0 | €0 | €0 (public repo) | €0 |
| Measured/expected reliability | 3/3 runs, avg 17 min late | ~38% uptime (freezes when idle) | Unverified; docs warn of delays and dropped runs | Worst; same delays, more drops |
| Wakes / AI credits | uses routine wakes | needs box awake | **no box/AI usage at all** | none |
| State | local + bot store mirror | local | public repo commits | public repo commits (big churn) |
| ToS risk | none | none | low–medium (grey zone) | medium–high |
| Fits strategies | 4h/1h ✔ | 5m only while awake | 4h/1h ✔ | 5m only marginally (late runs) |

## 4. Recommendation
1. **Keep the box hourly routine as the primary executor** for ACTIVE / SHADOW / TEST (4h/1h). It is verified, free and good enough. Lateness of ~15–20 min costs little on 1h/4h bars.
2. **Treat `hf_runner` as best-effort.** The 5m EXPERIMENTAL portfolio only trades while the box is awake, and the dashboard reports its uptime honestly. Do not try to make it 24/7 on the box.
3. **Optional, only with your approval:** a GitHub Actions *hourly* job (cron `37 * * * *`) as a **redundant backup**, not a replacement. Or migrate fully if box routine costs/credits become a concern. Do **not** run a 5-minute Actions loop (ToS + reliability).

## 5. What a migration to GitHub Actions would take (not done)
1. **New public repo** `gelddruckmaschine` (code) or reuse the dashboard repo. It must contain the code, `requirements.txt` (pandas, numpy, requests) and state. Audit that no box paths or secrets are present (none today).
2. **Make state portable:** move `state/*.json` + DBs into the repo, switch SQLite → JSONL (diff-friendly), remove the bot-store mirror and the box watchdog/tunnel from the Actions path.
3. **Workflow** `.github/workflows/cycle.yml`:
   ```yaml
   on: {schedule: [{cron: "37 * * * *"}], workflow_dispatch: {}}
   permissions: {contents: write}
   concurrency: {group: cycle, cancel-in-progress: false}
   jobs: {run: {runs-on: ubuntu-latest, timeout-minutes: 10, steps: [checkout, setup-python 3.12, pip install -r requirements.txt, "python cycle.py --trigger github-actions", commit & push state + public/ with retry]}}
   ```
4. **Single-writer rule:** if both box and Actions run, they would fork the state. Either Actions becomes the only writer, or it runs only when `data.json` is >90 min stale (backup mode).
5. **Test:** one `workflow_dispatch` run to confirm the Hyperliquid API from a runner, measure duration (~1–2 min) and repo growth. Then observe the schedule delay for ~3 days before relying on it.
6. **Effort:** ~1–2 h of agent work. Needs your OK to make the code public and to add a workflow (the gh token already has `workflow` scope).
