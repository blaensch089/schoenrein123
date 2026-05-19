# Recherche: Armbrustschützenzelt Reservierungsportal
**Datum:** 2026-05-18  
**URL:** https://reservierung.armbrustschuetzenzelt.de/reservierung

---

## Zusammenfassung

**Muster anwendbar: JA.** Das Armbrustschützenzelt nutzt exakt dasselbe Festzelt-OS/Livewire-Muster wie Bräurosl und Hacker-Festzelt. Kein Login erforderlich. 8 buchbare Daten (Mo–Do) vorhanden, alle mit einer einzigen Schicht ("Mittag"). Die `seatplan_area` bleibt leer — entweder gibt es keine Bereichsaufteilung oder sie erscheint erst nach weiteren Schritten im Wizard.

---

## Schritt-für-Schritt-Protokoll

### Schritt 1: GET /reservierung
- **HTTP-Status:** 200 OK
- **Final-URL:** https://reservierung.armbrustschuetzenzelt.de/reservierung
- **Server:** cloudflare (CF-Ray vorhanden, aber kein Challenge)
- **HTML-Länge:** 76.754 Zeichen
- **application-name:** `Festzelt OS` (im `<meta>`-Tag bestätigt)
- **Session-Cookies:** `XSRF-TOKEN` + `festzelt_os_session`
- **CSRF-Token:** vorhanden (`<meta name="csrf-token">`)
- **wire:snapshots:** 2 gefunden
  - Snapshot[0]: `app.portal.livewire.view-portal-page` — enthält `createBookingStepOneForm`, `booking_list_group_id=68`
  - Snapshot[1]: `notifications` (Filament-Komponente, irrelevant)
- **wire:ids:** `ccMSoyj15NnfaMBEvhVo`, `2Zpr3T3uWC6PrubAyqAi`
- **Daten im SELECT** (`id="data.createBookingStepOneForm.date"`): 8 Daten (s. Tabelle unten)
- **Login-Hinweise:** keine
- **Cloudflare-Challenge:** nein

### Schritt 2: POST /livewire/update (Datum 2026-09-21)
- **Livewire-URL:** https://reservierung.armbrustschuetzenzelt.de/livewire/update
- **HTTP-Status:** 200 OK
- **Response-Keys:** `components`, `assets`
- **HTML-Fragment-Länge:** 66.012 Zeichen
- **booking_list_id SELECT:** vorhanden — Option `2071` / Label **"Mittag"**
- **seatplan_area:** leer (Block existiert, aber keine Optionen)
- **Schichtzeiten:** keine Uhrzeit-Angaben im HTML (kein `HH:MM – HH:MM`-Muster)

### Schritt 3: Alle 8 Daten
Alle 8 Daten erfolgreich abgefragt (HTTP 200), keine Rate-Limits.

---

## Vergleichstabelle: Festzelt-OS-Parameter

| Merkmal                        | Bräurosl                                         | Hacker-Festzelt                                  | **Armbrustschützenzelt**                                  |
|-------------------------------|--------------------------------------------------|--------------------------------------------------|-----------------------------------------------------------|
| URL-Pfad                      | `/reservation/`                                  | `/reservierung`                                  | `/reservierung`                                           |
| booking_list_group_id         | 62                                               | 55                                               | **68**                                                    |
| Livewire-Endpoint             | `/livewire/update`                               | `/livewire/update`                               | `/livewire/update`                                        |
| component name                | `app.portal.livewire.view-portal-page`           | `app.portal.livewire.view-portal-page`           | `app.portal.livewire.view-portal-page`                    |
| CSRF + Snapshot ohne Login    | ja                                               | ja                                               | **ja**                                                    |
| Cloudflare-Challenge          | nein                                             | nein                                             | **nein** (CF-Ray vorhanden, kein Block)                   |
| Daten vorhanden               | 9 Daten                                          | 0 (Vergabe ab 19.05.2026)                        | **8 Daten** (Mo–Do)                                       |
| Schichten                     | mehrere (Mittag/Abend)                           | –                                                | **nur "Mittag"** (eine pro Tag)                           |
| seatplan_area                 | ja                                               | –                                                | **leer / nicht ausgefüllt**                               |
| Login erforderlich            | nein                                             | nein                                             | **nein**                                                  |

---

## Datum × booking_list_id × Schicht

