# GELDDRUCKMASCHINE 2.0 – Paper-Trading (SIMULATION)

> **Nur Paper-Trading.** Virtuelles Geld, echte öffentliche Hyperliquid-Marktdaten. Keine Wallet, keine Keys, keine echten Orders, keine Kosten.

Dashboard: https://rudialbrecht159-maker.github.io/gelddruckmaschine-dashboard/
Steuerung: https://github.com/rudialbrecht159-maker/gelddruckmaschine/actions/workflows/session.yml

## Aufbau (eine Quelle der Wahrheit)
| Teil | Datei | Aufgabe |
|---|---|---|
| Konfiguration | `config.json` | **eine** Konfigurationsdatei: Kapital, Strategieliste, Dauer (0 = unbegrenzt), Hebel-Obergrenze, Risiko-Limits, Plug-ins, Urteile |
| Store | `store/` | **ein** Zustandsspeicher: `store/sessions/<id>/…` (Actions-Sessions), `store/box/portfolios.json` (stündliche Box-Portfolios) |
| Export | `store.py` → `public/data.json` | **eine** exportierte Datei. Dashboard, Berichte und Bot lesen nur diese. |
| Engine | `cycle.py` (Marktdaten, Stops, TP, Signale, Risiko) + `session.py` (Session-Ablauf) | gleiche Engine und Limits für alle Portfolios |
| Ausführung | `.github/workflows/session.yml` | GitHub Actions führt Sessions aus (Standard-Runner, ein Job, ≤ 170 min) |
| Plug-ins | `plugins.py` | Strategie-Module und Phasen-Evaluator aus `research5/` |

## Installation (lokal, optional)
```bash
git clone https://github.com/rudialbrecht159-maker/gelddruckmaschine && cd gelddruckmaschine
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python session.py start --capital 100 --minutes 10 --strategy funding-fade-4h-x1   # lokal, ohne Sync
```
Für den normalen Betrieb ist nichts zu installieren. Sessions laufen in GitHub Actions.

## Start (iPhone/iPad)
1. Dashboard öffnen und unten **▶ START** tippen. GitHub öffnet „trading-session“ (in der GitHub-App oder in Safari, angemeldet).
2. **Run workflow** tippen und eintragen: `action = start`, `capital`, `minutes` (1–180 oder 0 = unbegrenzt), `strategy`. `chain` bleibt aus.
3. Grünes **Run workflow** tippen. Nach etwa 30–60 s ist die Session im Dashboard live (grüner Punkt „Session-Engine live“).

Die Werte erzeugt das Einstellungs-Panel im Dashboard. Per CLI:
`gh workflow run session.yml -R rudialbrecht159-maker/gelddruckmaschine -f action=start -f capital=200 -f minutes=15 -f strategy=funding-fade-4h-x1`

## Stop
- **■ STOP**, dann Run workflow mit `action = stop`. Die Engine liest alle 5 s die Workflow-Runs (nur lesend, mit dem GITHUB_TOKEN des Jobs) und erkennt den STOP, sobald GitHub den Run angelegt hat.
- Danach gibt es keine neuen Einstiege mehr. Offene Positionen laufen mit ihren Regeln (Stop/TP/Signal) weiter, und die Session endet automatisch, sobald alles geschlossen ist.
- Das Dashboard zeigt **„STOP bestätigt um HH:MM:SS“** samt gemessener Latenz.

## Notfall-Close
- Roter **NOTFALL CLOSE**-Button. Im Dialog `CLOSE ALL` eintippen, dann in GitHub `action = close_all` und `confirm = CLOSE ALL` eingeben.
- Ohne exakte Bestätigung wird der Befehl abgelehnt (Run-Name „close_all REJECTED“, Job rot).
- Mit Bestätigung schließt die Engine alle Paper-Positionen sofort zum Marktpreis inklusive Kosten und beendet die Session.

## Konfiguration (`config.json`)
- `session.capital_eur`, `session.strategy`, `session.duration_min` (0 = unbegrenzt) und `session.strategies` (Session-Auswahl: `funding-fade-4h-x1` S5 experimentell, `trend-4h-v1` S1).
- `session.loop_s` (60), `control_poll_s` (5), `sync_every_s` (60), `job_budget_min` (170), `chain_jobs` (false), `max_chain` (3).
- `leverage_cap` (Standard 3), `leverage_hard_max` (5). Werte über 5 werden im Code auf 5 begrenzt.
- Die Risiko-Limits bleiben unverändert: `risk_per_trade` 1 %, `daily_loss_stop` 3 %, `max_drawdown_halt` 10 %, `max_positions` 2, Mindestorder $10.
- `strategy_verdicts`: Urteile aus research5. S2, S3 und S4 sind **verworfen**. Sie laufen stündlich unverändert weiter und sind im Dashboard als verworfen markiert.
- `plugins`: Andockpunkt für Strategie-Sets (`STRATEGIES`-Dict) und den Phasen-Evaluator (`research5/phases.py`).

## „Unbegrenzt“ ehrlich erklärt
GitHub-Jobs dürfen höchstens 6 h laufen, und die Nutzungsbedingungen erlauben Actions nur für Entwicklung, Test und Veröffentlichung des Repos, nicht als Dauer-Server.
- **Standard:** Eine unbegrenzte Session läuft bis zum Job-Budget (170 min) und geht dann in **„Pausiert“**. Der Zustand ist gespeichert, offene Positionen bleiben mit Stop stehen.
- Der nächste START setzt die Session fort. Stops, die in der Pause getroffen wurden, werden anhand der 1h-Kerzen nachträglich korrekt ausgeführt (zum Stop-Kurs oder bei einer Lücke zum Eröffnungskurs).
- **Opt-in `chain`** (Standard AUS): Am Job-Limit startet der Job selbst einen Folge-Job (höchstens `max_chain` = 3). Das ist bewusst ausgeschaltet, weil eine Dauerkette von Actions-Jobs gegen die Nutzungsbedingungen verstoßen kann.

## Sicherheit
- Steuern kann nur, wer Schreibrechte am Repo hat (GitHub-Login).
- Kein persönlicher Token in Secrets, nur der automatische GITHUB_TOKEN.
- Veröffentlicht werden nur Paper-Statistiken.
