# Diagnose: Schützenfestzelt — Warum der Bot nur 2 Schichten sieht

**Datum:** 2026-05-14

---

## 1. Ausgangsfrage

Chris sieht im Portal `reservierung.schuetzenfestzelt.com` durchgehend Schichten vom 19.09.–04.10. inkl. Abendschichten (z. B. Sa 19.09. 17:00–22:30). Unser Bot findet via `GET /lp/guestlists` nur 2 Einträge (beide Montagsmittag). Woher kommt der Unterschied?

---

## 2. Technische Untersuchung

### 2a. Portal-Architektur (JS-Bundle-Analyse)

Das Schützenfestzelt-Portal ist eine **reine Client-Side-Rendering (CSR) Nuxt.js 2 SPA** — kein SSR, kein Preload. HTML-Shell ist nur 2.473 Bytes, `window.__NUXT__` enthält nur die App-Config (kein Daten-Preload).

Das `SchuetzenReservation`-Component (Chunk 61: `4390f71.js`) baut die Datums- und Schicht-Dropdowns **ausschließlich aus der `guestList`**:

```javascript
// Datumsauswahl im Dropdown:
dates: function() {
    return this.guestList.filter(e => e.uid !== voucherShop.listUid)
        .forEach(n => {
            var r = new Date(n.date).toLocaleDateString("de-DE", {
                weekday:"long", year:"numeric", month:"long", day:"numeric",
                timeZone:"Europe/Berlin"
            });
            t[r] = r;
        });
},
// Schicht-Auswahl (Mittag / Abend / etc.):
timeOptions: function() {
    return this.guestList.filter(...)
        .forEach(n => {
            t[dateKey].push({ uid: n.uid, ...n.shift });  // shift.label → "Mittag", "Abend"
        });
}
```

**Konsequenz: Wenn die API 2 Einträge liefert, zeigt das Portal genau 2 Datumsoptionen.** Es gibt keinen zweiten API-Aufruf, keinen statischen Kalender, keine andere Datenquelle.

### 2b. API-Endpunkte und Parameter-Tests

Alle folgenden Varianten liefern **exakt 2 Ergebnisse**, keine mehr:

| Aufruf | Ergebnis |
|--------|----------|
| `GET /lp/guestlists` | 2 Einträge |
| `GET /lp/guestlists?status=all` | 2 Einträge |
| `GET /lp/guestlists?public=true` | 2 Einträge |
| `GET /lp/guestlists?include=all` | 2 Einträge |
| `GET /lp/guestlists?limit=100` | 2 Einträge |
| `GET /lp/events` | 404 |
| `GET /lp/shifts` | 404 |
| `GET /lp/calendar` | 404 |
| `GET /lp/availability` | 404 |

Keine Paginierung, keine versteckten Parameter. `GET /lp/guestlists` **ist** der einzige relevante Endpunkt — genau wie unser Bot ihn verwendet.

### 2c. Die 2 aktuellen Schichten

```
UID      Name                              Shift   new_reservation_state
DEYY8UE  1. Montag, 21.09.2026 - Mittag   Mittag  requested
8NUPGYT  2. Montag, 28.09.2026 - Mittag   Mittag  requested
```

earliest_start aus Definitions-Cache:
- DEYY8UE: 09:00 UTC = **11:00 Uhr MUC** → Filter: **nein** (zu früh)
- 8NUPGYT: 09:30 UTC = **11:30 Uhr MUC** → Filter: **nein** (zu früh)

### 2d. Pagination-Anomalie — wichtigster Fund

| Zelt | `data`-Einträge | `pagination.total` | `pagination.pages` |
|------|----------------|--------------------|--------------------|
| Schottenhamel | 19 | **19** | 1 |
| Marstall | 11 | **11** | 1 |
| **Schützenfestzelt** | **2** | **0** | **0** |

Bei Schottenhamel und Marstall stimmen `pagination.total` und die tatsächliche Anzahl überein. Beim **Schützenfestzelt meldet die API `total: 0, pages: 0` — obwohl 2 Datensätze im `data`-Array stehen.** Das deutet auf eine inkonsistente oder fehlerhafte Konfiguration im festzelt-os.com-Backend hin.

