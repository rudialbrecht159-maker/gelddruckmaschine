# GELDDRUCKMASCHINE: SIMULATED paper-trading engine
**Paper trading only.** Virtual money, public Hyperliquid market data, no API keys, no wallet, no real orders (the code has no order endpoints).

- `session.py`: Trading Session Mode (user-set virtual capital and duration, one existing strategy, same risk limits: 1% risk/trade, 3% daily stop, 10% drawdown halt, max 2 positions, 3x cap, $10 min).
- `.github/workflows/session.yml`: run a session from GitHub (Actions → trading-session → Run workflow). Only the repo owner can trigger it.
- Session state is committed to `sessions/`; the live view is `public/session.json`, shown on https://rudialbrecht159-maker.github.io/gelddruckmaschine-dashboard/
- `docs/`: architecture and session-mode notes. Backtests are not a guarantee; all results are hypothetical.
