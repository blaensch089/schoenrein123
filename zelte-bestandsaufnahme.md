# Oktoberfest Festzelt Reservierungsportale — Technische Bestandsaufnahme

**Datum:** 2026-05-14

## Ergebnistabelle

| Zelt | URL | Typ | Details |
|------|-----|-----|---------|
| Schützenfestzelt | https://reservierung.schuetzenfestzelt.com/reservation/ | **A** | API: `https://schuetzen-api.festzelt-os.com/lp` · `x-festzelt-os-Company: M5RN1H1` · `/lp/guestlists` antwortet HTTP 200 |
| Hacker Festzelt | https://reservierung.derhimmelderbayern.de/ | **B** | Livewire (Laravel + Filament + Festzelt OS Backend) · `wire:id` im HTML · `/livewire/update` vorhanden (405/403 auf GET, POST-only) · Daten sind server-side gerendert, nicht direkt per GET maschinenlesbar |
| Bräurosl | https://reservierung.braeurosl.de/reservation/ | **B** | Livewire (Laravel + Filament + Festzelt OS Backend) · identische Struktur wie Hacker · `/livewire/update` vorhanden · `booking_list_group_id: 62` im initialen Snapshot sichtbar |
| Armbrustschützenzelt | https://reservierung.armbrustschuetzenzelt.de/reservierung | **B** | Livewire (Laravel + Filament + Festzelt OS Backend) · `wire:id` im HTML · `booking_list_group_id: 68` im Snapshot · `/livewire/update` vorhanden |
| Marstall-Festzelt | https://reservierung.marstall-oktoberfest.de/reservation | **A** | API: `https://marstall-api.festzelt-os.com/lp` · `x-festzelt-os-Company: J12J1KA` · `/lp/guestlists` antwortet HTTP 200 |
| Löwenbräu Festzelt | https://reservierung.loewenbraeuzelt.de/reservierung | **B** | Livewire (Laravel + Filament + Festzelt OS Backend) · `wire:id` im HTML · `/livewire/update` vorhanden |
| Winzerer Fähndl (Paulaner) | https://reservierung.paulanerfestzelt.de/reservierung | **B** | Livewire (Laravel + Filament + Festzelt OS Backend) · `wire:id` im HTML · `/livewire/update` vorhanden |
| Ochsenbraterei | https://reservierung.ochsenbraterei.de/reservierungen | **B** | Livewire (Laravel + Filament + Festzelt OS Backend) · `wire:id` im HTML · `/livewire/update` vorhanden |
| Weinzelt | https://reservierung.weinzelt.com/reservation/ | **A** | API: `https://api.festzelt-os.com/lp` · `x-festzelt-os-Company: FOSKUFW4711` · `/lp/guestlists` antwortet HTTP 200 |

---

## Zusammenfassung

- **Typ A (direkte festzelt-os.com REST-API, Nuxt.js Frontend):** 3 Zelte
  - Schützenfestzelt (`M5RN1H1`, `schuetzen-api.festzelt-os.com`)
  - Marstall-Festzelt (`J12J1KA`, `marstall-api.festzelt-os.com`)
  - Weinzelt (`FOSKUFW4711`, `api.festzelt-os.com`)

- **Typ B (Livewire / Laravel + Filament, server-seitiges Rendering):** 6 Zelte
  - Hacker Festzelt, Bräurosl, Armbrustschützenzelt, Löwenbräu, Winzerer Fähndl, Ochsenbraterei

- **Typ C (Sonstiges):** 0 Zelte

---

## Technische Hinweise

### Typ A — Direkte API-Abfrage möglich
Alle drei Typ-A-Portale verwenden ein Nuxt.js 2 SPA-Frontend das direkt die `festzelt-os.com` REST-API anspricht. Der Endpunkt `/lp/guestlists` liefert Verfügbarkeitsdaten als JSON. Pflicht-Header: `x-festzelt-os-Company: <COMPANY_UID>` sowie `Accept: application/json`.

Weinzelt ist der einzige Fall mit einer generischen API-Subdomain (`api.festzelt-os.com` statt `weinzelt-api.festzelt-os.com`). Die Company-UID (`FOSKUFW4711`) ist länger als die üblichen 7 Zeichen.

### Typ B — Livewire: Daten bedingt maschinenlesbar
Alle sechs Typ-B-Portale nutzen dieselbe Laravel/Filament/Livewire-Architektur und laufen ebenfalls auf Festzelt OS Infrastruktur (gleiche CSS-Assets, gleiche Komponentennamen wie `app.portal.livewire.view-portal-page`). Der initiale HTML-Response enthält einen `wire:snapshot`-JSON-Blob mit dem Livewire-Komponentenzustand — darin sind bereits einige Daten sichtbar (z. B. `booking_list_group_id`). Für vollständige Verfügbarkeitsdaten wäre ein POST auf `/livewire/update` nötig (mit CSRF-Token und Snapshot-Checksum), was eine laufende Session voraussetzt.
