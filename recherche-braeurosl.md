# Recherche: Bräurosl Livewire-Reservierungsseite

## Zusammenfassung

Die Bräurosl-Reservierungsseite (reservierung.braeurosl.de) nutzt Laravel Livewire v3 und lässt sich **komplett ohne Login** ansprechen. Die Verfügbarkeit wird nicht als numerische Restplatzzahl exponiert, sondern als schrittweise ausfüllbares Formular: Datum → Schicht → Sitzbereich → Tischanzahl. Ein freies Angebot bedeutet, dass Optionen im SELECT-Feld erscheinen (belegt = SELECT leer oder Option nicht vorhanden). Die Buchungslogik basiert auf `booking_list_group_id=62` (fest für Bräurosl) und 10 buchbaren Daten für Oktoberfest 2026, alle mit nur einer "Mittag"-Schicht (11:00–16:45 Uhr).

---

## Schritt-für-Schritt-Protokoll

### Schritt 1 — GET https://reservierung.braeurosl.de/reservation/

**HTTP-Status: 200**

Cookies gesetzt:
- `XSRF-TOKEN`: (JWT-ähnlicher Base64-Wert, gültig 2h)
- `festzelt_os_session`: (verschlüsselte Session)

CSRF-Token im `<meta name="csrf-token">` gefunden.

Livewire-Komponenten im HTML:
- `wire:id` (2 IDs gefunden): Hauptkomponent `app.portal.livewire.view-portal-page` und `notifications`
- `wire:snapshot` (2 Stück): vollständige Zustandsdaten

Snapshot[0] nach JSON-Parse:
```json
{
  "memo": {
    "name": "app.portal.livewire.view-portal-page",
    "id": "<dynamisch>"
  },
  "data": {
    "createBookingStep": 1,
    "createBookingStepOneForm": {
      "booking_list_group_id": 62,
      "date": null,
      "booking_list_id": null,
      "seatplan_area_id": null,
      "pax_options": null,
      ...
    }
  }
}
```

`booking_list_group_id=62` ist fest vorbelegt (Bräurosl-spezifisch).

`memo.methods` ist leer (Livewire v3 serverseitig, keine Client-Methoden-Exposition).

Keine `uid`, keine `start_at`/`end_at`-Felder im initialen Snapshot.

HTML-Datei gespeichert: 77.155 Zeichen.

---

### Schritt 2 — Livewire-POST: Datum setzen

**POST https://reservierung.braeurosl.de/livewire/update**

Payload:
```json
{
  "components": [{
    "snapshot": "<decoded snapshot>",
    "updates": {"data.createBookingStepOneForm.date": "2026-09-22"},
    "calls": []
  }]
}
```

**HTTP-Status: 200**

Response-Struktur:
```json
{
  "components": [{
    "snapshot": "<neues JSON>",
    "effects": {
      "returns": [],
      "html": "<vollständiges HTML der Seite>"
    }
  }],
  "assets": []
}
```

Nach Datumssetzung erscheint im SELECT für `booking_list_id` exakt eine Option: `value="1917"` → **"Mittag"**.

Alle 10 verfügbaren Oktoberfest-2026-Daten (aus dem Datums-SELECT):
- 2026-09-22 (Di), 2026-09-23 (Mi), 2026-09-24 (Do)
- 2026-09-27 (So), 2026-09-28 (Mo), 2026-09-29 (Di), 2026-09-30 (Mi)
- 2026-10-01 (Do), 2026-10-02 (Fr), 2026-10-04 (So)

**Beobachtung:** 2026-09-25 (Fr), 2026-09-26 (Sa) und 2026-10-03 (Sa) fehlen — Samstag/Freitag haben keine buchbaren Schichten (oder sind bereits ausgebucht/nicht freigeschaltet).

---

### Schritt 3 — booking_list_id setzen

**POST mit** `"data.createBookingStepOneForm.booking_list_id": 1917`

**HTTP-Status: 200**

SELECT für `seatplan_area_id` erscheint mit 4 Optionen:
| ID  | Bereich           |
|-----|-------------------|
| 629 | Boxen             |
| 630 | Brauerei Box      |
| 632 | Mittelschiff Ost  |
| 634 | Mittelschiff West |

---

### Schritt 4 — seatplan_area_id setzen (629 = Boxen)

