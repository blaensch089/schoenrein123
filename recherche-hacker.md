# Recherche: Hacker Festzelt Reservierungsportal

**Datum:** 18. Mai 2026  
**Portal:** https://reservierung.derhimmelderbayern.de  
**Frage:** Ist das Bräurosl-Livewire-Muster 1:1 anwendbar?

---

## Zusammenfassung

**Ja — das Bräurosl-Muster ist fast 1:1 anwendbar.**

Das Hacker-Festzelt nutzt dieselbe **Festzelt OS**-Plattform mit identischem Livewire-v3-Backend. Der einzige Unterschied zur aktuellen Stunde: das Buchungsformular ist noch nicht freigeschaltet — laut Seitentext erscheinen die Termine erst **ab 19. Mai 2026 10:00 Uhr**. Das Livewire-Framework funktioniert aber bereits vollständig: Livewire-POSTs liefern HTTP 200, der Snapshot nimmt das gesetzte Datum entgegen, und `booking_list_id`-Optionen werden erscheinen, sobald der Admin Termine anlegt.

**Login ist für das Slot-Monitoring NICHT nötig.** `/reservierung` ist öffentlich zugänglich (HTTP 200 ohne Authentifizierung). Nur `/meine-buchungen` erfordert Login (Redirect auf `/login`).

| Merkmal | Bräurosl | Hacker Festzelt |
|---|---|---|
| Framework | Festzelt OS | Festzelt OS |
| Livewire | v3 | v3 |
| Component-Name | `app.portal.livewire.view-portal-page` | `app.portal.livewire.view-portal-page` |
| Reservierungs-URL | `/reservation/` | `/reservierung` |
| booking_list_group_id | 62 | **55** |
| Login für Slot-Check | nicht nötig | **nicht nötig** |
| Login für Buchung | nicht nötig | nötig (Livewire `data.email` / `data.password`) |
| Termine sichtbar | ja (9 Daten im HTML) | nein (noch nicht freigeschaltet) |

---

## Schritt-für-Schritt-Protokoll

### Schritt 1a: GET auf Portal-Root

```
GET https://reservierung.derhimmelderbayern.de/
Status: 200
Server: cloudflare
CF-Ray: vorhanden (kein Challenge)
HTML-Länge: 59.478 Zeichen
Cookies: XSRF-TOKEN, festzelt_os_session
CSRF-Token: GEFUNDEN
wire:snapshots: 2
```

**Befund:** Die Root-Seite (`/`) enthält ein `createBookingStep: 1` im Snapshot, aber **kein** `createBookingStepOneForm`-Formular im HTML. Das Formular liegt auf `/reservierung`.

### Schritt 1b: GET auf /reservierung

```
GET https://reservierung.derhimmelderbayern.de/reservierung
Status: 200
HTML-Länge: 58.665 Zeichen
wire:snapshots: 2
```

**Snapshot[0] Inhalt (relevant):**
```json
{
  "createBookingStepOneForm": [{
    "booking_list_group_id": 55,
    "date": null,
    "booking_list_id": null,
    "seatplan_area_id": null,
    ...
  }]
}
```

**Component-Name:** `app.portal.livewire.view-portal-page`  
**Memo-Path:** `reservierung`  
**Wire-ID:** `2PaCKUpdHzMGlo48FWAO`

**Sichtbarer HTML-Inhalt:**
```
Reservierungen Oktoberfest 2026
Wir stellen in regelmäßigen Abständen neue Reservierungsmöglichkeiten online.
Sollte aktuell kein Termin verfügbar sein, bearbeiten wir noch vorherige Anfragen
oder es bestehen derzeit keine freien Kapazitäten.
Wir vergeben das Münchner Kontingent am: 19. Mai 2026 ab 10:00 Uhr
```

Keine `<select>`-Elemente und keine `<option>`-Tags im Initial-HTML — Buchungsformular noch nicht gerendert.

### Schritt 2: Livewire-POST

```
POST https://reservierung.derhimmelderbayern.de/livewire/update
Headers: Content-Type: application/json, X-Livewire: true,
         X-CSRF-TOKEN: <token>, Referer: /reservierung
Body: {"components": [{"snapshot": "<snap>",
       "updates": {"data.createBookingStepOneForm.date": "2026-09-19"},
       "calls": []}]}

Status: 200
Response-Keys: ["components", "assets"]
HTML-Fragment-Länge: 43.800 Zeichen
```

**Wichtiger Hinweis zum 419-Fehler:** Ein erster Versuch mit der gespeicherten HTML-Datei aus einer alten Session lieferte HTTP 419 (CSRF Mismatch). Korrekte Lösung: GET und POST in **derselben Session** ausführen — dann HTTP 200.

**Response-Analyse:**
- Neuer Snapshot enthält `"date": "2026-09-19"` → Datum wurde korrekt gesetzt
- `booking_list_id` bleibt `null` → keine Buchungslisten für dieses Datum freigeschaltet
- HTML-Fragment enthält dasselbe Info-HTML ("Münchner Kontingent am 19. Mai")
- `<select id="data.createBookingStepOneForm.booking_list_id">`: **nicht vorhanden**

### Schritt 3: Weitere Daten testen

| Datum | Status | booking_list_id Optionen | Snapshot date gesetzt? |
|---|---|---|---|
| 2026-09-19 | 200 | — | ja |
| 2026-09-20 | 200 | — | ja |
| 2026-09-26 | 200 | — | ja |
| 2026-10-03 | 200 | — | ja |
| 2025-09-20 | 200 | — | ja (akzeptiert beliebige Daten) |
| 2023-01-01 | 200 | — | ja (akzeptiert beliebige Daten) |

