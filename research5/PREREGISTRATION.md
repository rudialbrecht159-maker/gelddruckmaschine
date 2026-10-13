# research5 pre-registration (2026-10-13 23:10 CEST, before any research5 result)
Framework: framework.py (shared €50 account, live limits, taker and conservative-maker fee modes, funding, slippage, half-spread).
Existing strategies are re-tested with their ALREADY-FIXED params (no re-tuning). OOS = last 50% of each timeframe's data;
walk-forward consistency = OOS split into 4 consecutive folds (each restarts with €50). Note: for S1-S3/S5 the params were
chosen in earlier rounds using data that overlaps part of this OOS -> OOS is only partly "clean".
New ideas (3 configs, fixed, trials total ≈ 170 + 3 = 173):
N1 bbrev_1h  vol-filtered mean reversion: 4h trend dir (EMA50/200 from complete 4h blocks); long if dir>0 and close < SMA20-2SD and
             ATR%(1h) < its prior-500-bar 70th pct; short mirror; exit close crosses SMA20; stop 2 ATR; max hold 24 bars.
N2 donchian_adx_4h  regime-filtered trend: 4h close breaks 20-bar high/low and ADX14 > 25; exit 10-bar opposite channel; stop 2 ATR.
N3 zmom_1h  momentum: z = ret6 / (std(1h returns,168)*sqrt(6)); long z>2 with 4h dir>0, short z<-2 with dir<0; stop 1.5 ATR, TP 3 ATR, max hold 12 bars.
All new: expected-edge gate = stop distance >= 5x round-trip taker cost.
Verdict rule: KEEP = OOS taker net>0, PF>=1.2, >=30 OOS trades, >=3 of 4 folds >=0, not halted. REWORK/OBSERVE = OOS net>0 but fails a criterion
(incl. <30 trades). DISCARD = OOS net<=0 or gross<=0 under taker costs.
Portfolio: survivors (KEEP or REWORK with OOS net>0) combined on the 1h timeline in one account if daily-return correlation < 0.5.
