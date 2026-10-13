# Strategie-Urteile research5 (SIMULIERT) – 13.10.2026
Regel (vorab festgelegt): **KEEP** = OOS netto > 0, PF ≥ 1,2, ≥ 30 OOS-Trades, ≥ 3/4 Folds ≥ 0, kein Halt. **ÜBERARBEITEN/BEOBACHTEN** = netto > 0, aber ein Kriterium verfehlt (z. B. < 30 Trades). **VERWERFEN** = OOS netto ≤ 0 oder brutto ≤ 0.

## Behalten
- **S5 funding-fade-4h-x1:** KEEP, aber experimentell mit niedriger bis mittlerer Zuversicht.
  - OOS +22,2 %, PF 2,66, MaxDD 5,2 %, 35 Trades.
  - Einschränkungen: auf den Hold-out-Märkten negativ (research4), nicht signifikant (DSR 0,16), nur etwa 2,6 Trades/Monat.

## Überarbeiten / beobachten
- **S1 trend-4h-v1 (aktiv):** +10,8 % OOS, aber
  - nur 29 Trades (< 30),
  - 2/4 Folds negativ,
  - bei doppelten Kosten ±0 %,
  - MaxDD 9,9 % (fast am Halt),
  - viele Signale unter der $10-Mindestorder.

  Als Vergleichsbasis weiterlaufen lassen, nicht ausbauen. Mögliche Überarbeitung: engere Stops oder 1d-Filter, dann neu vorregistrieren.
- **N2 donchian_adx_4h:** Mit Halt +6,0 % (55 Trades), aber PF 1,19 < 1,2. Ohne Halt −6,6 %, die letzten 2 Folds negativ, mit Maker-Einstiegen −0,15 %. Faktisch kein Vorteil; nicht als Testportfolio starten.

## Verworfen
- **S2 breakout-1h-v1 (Schattenportfolio):** OOS −5,3 %, nach 8 Trades am 10-%-Halt gestoppt. Ohne Halt +74 %, aber das stammt aus 2 Trades der Altcoin-Rally (Fold 4: +48 %). Folds 1–3 negativ. Unter Live-Limits nicht tragfähig.
- **S3 test-breakout1h-filtered:** OOS −10,8 % (Halt), 13 Trades, PF 0,02, alle 4 Folds negativ.
- **S4 test-hf-zscore-5m:** −10,0 % (Halt), PF 0,34, alle Folds negativ, ohne Halt −31 %. Schon brutto negativ, die Kosten verschlimmern es nur.
- **N1 bbrev_1h (neu):** OOS −8,9 % (Halt), PF 0,5, auch in-sample −8,6 %. Mean Reversion ist in allen Runden negativ.
- **N3 zmom_1h (neu):** OOS −9,5 % (Halt), PF 0,46, in-sample −9,2 %. Kurzfristiges Momentum hat nach Kosten keinen Vorteil.
- **Kombination S1+S5:** Gering korreliert (0,16), aber schlechter als S5 allein (+13,3 % gegenüber +22,2 %). Nicht kombinieren.