**POST mit** `"data.createBookingStepOneForm.seatplan_area_id": 629`

**HTTP-Status: 200**

SELECT für `pax_options` erscheint mit Tischkombinationen:
```
10_1_10  → 1 Tisch, 10 Personen
10_2_20  → 2 Tische, 20 Personen
10_3_30  → 3 Tische, 30 Personen
...
10_10_100 → 10 Tische, 100 Personen
```

---

### Schritt 5 — pax_options setzen + mountAction("incrementCreateBookingStep")

**POST mit** `"data.createBookingStepOneForm.pax_options": "10_1_10"`  
danach: `"calls": [{"method": "mountAction", "params": ["incrementCreateBookingStep"]}]`

**HTTP-Status: 200** (beide Requests)

`createBookingStep` wechselt von 1 auf 2.

Die Buchungsübersicht in Step 2 zeigt:

```
Ihr Termin
  Dienstag, 22.09.2026
  11:00 - 16:45
  10 Personen
  1 Tisch
  Boxen
```

**Beobachtung:** Die Schichtzeit 11:00–16:45 Uhr wird im HTML von createBookingStep 2 angezeigt. Sie steht NICHT im Snapshot, sondern nur im gerenderten HTML-Fragment.

Step 2 zeigt Speisen/Verzehrpakete an (Mindestabnahme, Traditionsmenü etc.) — kein Login nötig bis hierher.

---

### Schritt 6 — festzelt-os.com REST-API (wie bei anderen Zelten)

Getestete Company-Header: `braeurosl`, `braurosl`, `braeurosl-muenchen`, `braeurosl_muenchen`

Alle → **HTTP-Status: 404** (kein gültiger Company-Slug)

`bräurosl` (mit Umlaut) → **HTTP-Status: 403**

**Ergebnis:** Bräurosl hat keinen direkten API-Zugang über festzelt-os.com (oder der Company-Slug ist unbekannt).

---

## Snapshot-Analyse

**Component-Name:** `app.portal.livewire.view-portal-page`

**memo.methods:** `[]` (leer — Livewire v3 exponiert Methoden nicht im Snapshot)

**data-Keys (vollständig):**
- Buchungsformular: `createBookingStep`, `booking`, `createBookingStepOneForm`, `createBookingStepTwoForm`
- Sitzplan: `cachedSeatplanAreas`, `blockedBookableSeatplanElementPax`, `temporarilyBlockedSeatplanElementBlockIds`
- Tabelle: `isTableLoaded`, `tableGrouping`, `tableRecordsPerPage`, `tableSearch`, `tableSortColumn`, etc.
- Filament: `mountedActions`, `mountedTableActions`, `mountedFormComponentActions`, etc.

**Wichtige feste Werte:**
- `booking_list_group_id = 62` (Bräurosl-ID, immer gleich)
- `booking_list_ids` für Mittag 2026: 1917, 1919, 1921, 1927, 1929, 1931, 1933, 1935, 1937, 1943 (je Datum eine ID)

**key=134764:** Eine numerische ID im Snapshot, Zweck unklar (könnte Reservation/Booking-ID oder interner Key sein).

**Sitzplankomponente:** `PortalSeatplanElementPicker` — bleibt `class="hidden"` wenn `seatplan_group_id` nicht gesetzt. Die Sitzplan-Elemente (einzelne Tische) werden nicht ohne weitere Interaktion geladen.

---

## Verfügbarkeits-Logik

Die Verfügbarkeit ist **implizit** codiert:

| Signal | Bedeutung |
|--------|-----------|
| Datum erscheint im SELECT | Schicht für dieses Datum buchbar |
| Datum fehlt im SELECT | Ausgebucht oder gesperrt |
| `booking_list_id`-Option erscheint | Schicht verfügbar |
| SELECT für `booking_list_id` leer | Alle Schichten belegt |
| `seatplan_area_id`-Optionen vorhanden | Bereiche verfügbar |
| `pax_options` SELECT vorhanden | Tische verfügbar |

**Aktuell fehlende Daten (2026-09-25, 2026-09-26, 2026-10-03):** Diese drei Samstage/Freitag fehlen im Datums-SELECT → entweder ausgebucht oder noch nicht freigeschaltet.

