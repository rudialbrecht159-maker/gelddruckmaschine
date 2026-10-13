# Selbsttest Projekt 2.0 (13.10.2026, Zeiten Berlin) – SIMULIERT
Session 20261013-214635, €200, 15 min, funding-fade-4h-x1, GitHub Actions Standard-Runner.

| Schritt | Run-ID | Zeit | Ergebnis |
|---|---|---|---|
| START | 38473066803 | 23:46:20 | Session live nach ~15 s, BTC LONG eröffnet 23:46:55 (Stop 80.645,9), data.json über die Contents-API 23:48:00 |
| Crash (Run abgebrochen) | 38473066803 | 23:48:24 | cancelled, Zustand per final sync gesichert |
| Neustart → Resume | 38473412319 | 23:49:11 | gleiche Session, resumes=1, Position erhalten. Eingaben €999/5 min/trend wurden korrekt ignoriert |
| STOP | 38473610136 | 23:50:49 | **Engine-Bestätigung 23:50:53, Latenz 4,5 s** (Dispatch → Ack). Status „Beenden – offene Positionen werden verwaltet“ |
| close_all ohne confirm | 38473778911 | 23:52:15 | abgelehnt (Job failure, Run-Name „close_all REJECTED“), Engine ignoriert |
| close_all mit CLOSE ALL | 38473858705 | 23:52:56 | Ack 23:52:58 (2,7 s), Position geschlossen 23:53:18 (Markt-Fetch ~20 s), Session beendet |
| Bericht | – | 23:53:18 | Netto −€0,0621 (Brutto −€0,0109, Gebühren €0,0511), 1 Trade, 6,7 min, 2 Jobs, 0 Engine-Fehler |
