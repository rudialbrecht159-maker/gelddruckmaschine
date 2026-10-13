# Phasenbewertung – BACKTEST-REPLAY S1+S5 (kein Live-Ergebnis) (SIMULIERT, Paper-Trading)
Start: 2025-08-23 00:00 UTC · Bewertet: 2025-11-26 00:00 UTC · Startkapital: 50.0 €

**Empfehlung:** PAUSE: Phase P3 nicht bestanden (net_positive, robust_net, min_trades). Keine neuen Einstiege; Ursachen prüfen, Strategie überarbeiten oder verwerfen.  
**Aktion:** `pause`

| Phase | Zeitraum | Status | Netto € | Trades | MaxDD % | Netto − bester Trade € | Netto>0 | ≥30 Trades | DD<10 % | Robust |
|---|---|---|---|---|---|---|---|---|---|---|
| P1 | 2025-08-23 00:00 UTC → 2025-08-30 00:00 UTC | INCONCLUSIVE | 0.0 | 0 | 0.0 | 0.0 | ❌ | ❌ | ✅ | ❌ |
| P2 | 2025-08-30 00:00 UTC → 2025-09-13 00:00 UTC | INCONCLUSIVE | 0.01 | 1 | 0.65 | 0.01 | ✅ | ❌ | ✅ | ✅ |
| P3 | 2025-09-13 00:00 UTC → 2025-09-27 00:00 UTC | FAIL | -0.3 | 2 | 1.89 | -0.3 | ❌ | ❌ | ✅ | ❌ |

## Ursachenanalyse P3
Brutto -0.56 € · Gebühren 0.02 € · Funding 0.06 € · Kostenanteil am Brutto: None

- Bruttoergebnis ≤ 0: die Signale selbst haben keinen Vorteil (nicht nur Kosten).
- Schwächste Strategie: S1 (-0.65 € in 2 Trades).
- Schwächster Coin: BTC (-0.37 €).

| Strategie | Trades | Netto € | Gewinnquote % |
|---|---|---|---|
| S1 | 2 | -0.65 | 0.0 |

| Coin | Trades | Netto € | Gewinnquote % |
|---|---|---|---|
| BTC | 1 | -0.37 | 0.0 |
| SUI | 1 | -0.28 | 0.0 |

| Ausstiegsgrund | Trades | Netto € | Gewinnquote % |
|---|---|---|---|
| signal | 2 | -0.65 | 0.0 |

Hinweis: Kriterien werden kumuliert ab Start bewertet. In P1/P2 gelten <30 Trades oder ein Ergebnis, das an einem Trade hängt, als INCONCLUSIVE (kein Fehler); ab P3 führt Letzteres zur Pause.