| Datum       | Wochentag    | booking_list_id | Schicht-Label |
|-------------|--------------|-----------------|---------------|
| 2026-09-21  | Montag       | 2071            | Mittag        |
| 2026-09-22  | Dienstag     | 2074            | Mittag        |
| 2026-09-23  | Mittwoch     | 2077            | Mittag        |
| 2026-09-24  | Donnerstag   | 2080            | Mittag        |
| 2026-09-28  | Montag       | 2091            | Mittag        |
| 2026-09-29  | Dienstag     | 2094            | Mittag        |
| 2026-09-30  | Mittwoch     | 2097            | Mittag        |
| 2026-10-01  | Donnerstag   | 2100            | Mittag        |

**Muster der booking_list_ids:** +3 pro Tag innerhalb einer Woche (`2071 → 2074 → 2077 → 2080`), dann Sprung auf `2091` für die Folgewoche. Das entspricht dem bekannten 3er-Schritt-Muster von Festzelt OS.

**Fehlende Tage:** Fr (19.09, 25.09), Sa (20.09, 26.09), So (21.09 = Wiesn-Beginn erscheint als 1. Datum erst Mo 21.09?). Das Armbrustschützenzelt öffnet offenbar nur Mo–Do für Mittagsreservierungen, keine Wochenend-/Abendbelegung über dieses Portal. Der 4. Oktober 2026 (So, letzter Wiesn-Tag) fehlt ebenfalls.

---

## Snapshot-Struktur (Auszug)

```json
{
  "booking_list_group_id": 68,
  "date": "2026-09-21",
  "booking_list_id": null,
  "seatplan_area_id": null,
  "pax_options": null,
  "simple_pax_planned": null,
  "custom_start_time": null,
  "seatplan_group_id": null,
  "seatplan_element_ids": [[], {"s": "arr"}],
  "seatplan_element_pax": null,
  "pax_planned": null,
  "seatplan_elements_count_planned": null
}
```

---

## Offene Fragen

1. **Warum bleibt `booking_list_id` im Snapshot `null`** nach dem Update-Call? Das Select zeigt zwar Option 2071 an, aber der Snapshot übernimmt den Wert nicht — möglicherweise muss die Auswahl über einen anderen Mechanismus (z.B. `calls`-Array) gesetzt werden. Bei Bräurosl verhielt sich das anders.

2. **Nur eine Schicht "Mittag":** Gibt es auch Abendschichten? Die 8 angebotenen Tage sind alle Mo–Do. Das könnte bedeuten: (a) nur Mittagsreservierungen, (b) Abendschichten sind ausgebucht und wurden aus dem SELECT entfernt, oder (c) Fr/Sa/So-Daten werden separat verwaltet.

3. **seatplan_area leer:** Erscheint der Bereich-Selector erst nach tatsächlicher Auswahl von `booking_list_id` über das Browser-Frontend? Im Bot müsste ggf. ein weiterer POST mit gesetzter `booking_list_id` im `calls`-Array erfolgen.

4. **booking_list_ids 2081–2090** (Lücke zwischen 2080 und 2091): Möglicherweise Fr/Sa/So-Schichten, die nicht buchbar sind. Der Sprung von 10 Einheiten deutet auf Fr+Sa+So = 3 Tage × 3 IDs hin — wenn auch Abend existierte, wären es 6, aber der 10er-Sprung passt nicht exakt. Unklar.

5. **Kein Vergabe-Datum gefunden:** Im HTML kein expliziter Hinweis wie "Reservierungen ab XX.XX.XXXX". Der Buchungsstart könnte bereits offen sein (Daten sind sofort sichtbar).

---

## Empfehlung für Bot-Integration

Das Armbrustschützenzelt kann mit **identischem Code wie Bräurosl** überwacht werden:

```python
ZELTE = {
    "armbrustschuetzen": {
        "url": "https://reservierung.armbrustschuetzenzelt.de/reservierung",
        "booking_list_group_id": 68,
        "name": "Armbrustschützenzelt",
    }
}
```

**Hinweis zu seatplan_area:** Solange `seatplan_area_id` nicht befüllbar ist, kann der Bot nur auf Datum-Ebene prüfen ob booking_list_id-Optionen vorhanden sind (= Schicht buchbar). Eine Bereichs-Verfügbarkeit (wie bei Bräurosl) ist aktuell nicht abrufbar ohne tieferen Wizard-Schritt.

**Sofort umsetzbar:** Monitoring auf `booking_list_id`-Optionen pro Datum — erscheint ein neuer Wert oder verschwindet einer, ist das ein Signal. Alle 8 Daten haben genau eine Schicht ("Mittag"), daher ist die Logik einfacher als bei Bräurosl.
