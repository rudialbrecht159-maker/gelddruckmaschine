# GELDDRUCKMASCHINE – Backtest-Bericht research5 (SIMULIERT, nur Forschung) – 13.10.2026
**Ein Framework für alle Strategien** (`framework.py`): ein gemeinsames 50-€-Konto pro Lauf mit Live-Limits (1 % Risiko, max. 3× Hebel, $10 Mindestorder, max. 2 Positionen, 3 % Tagesstopp, 10 % DD-Halt).
- **Ausführung:** Signal bei Kerzenschluss, Ausführung zur nächsten Eröffnung, Stop vor Take-Profit, Gaps zum Eröffnungskurs.
- **Kosten Taker:** 0,045 % Gebühr je Seite, 3 Bp Slippage, halber Spread, echtes stündliches Funding.
- **Kosten Maker (konservativ):** Limit zum Signal-Schlusskurs, gefüllt nur, wenn die nächste Kerze den Kurs um ≥ 1 Bp durchhandelt (sonst verpasst). 0,015 % Gebühr, Ausstiege als Taker.
- **Daten (echte Hyperliquid-Daten):**
  - 4h: 2024-07 → 2026-10 (OOS ab 2025-08-23, 14 Monate)
  - 1h: 2026-03 → 2026-10 (OOS ab 2026-07-01, 3,5 Monate)
  - 5m: 17 Tage, komplett, zu kurz für eine IS/OOS-Teilung
  - 15m (52 Tage) habe ich nicht separat getestet, weil keine Strategie diesen Zeitrahmen nutzt.
- **Walk-Forward:** Die Parameter waren vorab fixiert, nichts wurde neu optimiert. Die OOS-Hälfte ist in 4 aufeinanderfolgende Folds geteilt, jeder mit neuem Startkapital von 50 €.
- **Einschränkung:** S1–S3 und S5 wurden in früheren Runden auf Daten gewählt, die sich teilweise mit diesem OOS-Zeitraum überschneiden. Das OOS ist also nur teilweise „sauber“.
- **Mehrfachtests:** etwa 173 Konfigurationen insgesamt. Der Deflated Sharpe (DSR) berücksichtigt das; erst ab DSR ≥ 0,95 wäre ein Vorteil statistisch belegt.

Neue Ideen und Urteilsregel sind in PREREGISTRATION.md festgelegt.

## Ergebnisse OOS (Taker-Kosten, Live-Limits)
| Strategie | TF | OOS | Netto % | Brutto / Gebühren / Funding € | Gewinnquote % | PF | Sharpe | MaxDD % | Trades | Maker netto % | 2× Kosten netto % | Folds % | P(≤0) | DSR | Urteil |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1 trend-4h-v1 (aktiv) | 4h | 2025-08-23→2026-10-13 | 10.75 | 6.49 / 0.32 / 0.79 | 17.2 | 1.61 | 0.61 | 9.91 | 29 (2.1/Mon.) | 3.34 | -0.0 | -1.9 / -2.3 / 11.0 / 14.4 | 0.254 | 0.017 | **REWORK/OBSERVE** |
| S2 breakout-1h-v1 (Schatten) | 1h | 2026-07-01→2026-10-13 | -5.3 | -2.32 / 0.22 / 0.11 | 12.5 | 0.2 | -1.49 | 10.49 | 8 (2.3/Mon.) | -5.21 | -5.39 | -5.3 / -8.8 / -10.5 / 48.2 | 0.988 | 0.0 | **DISCARD** |
| S3 test-breakout1h-filtered | 1h | 2026-07-01→2026-10-13 | -10.8 | -5.1 / 0.32 / -0.02 | 7.7 | 0.02 | -4.38 | 10.8 | 13 (3.8/Mon.) | -10.93 | -10.79 | -10.8 / -7.3 / -8.5 / -1.6 | 1.0 | 0.0 | **DISCARD** |
| S4 test-hf-zscore-5m | 5m | 2026-09-27→2026-10-13 (gesamt, zu kurz für IS/OOS) | -10.01 | -3.46 / 1.55 / -0.0 | 30.8 | 0.34 | -7.91 | 10.01 | 26 (49.2/Mon.) | -9.97 | -10.78 | -10.0 / -8.0 / -10.7 / -8.6 | 0.988 | 0.0 | **DISCARD** |
| S5 funding-fade-4h-x1 | 4h | 2025-08-23→2026-10-13 | 22.19 | 11.3 / 0.4 / -0.2 | 48.6 | 2.66 | 1.69 | 5.16 | 35 (2.6/Mon.) | 22.85 | 21.65 | 0.1 / 0.5 / 13.2 / 8.3 | 0.026 | 0.157 | **KEEP** |
| N1 bbrev_1h | 1h | 2026-07-01→2026-10-13 | -8.91 | -3.65 / 0.86 / -0.05 | 40.6 | 0.5 | -2.61 | 10.02 | 32 (9.4/Mon.) | -11.03 | -10.22 | -8.9 / 1.1 / -0.1 / -1.1 | 0.975 | 0.0 | **DISCARD** |
| N2 donchian_adx_4h | 4h | 2025-08-23→2026-10-13 | 6.04 | 3.97 / 0.69 / 0.25 | 30.9 | 1.19 | 0.4 | 10.14 | 55 (4.0/Mon.) | -0.15 | 4.27 | 2.4 / 4.7 / -1.9 / -8.4 | 0.336 | 0.01 | **REWORK/OBSERVE** |
| N3 zmom_1h | 1h | 2026-07-01→2026-10-13 | -9.54 | -3.64 / 1.08 / 0.05 | 40.0 | 0.46 | -3.26 | 10.18 | 35 (10.2/Mon.) | -10.98 | -11.43 | -2.3 / -7.4 / -5.5 / 1.6 | 0.968 | 0.0 | **DISCARD** |