**Nur "Mittag"-Schicht** (11:00–16:45) sichtbar — kein Abend-Betrieb oder noch nicht freigeschaltet für 2026.

---

## Offene Fragen / Stolpersteine

1. **Tatsächliche Kapazitätszahl:** Die Seite gibt keine numerische "X von Y Plätzen verfügbar"-Info aus. Verfügbarkeit = ob Option erscheint.

2. **Fehlende Samstage:** Ob 2026-09-25/26 und 2026-10-03 ausgebucht oder nicht freigeschaltet sind, kann ohne tiefere API-Kenntnis nicht unterschieden werden.

3. **start_at/end_at als strukturierter Wert:** Die Zeit 11:00–16:45 erscheint nur als gerendeter HTML-Text in der Übersicht von Step 2 — nicht als strukturiertes JSON-Feld im Snapshot.

4. **$refresh-Call → 500:** Das direkte Setzen von `createBookingStep` oder Aufrufen von nicht vorhandenen Methoden liefert HTTP 500 — Server validiert Checksum im Snapshot.

5. **PortalSeatplanElementPicker bleibt hidden:** Die individuelle Tisch-Auswahl (Seatplan-Picker) wird vermutlich über einen weiteren Livewire-Call oder AJAX geladen, der `seatplan_group_id` benötigt — dieser Wert bleibt `null`.

6. **festzelt-os.com API:** Company-Slug für Bräurosl unbekannt; möglicherweise gibt es einen internen Slug, der im JavaScript des initialen HTML hardcodiert ist — noch nicht vollständig untersucht.

---

## Empfehlung: Nächster Schritt

**Direkter Bot-Bau ist möglich — kein Login nötig.**

Die Verfügbarkeit lässt sich mit folgenden 2–3 Livewire-Requests pro Datum prüfen:

```python
# Pro Datum (z.B. "2026-09-22"):
# Request 1: GET /reservation/ → snap0, csrf_token
# Request 2: POST /livewire/update, updates={"date": datum} → Prüfe ob booking_list_id-SELECT nicht leer
# (Optional) Request 3: POST /livewire/update, updates={"booking_list_id": bl_id, "seatplan_area_id": area_id, "pax_options": pax}
#   → Prüfe ob alle Bereiche (629/630/632/634) noch Optionen haben

# Signale für "noch verfügbar":
# - Datum im SELECT vorhanden (primär)
# - booking_list_id-Option vorhanden (sekundär)
# - seatplan_area_id-Optionen vorhanden (tertiär)
```

**Monitoring-Strategie:** Da Samstage fehlen und 2025-Daten gar nicht gelistet sind, ist die Seite wahrscheinlich schon für 2026 geöffnet und alle 10 Daten zeigen aktuell Verfügbarkeit. Bot sollte prüfen, wann Daten aus dem SELECT verschwinden.

**Schichtzeiten aus HTML extrahieren:** Nach `mountAction("incrementCreateBookingStep")` enthält das HTML `<span>11:00 - 16:45</span>` — per Regex `r'<span>(\d{1,2}:\d{2} - \d{1,2}:\d{2})</span>'` extrahierbar.

**start_at/end_at als datetime:** `2026-09-22` + `11:00` = `2026-09-22T11:00:00`, `2026-09-22T16:45:00`.

**Kein festzelt-os.com API-Zugang nötig** — der Livewire-Weg funktioniert vollständig.

---

## Phantom-Check Runde 2 (Datum: 2026-05-17)

### Methodik

Für alle 10 im Datums-SELECT gefundenen Daten wurde je ein POST an `/livewire/update` gesendet (Livewire v3, `X-Livewire: true`, aktueller CSRF-Token + Snapshot aus vorherigem GET). Das Response-HTML-Fragment wurde auf das `<select id="data.createBookingStepOneForm.booking_list_id">` untersucht.

Wichtiger technischer Befund: Die Option-Tags im Livewire-HTML sind in IE-Conditional-Comment-Blöcke (`<!--[if BLOCK]><![endif]-->`) eingebettet, weshalb ein Standard-Regex für `<option value="...">Text</option>` 0 Treffer liefert. Korrekt ist das Extrahieren des SELECT-Blocks per `id="data.createBookingStepOneForm.booking_list_id"` und dann `value="(\d+)"` darin.