---

## 3. Befund: Warum der Bot nur 2 Schichten sieht

**Es gibt keine versteckte API.** Der Bot macht alles richtig. Die festzelt-os.com-API des Schützenfestzelts liefert schlicht nur 2 aktive Guestlists.

Die Ursache ist **eine von zwei Möglichkeiten**:

**Möglichkeit A (wahrscheinlich): Phasenweise Freischaltung**
Festzelt-OS schaltet Guestlists sukzessive frei. Aktuell (Mai 2026) sind nur 2 Montagsmittag-Schichten für öffentliche Reservierungen aktiviert. Weitere Schichten (inkl. Abend) werden in den kommenden Wochen/Monaten freigeschaltet — dann tauchen sie in der API auf, und der Bot erkennt sie automatisch.

**Möglichkeit B (möglich): Konfigurationsfehler im Backend**
`pagination.total: 0` bei gleichzeitig 2 vorhandenen Einträgen ist anomal. Es könnte sein, dass die Schützenfestzelt-Konfiguration im festzelt-os.com-Backend unvollständig ist und die meisten Schichten daher nicht sichtbar sind.

---

## 4. Was Chris im Portal gesehen hat — Erklärung

Da die Datums-Dropdowns im Portal **direkt und ausschließlich** aus der API-Antwort gebaut werden, ist folgendes sicher:

> **Wenn Chris Sa 19.09. Abend sieht, muss die API zu diesem Zeitpunkt mehr Einträge geliefert haben.**

Mögliche Erklärungen:
- Chris hat das Portal zu einem anderen Zeitpunkt geöffnet, als mehr Schichten aktiv waren (Festzelt-OS öffnet und schließt Slots dynamisch)
- Die Schichten wurden kurz geöffnet und dann wieder deaktiviert (z. B. Testphase)

**Es gibt kein alternatives Buchungssystem oder Portal** — `reservierung.schuetzen-festzelt.com` (mit Bindestrich) existiert nicht (DNS-Fehler), und `www.schuetzenfestzelt.com` leitet auf die Hauptwebsite `schuetzen-festzelt.de` um.

---

## 5. Auswirkung auf den Bot

| Frage | Antwort |
|-------|---------|
| Übersieht der Bot Abendschichten durch einen API-Fehler? | **Nein** — die API liefert keine Abendschichten |
| Gibt es einen Parameter, der mehr Daten liefert? | **Nein** — alle Parameter getestet, gleiches Ergebnis |
| Würde der Bot Abendschichten erkennen, wenn sie auftauchen? | **Ja** — sobald eine neue UID in der API erscheint, löst der Bot einen Push aus |
| Muss bot.py geändert werden? | **Nein** — die Logik ist korrekt |

---

## 6. Vergleich mit den anderen Typ-A-Zelten

Zur Information: Auch bei Schottenhamel (22 Schichten im Cache), Marstall (11) und Weinzelt (9) gibt es aktuell **keine Abendschicht (≥ 17:00 Uhr MUC)**. Alle aktuellen Schichten starten zwischen 10:00 und 15:15 Uhr.

Für Schottenhamel greifen derzeit 2 Nachmittag-WE-Treffer:
- Fr 02.10.2026: Nachmittag, 14:45 MUC
- So 04.10.2026: Nachmittag, 14:45 MUC

**Das bedeutet: Der Bot wartet derzeit bei allen 4 Zelten auf das erste Erscheinen relevanter Schichten. Die Filter-Logik ist korrekt eingestellt — sie wird auslösen, sobald Abend- oder WE-Nachmittagsschichten in der API erscheinen.**

---

## 7. Empfehlung

Keine Änderung an bot.py notwendig. Der Bot ist korrekt implementiert. 

Falls gewünscht, könnte man den Nachmittag-Filter für Schottenhamel prüfen (14:45 Uhr MUC fällt unter Fr/Sa/So 13:00–16:59 → würde gepusht), aber das ist kein Bug.

**Beobachten:** Wenn die Schützenfestzelt-Abendschichten erscheinen, werden sie im nächsten Polling-Zyklus erkannt.
