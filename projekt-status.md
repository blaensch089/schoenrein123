# Wiesn-Bot — Projekt-Status

**Stand: 17.05.2026 (Ende Tag 7)**

Diese Datei ist die Schnell-Übersicht für Claude beim Start einer neuen Session.
Vor allem anderen zuerst lesen — danach erst in den Skill oder ältere Chats schauen.

---

## Wo der Bot gerade steht

- **Läuft 24/7 in der Cloud, stündlich 6-22 Uhr München.**
- Trigger: cron-job.org (extern, zuverlässig). GitHub-interner Cron ist deaktiviert.
- 4 Zelte werden überwacht: Schottenhamel, Schützenfestzelt (mit Login), Marstall, Weinzelt.
- Cache wird täglich um 5:00 Uhr München automatisch refresht (separater Workflow).
- State überlebt zwischen Läufen (via `dawidd6/action-download-artifact@v6`).
- Bei neuen UIDs ohne Cache-Eintrag: Push mit "⚠️ Uhrzeit unbekannt".
- Bei ≥10 neuen UIDs gleichzeitig: Bulk-Summary statt Einzel-Pushes.

## Letzter committed Stand
- Bot-Workflow: Commit `19f7e9d` (cron-job.org übernimmt Trigger, GitHub-Cron deaktiviert)
- Refresh-Workflow: Commit `3b5e2b3` (Schritt B)
- Caches im Repo: 19+37+11+9 Einträge (Schottenhamel, Schützenfestzelt, Marstall, Weinzelt)

## Offene Punkte (Priorisierung wenn Chris fragt)

1. **Etappe 4 — Livewire-Zelte einbauen** (6 Stück): Hacker, Bräurosl, Armbrustschützen, Löwenbräu, Winzerer Fähndl, Ochsenbraterei. Brauchen Session + CSRF-Token. Eigene Session, größerer Aufwand.
2. **Etappe 5 — Augustiner Festhalle**: eigenes System.
3. **E-Mail-Backup** (To-do 3): unabhängiger, überschaubarer Brocken.
4. **README.md** für Wiederverwendung Wiesn 2027 — am Projektende schreiben.

## Mögliche Optimierungen (nicht akut)

- **Cache nie schrumpfen lassen** — aktuell wird Cache beim Refresh überschrieben. Wenn Schichten aus der API verschwinden (vergeben), gehen ihre Uhrzeiten verloren. Bei späterem Wiederauftauchen (Storno) kann der Bot sie nicht klassifizieren und pusht "Uhrzeit unbekannt". Lösung: Cache nur erweitern. Wert besprechen wenn es Chris wirklich beißt.
- **Schützenfestzelt 37 Schichten alle mit Status `requested`** — Bedeutung unklar (vermutlich "bereits angefragt/blockiert"). Chris will trotzdem alle Pushes haben. Liberal-Filter erfüllt das.
- **Phantom-Verfügbarkeit** — Tische im Portal sind nicht garantiert frei (Chris hat schon Absagen bekommen). Treffer = Kandidaten, keine Garantie.

## Wichtige Eigenheiten / Stolpersteine

- **WSL/Claude Code:** EINEN Schritt pro Antwort, nie mehrere Befehle stapeln (Chris' ausdrücklicher Wunsch).
- **Geheime Werte NIE im Chat zeigen.** Sternchen-Zensur empfehlen. (Vorfall an Tag 6: Klartext-Passwort + Kundennummer in Chat → Passwort geändert.)
- **NIEMALS Passwörter in Debug-Outputs** — auch nicht in Request-Body-Dumps. Maskieren.
- **Claude Code neigt zu voreiligen "alles funktioniert"-Schlüssen.** Mehrfach passiert. Chris' eigene Beobachtungen (Screenshots, was er im Portal sieht) haben Vorrang vor Code-Analyse-Theorien.
- **git push aus WSL:** Username + PAT jedes Mal. Claude Code kann NICHT autonom pushen.
- **PAT für Push:** Classic, scopes `repo`+`workflow`, läuft ~Mitte August 2026 ab.
- **PAT für cron-job.org (Workflow-Trigger):** Fine-grained, nur Repo `wiesn-bot`, nur `Actions: Read and write`, läuft 15.08.2026 ab.
- **urllib vermeiden:** Cloudflare blockt User-Agent `Python-urllib/3.14`. Außerdem zerlegt `urllib.add_header()` Header-Namen via `.capitalize()` → `Content-Type` wird `Content-type` → Backends können das ablehnen. Daher überall `requests` verwenden.
- **Schützenfestzelt-Login:** POST `/lp/auth/login` mit `{"customer_number","password"}` (NICHT E-Mail). Token in `response.data.token`. JWT, 30 Min gültig, kein Refresh. Cloudflare verlangt Browser-User-Agent.
- **cron-job.org-Trigger:** sendet POST an `https://api.github.com/repos/blaensch089/wiesn-bot/actions/workflows/check.yml/dispatches`, Body `{"ref":"main"}`, 4 Header. Bei roter "Verifikation"-Meldung im UI: F5 oder neu einloggen.

## Kommunikationsstil mit Chris

- Auf Deutsch antworten.
- EIN Schritt pro Antwort.
- Befehle erklären, kein unerklärter Jargon.
- Bei zu kopierendem Code: Codeblock.
- Klare Aussagen treffen, auch wenn unbequem.
- Chris hat keine Coding-Erfahrung — entsprechend ausführlich erklären.
