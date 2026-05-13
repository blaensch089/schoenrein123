# Recherche-Bericht Schottenhamel

Analysiert am: 2026-05-12  
Portal: https://reservierung.festhalle-schottenhamel.de/reservation/

---

## API-Grundlagen

**Basis-URL:** `https://schottenhamel-api.festzelt-os.com`

**Whitelabel-Anbieter:** [Festzelt OS](https://festzelt-os.com)  
Nachweis: Footer-Text „Powered by Festzelt OS" + Logo + API-Domain.  
Hypothese bestätigt: Alle Zelte, die `reservierung.X.de` verwenden, nutzen sehr wahrscheinlich Festzelt OS als gemeinsames Backend.

**Auth-Header (Pflicht):**
```
x-festzelt-os-company: KDLWJDR
```
Dieser Header identifiziert den Mandanten (Schottenhamel). Er ist in jede Frontend-JS-Bundle eingebaut und wird bei jedem API-Request mitgesendet. **Kein Login, kein Bearer-Token nötig** — der Company-Header reicht für die öffentlichen `/lp/`-Endpunkte.

**Weitere relevante Request-Headers (Browser-Standard, empfohlen):**
```
Referer: https://reservierung.festhalle-schottenhamel.de/
Origin:  https://reservierung.festhalle-schottenhamel.de
Accept:  application/json
```

**Cookies / Session:** Nicht nötig für Lese-Endpunkte. Browser setzt `i18n_redirected=de; auth.strategy=local`, aber diese sind für den öffentlichen Zugriff irrelevant.

**Frontend-Framework:** Nuxt.js (Vue 3), SSR. Bundles unter `/_nuxt/*.js`.

**Bot-Schutz:** Kein Cloudflare, kein CAPTCHA detektiert. Sentry-Integration vorhanden (Error-Monitoring). Rate-Limit aktiv (429 nach ca. 15–20 schnellen Requests in Folge).

---

## Gefundene Endpunkte

### `GET /lp/guestlists`
Gibt alle Schichten (Events) zurück.

```json
{
  "meta": { "curTime": "2026-05-12T16:30:12+00:00" },
  "pagination": { "total": 23, "current": 1, "perPage": 100, "pages": 1 },
  "data": [ /* Array mit 23 Schicht-Objekten */ ]
}
```

- Öffentlich zugänglich mit `x-festzelt-os-company`-Header.
- Liefert alle UIDs, Daten, Schicht-Labels und den `new_reservation_state`.
- **Das ist der primäre Endpunkt für den Monitor-Bot.**

---

### `GET /lp/guestlists/{uid}/definitions`
Gibt Bereiche (Areas/Hallen) einer Schicht zurück.

Erfolgreich im Browser-Session abgefangen (Phase 2), Beispiel-Response für `6LZMCCZ` (Do 01.10. Mittag):
```json
{
  "status": 200,
  "data": {
    "default_min_consumption": null,
    "areas": [
      {
        "id": 87,
        "label": "Halle Süd/Mitte",
        "start": "2026-10-01T10:00:00+00:00",
        "end":   "2026-10-01T13:30:00+00:00",
        "min_consumption": "86fccd8c-...",
        "custom_1": "", ...
      },
      {
        "id": 91,
        "label": "Hallenboxe...",
        ...
      }
    ]
  }
}
```

- Direkte Calls ohne Browser-Session liefern **401 Unauthorized**.
- Möglicherweise braucht dieser Endpunkt ein Session-Token, das die Frontend-App beim ersten Load bezieht (nicht in Cookies, evtl. localStorage oder in der Nuxt-App-Config eingebettet).
- Funktioniert sicher über den Browser (Playwright-Session).

---

### `GET /lp/deposits`
Zahlungsarten/Deposit-Konfiguration. Für den Monitor-Bot nicht relevant.

---

### Noch nicht getestet (kein weiterer Traffic heute):
- `/lp/guestlists/{uid}/seats` — vermuteter Seatplan-Endpunkt
- `/lp/guestlists/{uid}/seatplan` — alternativ
- `/lp/guestlists/{uid}/reservations` — möglicherweise Auth-geschützt
- `/lp/guestlists/{uid}/capacity`

---

## Slot-Datenstruktur

### Schicht-Objekt (vollständig, aus `/lp/guestlists`):
```json
{
  "name": "1. Montag, 21.09.2026 - Mittag",
  "date": "2026-09-21T00:00:00+00:00",
  "uid":  "NXUZF4B",
  "default_mc_guestlist_object_id": null,
  "shift": {
    "id": 19,
    "label": "Mittag"
  },
  "use_seatplan_in_public": true,
  "payment_required_for_confirmation": false,
  "disable_shipping": false,
  "new_reservation_state": "confirmed"
}
```

### Status-Feld: `new_reservation_state`
Aktuell haben **alle 23 Schichten** den Wert `"confirmed"`.  
Mögliche Werte (aus dem Feldname abgeleitet, noch nicht verifiziert):
- `"confirmed"` — Reservierungen aktiv / offen
- `"waitlist"` — Warteliste (vermutlich)
- `"closed"` — Keine neuen Reservierungen mehr möglich
- `"cancelled"` — Schicht storniert (vermutlich)

**Achtung:** Dieser Status gibt an, ob die Schicht *generell* offen ist — **nicht**, ob einzelne Tische für eine bestimmte Personenzahl frei sind. Tisch-Verfügbarkeit ist ein nachgeordnetes Level (Seatplan).

### `use_seatplan_in_public: true`
Wichtiger Hinweis: Der Sitzplan ist für die öffentliche Ansicht aktiviert. Das bedeutet, Tisch-Verfügbarkeit sollte **ohne Login** abfragbar sein — aber der Endpunkt dafür ist noch nicht vollständig identifiziert.

---

### Alle 23 Schichten (Stand 2026-05-12):

| # | Datum | Wochentag | Schicht | UID | Status |
|---|-------|-----------|---------|-----|--------|
| 1 | 21.09.2026 | Mo | Mittag | NXUZF4B | confirmed |
| 2 | 21.09.2026 | Mo | Nachmittag | D4V8NMG | confirmed |
| 3 | 22.09.2026 | Di | Mittag | PUUH5QK | confirmed |
| 4 | 22.09.2026 | Di | Nachmittag | M7U2N61 | confirmed |
| 5 | 23.09.2026 | Mi | Mittag | FLP55A4 | confirmed |
| 6 | 23.09.2026 | Mi | Nachmittag | GGFESMA | confirmed |
| 7 | 24.09.2026 | Do | Mittag | 9GCH6GZ | confirmed |
| 8 | 24.09.2026 | Do | Nachmittag | 9836RXV | confirmed |
| 9 | 25.09.2026 | Fr | Mittag | YQKXBK1 | confirmed |
| 10 | 26.09.2026 | Sa | Mittag | MFLBTDD | confirmed |
| 11 | 28.09.2026 | Mo | Mittag | MPPWW6M | confirmed |
| 12 | 28.09.2026 | Mo | Nachmittag | F4DPXZF | confirmed |
| 13 | 29.09.2026 | Di | Mittag | H485MY6 | confirmed |
| 14 | 29.09.2026 | Di | Nachmittag | ZLT6U6K | confirmed |
| 15 | 30.09.2026 | Mi | Mittag | PCE2351 | confirmed |
| 16 | 30.09.2026 | Mi | Nachmittag | 7EQXM7Y | confirmed |
| 17 | 01.10.2026 | Do | Mittag | 6LZMCCZ | confirmed |
| 18 | 01.10.2026 | Do | Nachmittag | P3W5W2S | confirmed |
| 19 | 02.10.2026 | Fr | Mittag | G29ETMZ | confirmed |
| 20 | 02.10.2026 | Fr | Nachmittag | FFZQADL | confirmed |
| 21 | 03.10.2026 | Sa | Mittag | KW2R69W | confirmed |
| 22 | 04.10.2026 | So | Mittag | PV38RS8 | confirmed |
| 23 | 04.10.2026 | So | Nachmittag | WBEHY1P | confirmed |

**Wichtige Beobachtungen:**
- Oktoberfest beginnt 19.09.2026 (Sa). **Das Eröffnungswochenende (Sa 19.09 + So 20.09) fehlt komplett** — entweder gesondert buchbar (VIP/Sponsor-Kontingent) oder noch nicht freigeschaltet.
- So 27.09. fehlt ebenfalls.
- Fr 25.09. hat nur eine Schicht (Mittag), kein Nachmittag.
- Sa 26.09. hat nur Mittag, kein Nachmittag.
- Sa 03.10. (Tag der Deutschen Einheit) hat nur Mittag.
- **Keine einzige „Abendschicht"** — das Portal unterscheidet nur Mittag und Nachmittag. Die gesuchten „Abendslots" aus dem ursprünglichen Testcase existieren als separate Schicht nicht.

---

## Noch offen

1. **Seatplan-Endpunkt für Tisch-Verfügbarkeit:** Der Endpunkt, der für eine gegebene Schicht (`uid`) und eine Personenzahl (8 oder 10) freie Tische zurückgibt, ist noch nicht identifiziert. Kandidaten: `/lp/guestlists/{uid}/seats`, `/seatplan`, `/capacity`. Phase 5 scheiterte, weil der Weiter-Button deaktiviert blieb (noch zu untersuchen).

2. **Warum ist Weiter deaktiviert?** Möglicherweise braucht das Formular auf Schritt 1 noch ein Personenzahl-Feld (nicht gefunden) oder einen anderen Trigger. Im HTML sind keine `input[type=number]`-Felder sichtbar — könnte ein Plus/Minus-Widget in Vue sein.

3. **Auth für `/definitions`:** Klar ist, dass der Browser-Session die `/definitions`-Antwort liefert, direkte Calls aber 401 geben. Warum? Entweder braucht der Endpunkt einen zusätzlichen Token, der beim Seitenlade via Nuxt gesetzt wird, oder eine temporäre Session-ID aus dem initialen HTML.

4. **`new_reservation_state` vollständige Werteliste:** Alle 23 Schichten zeigen aktuell `"confirmed"`. Sobald eine ausverkauft ist, wird sich zeigen, auf welchen Wert das Feld wechselt.

5. **Seatplan-Struktur und `area.id`:** Bekannte Areas für Do 01.10. Mittag: `id=87` „Halle Süd/Mitte" und `id=91` „Hallenboxe..." (abgeschnitten). Vollständige Auflistung und Kapazitäten noch ausstehend.

6. **Andere Zelte:** Noch nicht geprüft, ob alle anderen Zelte denselben `x-festzelt-os-company`-Header verwenden (nur mit anderem Wert) und dieselbe API-Struktur haben.

---

## Rate-Limit-Verhalten

- **429-Schwelle:** Nach ca. 15–20 direkten API-Calls in kurzer Folge (< 1s Abstand) ohne Browser-Session trat 429 auf.
- **Persistenz:** Der 429-Status hielt mindestens 30+ Sekunden an (nach 30s Wartezeit noch aktiv).
- **Empfohlener Cooldown:** Mindestens **60 Sekunden** nach einem 429, besser 120s.
- **Empfohlener Abstand zwischen Requests:** ≥ 2 Sekunden für direkten API-Zugriff. Im Browser funktioniert es schneller (andere IP-/Session-Behandlung möglich).
- **Monitoring-Intervall für den Bot:** Nicht öfter als alle **5–10 Minuten** pro Schicht. Für 23 Schichten bedeutet das: alle Schichten in einem Durchlauf mit 2–3s Pause = ca. 1 Minute pro Runde, dann 9 Minuten Pause.
