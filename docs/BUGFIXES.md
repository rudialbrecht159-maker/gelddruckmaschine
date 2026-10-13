# Behobene Fehler (Projekt 2.0)

1. **Session-Anzeige falsch (Dauer/Strategie):**
   - **Ursache:** Das Dashboard las `session.json` aus zwei Quellen (Box und Code-Repo) und zeigte die „neuere“. So erschien z. B. eine alte Session (10 min, 21:13) statt der laufenden (5 min, 21:24). Die Ist-Dauer wurde im Browser aus der Planzeit gerechnet.
   - **Fix:** Es gibt nur noch einen Store und ein `data.json`. Geplante und tatsächliche Dauer sowie die Strategie werden in `store.session_summary()` aus dem Datensatz der jeweiligen Session berechnet. Die Session-Liste zeigt alle Sessions einzeln.
2. **„attempt to write a readonly database“ (2 Engine-Fehler im ersten Actions-Test):**
   - **Ursache:** `git pull --rebase` ersetzte die offene `paper.db`.
   - **Fix:** `sync.sh` nutzt merge statt rebase, und die Engine-Dateien werden nie umgeschrieben. Zuerst in Commit 2a02dfa behoben, jetzt in `sync.sh` zentral.
3. **Falsches Trigger-Label:** Session-Loops wurden als „likely hourly routine“ geloggt. Fix: `GDM_TRIGGER=session`.
4. **Widersprüchliche data.json:**
   - **Ursache:** Der HF-Runner, der stündliche Zyklus und die Session schrieben je eigene Exporte.
   - **Fix:** Der Alt-Export schreibt nur noch `data_legacy.json` (nicht veröffentlicht). Veröffentlicht wird nur `store.build()`. `publish.sh hf` pusht nur noch `hf.json`.
5. **STOP-Latenz 1–2 min:**
   - **Ursache:** Die Kontrolle wurde nur einmal pro Loop über einen Commit des Control-Jobs gelesen (Runner-Start + Checkout + Commit).
   - **Fix:** Die Engine pollt alle 5 s die Workflow-Run-Liste (Run-Name kodiert die Aktion). Das Control-File bleibt als Fallback und Audit.
6. **Dashboard-Verzögerung durch Cache (~5 min bei raw.githubusercontent):** Das Dashboard liest primär über die GitHub-Contents-API (kein CDN-Cache), raw und Pages dienen als Fallback.
7. **Nicht-exponentielle Wiederholungen:** Hyperliquid-Requests nutzen jetzt exponentiellen Backoff mit Jitter (5 Versuche) und erkennen 429 (Rate-Limit).
8. **Limitverletzung nur als Einstiegssperre:** Ein Tagesverlust ≥ 3 % oder ein DD-Halt stoppt die Session jetzt automatisch (Status „Beenden“) und erzeugt einen roten Alarm im Dashboard.
9. **Kein Schutz gegen ungültige Stops:** Ein Einstieg ohne gültigen Stop-Loss (NaN oder auf der falschen Seite) wird abgelehnt und geloggt.
10. **Mindestorder-Skips unsichtbar:** Sie stehen jetzt pro Portfolio gezählt und gelistet im Dashboard-Tab „Aktivität“.
11. **Kein TP-Pfad:** TP wird jetzt ausgeführt, wo die Strategie ein Ziel definiert (`tp`/`tp_atr`). Die aktuellen Strategien definieren keines, deshalb gibt es auch kein künstliches TP.