Alle Requests HTTP 200, kein Rate-Limiting (429). Die API nimmt jedes Datum entgegen und antwortet konsistent — Formular wird erst gerendert, wenn das Datum in der Admin-DB als verfügbar hinterlegt ist.

### Vergleich mit Bräurosl (Kontrollmessung)

```
GET https://reservierung.braeurosl.de/reservation/
booking_list_group_id: 62
Verfügbare Daten im HTML: 2026-09-22, -23, -24, -27, -28, -29, -30, 2026-10-01, -02

POST mit date=2026-09-22
→ booking_list_id Option: [('1917', '')]
→ Datums-Options nach POST: [2026-09-22, -23, -24, -27, -28] (identisches Pattern)
```

---

## Tabelle: Datum × Schichtzeit × booking_list_id (aktueller Stand)

Da das Hacker-Portal noch keine Termine freigeschaltet hat, ist diese Tabelle derzeit leer. Sie wird befüllt, sobald das Kontingent am **19. Mai 2026 ab 10:00 Uhr** freigeschaltet wird.

| Datum | Schichtzeit | booking_list_id | booking_list_label |
|---|---|---|---|
| (noch keine) | — | — | — |

---

## Login-Analyse

| Endpunkt | Status | Verhalten |
|---|---|---|
| `/reservierung` | 200 | Öffentlich zugänglich, kein Login |
| `/meine-buchungen` | 200 (redirect) | Redirect auf `/login`, Login erforderlich |
| `/login` | 200 | Livewire-Formular mit `data.email` + `data.password` |

**Login-Komponente:** `app.portal.livewire.auth.login`  
**Livewire-Action:** `wire:submit.prevent="authenticate"`  
**Felder:** `data.email`, `data.password`

Das Login-Formular ist **Livewire-basiert** (kein klassisches HTML-Form mit POST-Action). Für reine Slot-Überwachung ist kein Login nötig.

---

## Code-Anpassungen für den Bot

Der bestehende Bräurosl-Code ist fast unverändert wiederverwendbar. Nur folgende Konstanten müssen geändert werden:

```python
# Bräurosl:
BASE_URL = "https://reservierung.braeurosl.de/reservation/"
BOOKING_LIST_GROUP_ID = 62  # implizit im Snapshot

# Hacker Festzelt:
BASE_URL = "https://reservierung.derhimmelderbayern.de/reservierung"
BOOKING_LIST_GROUP_ID = 55  # implizit im Snapshot
```

**Livewire-URL:**
```python
# Bräurosl → /livewire/update (same domain)
# Hacker   → /livewire/update (same domain, identisch)
```

**Datums-Erkennung:** Bei Bräurosl kommen die Daten aus dem Initial-HTML (Option-Tags). Beim Hacker wahrscheinlich ebenfalls — sobald der Admin Termine anlegt, erscheinen sie in identischer HTML-Struktur. Der Parser `re.findall(r'<option[^>]+value="(\d{4}-\d{2}-\d{2})"', html)` funktioniert für beide.

**Session-Management:** Identisch. GET → Session-Cookies → POST mit X-CSRF-TOKEN aus meta-Tag.

---

## Offene Fragen

1. **Wie genau sieht das Formular aus, wenn Termine freigeschaltet werden?**  
   Derzeit keine Daten verfügbar. Nach 10:00 Uhr am 19. Mai 2026 prüfen ob booking_list_id-Options erscheinen.

2. **Gibt es eine Datums-SELECT mit IE-Conditional-Comments (wie bei Bräurosl)?**  
   Bei Bräurosl kamen Options teils in IE-Conditional-Comments. Beim Hacker bisher nicht getestet weil noch keine Daten freigeschaltet.

3. **Sind mehrere Schichten pro Tag möglich?**  
   Bräurosl hat eine booking_list_id pro Datum ohne Zeitanzeige. Beim Hacker unbekannt bis Freischaltung.

4. **XSRF-TOKEN-Cookie vs. X-CSRF-TOKEN-Header:**  
   Funktioniert mit dem meta-Tag-CSRF-Token (X-CSRF-TOKEN). Der XSRF-TOKEN-Cookie ist URL-encoded und nicht direkt nutzbar als Header-Wert.

5. **Rate-Limiting:**  
   Bei 6 Requests mit je 3 Sekunden Pause kein 429 — aber ab Freischaltung mit mehr Traffic möglicherweise engerer Limit.

---

## Empfehlung

**Sofort umsetzbar:** Den Bräurosl-Monitor-Code für Hacker Festzelt klonen mit:
- `BASE_URL = "https://reservierung.derhimmelderbayern.de/reservierung"`
- `BOOKING_LIST_GROUP_ID = 55` (fest im Snapshot)

**Am 19. Mai 2026 ab 10:00 Uhr** einen manuellen Test-Run starten um zu verifizieren, dass booking_list_id-Optionen korrekt erscheinen und die Datums-Erkennung funktioniert. Danach regulären Polling-Betrieb aufnehmen.

Der Code ist **fast 1:1 wiederverwendbar** — kein Login nötig, identisches Livewire-Pattern, identische API-Endpunkte. Einziger potenzieller Unterschied: ob das Datum-SELECT im Initial-HTML oder erst per Livewire-POST geladen wird. Das klärt sich nach der Freischaltung.