CSRF-Token wurde nach 5 Requests erneuert (neuer GET → neuer Token + neuer Snapshot). Snapshot wurde nach jedem POST aus der Response aktualisiert. Kein HTTP-429 oder HTTP-419 aufgetreten.

### Ergebnisse pro Datum

| Datum | Status | Schichten | booking_list_id | Schichtname |
|-------|--------|-----------|-----------------|-------------|
| 2026-09-22 | 200 | 1 | 1917 | Mittag |
| 2026-09-23 | 200 | 1 | 1919 | Mittag |
| 2026-09-24 | 200 | 1 | 1921 | Mittag |
| 2026-09-27 | 200 | 1 | 1927 | Mittag |
| 2026-09-28 | 200 | 1 | 1929 | Mittag |
| 2026-09-29 | 200 | 1 | 1931 | Mittag |
| 2026-09-30 | 200 | 1 | 1933 | Mittag |
| 2026-10-01 | 200 | 1 | 1935 | Mittag |
| 2026-10-02 | 200 | 1 | 1937 | Mittag |
| 2026-10-04 | 200 | 1 | 1943 | Mittag |

Details pro Datum (booking_list_id + Raw-Response-Auszug):

**2026-09-22** — booking_list_id 1917 "Mittag"
```
{"components":[{"snapshot":"{\"data\":{\"portalPage\":[null,{\"class\":\"Domain\\Company\\Models\\PortalPage\",\"key\":60,\"s\":\"mdl\"}],\"data\":[{\"createBookingStepOneForm\":[{\"booking_list_group_id\":62,\"date\":\"2026-09-22\",\"booking_list_id\":null,\"seatplan_area_id\":null,\"pax_opti...
```

**2026-09-23** — booking_list_id 1919 "Mittag" (Raw analog)

**2026-09-24** — booking_list_id 1921 "Mittag"

**2026-09-27** — booking_list_id 1927 "Mittag"

**2026-09-28** — booking_list_id 1929 "Mittag"

**2026-09-29** — booking_list_id 1931 "Mittag" (nach CSRF-Erneuerung)

**2026-09-30** — booking_list_id 1933 "Mittag"

**2026-10-01** — booking_list_id 1935 "Mittag"

**2026-10-02** — booking_list_id 1937 "Mittag"

**2026-10-04** — booking_list_id 1943 "Mittag"

Zur Schichtzeit: Die Uhrzeit (11:00–16:45) erscheint **nicht** nach dem Datum-POST im HTML, sondern erst nach dem `incrementCreateBookingStep`-Call (Schritt 5 in der Dokumentation oben). Das HTML in Phase 1 enthält nur CSS-Werte (`50:24`, `00:77`), keine echten Uhrzeiten.

### Auswertung

- **Phantom-Daten: NEIN** — 0 von 10 Daten sind Phantome. Jedes Datum im SELECT liefert garantiert genau 1 buchbare Schicht.
- **Schichtzeiten:** In dieser Request-Phase nicht extrahierbar (taucht erst nach booking_list_id-Selektion und Step-Advance auf). Bekannt aus Runde 1: 11:00–16:45 Uhr für alle Daten.
- **Schichtanzahl:** Immer genau 1 Schicht ("Mittag") pro Datum — keine Varianz über alle 10 Daten.
- **booking_list_ids:** Pro Datum eine eigene ID (1917, 1919, 1921, ... 1943) — nicht-konsekutiv (Lücken an 2026-09-25/26, 2026-10-03). Die IDs steigen monoton an und korrespondieren mit den Datumslücken.
- **Empfehlung für Bot-Logik:**
  - **Primär-Signal:** Datum verschwindet aus dem Datums-SELECT → ausgebucht.
  - **Sekundär-Signal:** Nach Datum-POST ist `booking_list_id`-SELECT leer → keine Schicht verfügbar.
  - **Beide Checks mit einem einzigen POST** pro Datum möglich (kein zweiter POST zur Bestätigung nötig).
  - **Kein Phantom-Problem vorhanden** — der Bot kann davon ausgehen, dass ein Datum im SELECT immer mindestens eine buchbare Schicht hat.
  - **Regex-Fix für Livewire-HTML:** Standard `<option value="...">` greift nicht. Korrekte Extraktion: SELECT-Block per `id=`-Attribut lokalisieren, dann `value="(\d+)"` darin suchen.