## Portfolio-Kandidat aus den Überlebenden (S1 + S5, gemeinsames 4h-Konto)
- **Korrelation:** Die täglichen Renditen von S1 und S5 im OOS korrelieren mit **0.163**. Das ist gering.
- **Kombiniert, OOS:** **13.25 %** netto, MaxDD 8.62 %, 50 Trades (3.7/Mon.), PF 1.5, Sharpe 0.83, P(≤0) 0.19, DSR 0.032.
- **Beiträge:** S1 -5.14 € in 24 Trades, S5 11.77 € in 26 Trades.
- **Folds:** [-1.77, 0.17, 12.28, 12.26]. Maker: 11.77 %.
- **IS (2024-07 → 2025-08):** 0.45 %, DD-Halt ausgelöst.

**Die Kombination ist schlechter als S5 allein** (+22,2 %, MaxDD 5,2 %). Im gemeinsamen Konto belegt S1 Positionsplätze, und sein Beitrag ist negativ. Eine Diversifikation durch Kombination lohnt sich hier also nicht.

## Wichtigste Befunde
1. **Kein statistisch belegter Vorteil.** Alle DSR-Werte liegen ≤ 0,16. Auch die beste Strategie (S5) ist nach Korrektur für etwa 173 Tests nicht signifikant.
2. **Nur S5 (Funding-Fade 4h) erfüllt die vorab festgelegte KEEP-Regel:** +22,2 %, PF 2,66, MaxDD 5,2 %, 35 Trades, 4/4 Folds ≥ 0, unempfindlich gegen doppelte Kosten. Aber: Auf den 8 Hold-out-Märkten aus research4 war S5 negativ (−3,3 %, 21 Trades).
3. **S1 trend-4h-v1 (aktiv) ist positiv, aber fragil:** +10,8 %, aber nur 29 Trades (<30), MaxDD 9,9 % (knapp unter dem Halt), 2 von 4 Folds negativ, bei doppelten Kosten ±0 %, mit Maker-Einstiegen nur +3,3 %.
4. **Die 1h- und 5m-Strategien (S2, S3, S4, N1, N3) lösen unter Live-Limits den 10-%-Halt aus** und sind im OOS negativ.
   - S2 und S3 sind ohne Halt zwar positiv, das hängt aber an der Altcoin-Rally im Sept./Okt. 2026 (Fold 4).
   - Das Ziel „häufiger handeln“ ließ sich bei diesen Kosten nicht mit Vorteil erreichen: N1 und N3 (9–10 Trades/Mon.) sind brutto negativ.
5. **Maker-Einstiege helfen nicht.** Bei konservativer Füllung (nur wenn der Kurs durch das Limit läuft) erwischt man vor allem die schlechten Fills (adverse Selektion). S1 fällt von +10,8 % auf +3,3 %, N2 von +6,0 % auf −0,15 %.
6. **Problem Mindestorder:** Mit 50 € und 3-ATR-Stops auf 4h liegen 1-%-Risiko-Positionen oft unter $10 und werden übersprungen. Abgelehnte Signal-Kerzen: S1 43, S5 110. Die Zähler sind pro Kerze und daher aufgebläht, aber ein großer Teil der Signale wird tatsächlich nicht handelbar. Die neue Engine muss diese Fälle sichtbar loggen. Das Limit darf dafür **nicht** heimlich erhöht werden.

## Phasen-Evaluator (Teil E)
`phases.py`, Unit-Tests: `tests/test_phases.py`, 9/9 bestanden. Die Tests nutzen **synthetische Testdaten**, keine Ergebnisse.

Als Backtest-Replay habe ich ihn auf S1+S5 ab Beginn des OOS angewendet (`phase_demo_backtest_replay.md`): P1 und P2 sind INCONCLUSIVE (0–1 Trades), P3 endet mit FAIL und `pause` (−0,30 €, 2 Trades).

Daraus folgt: **Strategien mit 2–4 Trades pro Monat können die ≥30-Trades-Hürde in 5 Wochen nie erreichen.** Für sie sollten die Phasen in Trades statt in Kalenderwochen gemessen werden, oder P3 auf etwa 6 Monate verlängert werden. Das ist eine Entscheidung für Rudi; im Code ist es per `phases=`-Parameter einstellbar.
