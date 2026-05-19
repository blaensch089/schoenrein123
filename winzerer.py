"""
Winzerer Fähndl Livewire-Checker für den Wiesn-Bot.
check_winzerer() → {uid: slot_dict}, kompatibel mit bot.py run_check().

UID-Format: winzerer_{datum}_{area_id}_{startzeit_hhmm}

DYNAMISCHE Area-Extraktion: Pro Datum werden zwei Livewire-POSTs gemacht.
Der erste setzt das Datum (→ booking_list_id-SELECT). Der zweite setzt die
booking_list_id (→ seatplan_group_id-SELECT mit allen verfügbaren Bereichen).
Damit erkennt der Bot automatisch jeden Bereich, der gerade frei ist, ohne
hardcoded Liste.

Pro Datum wird ein frischer GET geholt, um den Livewire-Snapshot sauber zu
halten (sonst klebt der booking_list_id-State vom vorigen Datum drin).

Schichtzeiten: "Mittag" → 11:00–16:45 (wird durch Push-Filter ignoriert).
Andere Schichten bekommen Default 17:00–22:30 und lösen den Abend-Filter
im bot.py aus → garantierter Push.
"""
import html as htmllib
import re
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

_BOOKING_URL = "https://reservierung.paulanerfestzelt.de/reservierung"
_BASE        = "https://reservierung.paulanerfestzelt.de"
_UA          = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_MUNICH_TZ   = ZoneInfo("Europe/Berlin")
_POST_DELAY  = 3

_SHIFT_TIMES = {
    "mittag": ("11:00", "16:45"),
}
_FALLBACK_TIMES = ("17:00", "22:30")


def _times_for_shift(bl_name):
    """Mappt Schichtname auf (start, end) im Format 'HH:MM'."""
    name_lower = bl_name.lower()
    for key, times in _SHIFT_TIMES.items():
        if key in name_lower:
            return times
    return _FALLBACK_TIMES


def _mk_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent":      _UA,
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9",
    })
    return s


def _find_select(html, field_id):
    """Findet den Inhalt des SELECT für ein Formularfeld (id='...')."""
    m = re.search(
        rf'id="{re.escape(field_id)}"[^>]*>(.*?)</select>',
        html, re.DOTALL | re.IGNORECASE,
    )
    return m.group(1) if m else ""


def _extract_csrf(html):
    m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    return m.group(1) if m else ""


def _extract_portal_snapshot(html):
    """Findet das Portal-Snapshot (erkennbar an createBookingStepOneForm)."""
    for raw in re.findall(r'wire:snapshot="([^"]+)"', html):
        decoded = htmllib.unescape(raw)
        if "createBookingStepOneForm" in decoded:
            return decoded
    return None


def _extract_dates(html):
    """Alle verfügbaren Daten aus dem Datums-SELECT."""
    block = _find_select(html, "data.createBookingStepOneForm.date")
    return re.findall(r'value="(\d{4}-\d{2}-\d{2})"', block) if block else []


def _parse_options(html_frag, select_id):
    """Robuste Extraktion aller <option>-Tags eines bestimmten SELECTs.

    Vorgehen:
    1. SELECT-Block per id="..." lokalisieren.
    2. Alle <option ...>...</option>-Blöcke darin greifen.
    3. Pro Block: value-Zahl extrahieren, HTML-Kommentare wegputzen,
       sichtbaren Text zwischen > und </option> als Namen.

    Gibt Liste von (value, name)-Tupeln zurück (ohne leere Platzhalter-Optionen).
    """
    select_inner = _find_select(html_frag, select_id)
    if not select_inner:
        return []

    results = []
    for block in re.findall(r'<option\s.*?</option>', select_inner, re.DOTALL):
        vm = re.search(r'value="(\d+)"', block)
        if not vm:
            continue
        cleaned = re.sub(r'<!--.*?-->', '', block, flags=re.DOTALL)
        tm = re.search(r'<option\s[^>]*>(.*?)</option>', cleaned, re.DOTALL)
        if not tm:
            continue
        name = tm.group(1).strip()
        if name:
            results.append((vm.group(1), name))
    return results


def _extract_bl_options(html_frag):
    """booking_list_id-Optionen (Schicht-Optionen) aus POST-Response-HTML."""
    return _parse_options(html_frag, "data.createBookingStepOneForm.booking_list_id")


def _extract_area_options(html_frag):
    """seatplan_group_id-Optionen aus POST-Response-HTML (DYNAMISCH).

    Winzerer Fähndl nutzt seatplan_group_id statt seatplan_area_id.
    Gibt Liste von (area_id, area_name)-Tupeln zurück.
    """
    return _parse_options(html_frag, "data.createBookingStepOneForm.seatplan_group_id")


def _to_utc_iso(datum, uhrzeit):
    """YYYY-MM-DD + HH:MM (München) → UTC ISO-String."""
    dt = datetime(
        int(datum[:4]), int(datum[5:7]), int(datum[8:10]),
        int(uhrzeit[:2]), int(uhrzeit[3:5]),
        tzinfo=_MUNICH_TZ,
    )
    return dt.astimezone(timezone.utc).isoformat()


def _post_livewire(session, snapshot, csrf_token, updates):
    """Sendet Livewire-POST, gibt (neuer_snapshot, html_frag) zurück."""
    r = session.post(
        f"{_BASE}/livewire/update",
        json={"components": [{"snapshot": snapshot, "updates": updates, "calls": []}]},
        headers={
            "Content-Type": "application/json",
            "Accept":       "text/html, application/xhtml+xml",
            "X-Livewire":   "true",
            "X-CSRF-TOKEN": csrf_token,
            "Referer":      _BOOKING_URL,
            "Origin":       _BASE,
        },
        timeout=20,
    )
    if r.status_code == 429:
        raise RuntimeError("WINZERER_RATELIMIT")
    r.raise_for_status()

    new_snap  = snapshot
    html_frag = ""
    for comp in r.json().get("components", []):
        if comp.get("snapshot"):
            new_snap = comp["snapshot"]
        html_frag += comp.get("effects", {}).get("html", "")
    return new_snap, html_frag


def _fetch_portal(session):
    """GET /reservierung → (csrf_token, snapshot, dates)."""
    r = session.get(_BOOKING_URL, timeout=20)
    r.raise_for_status()
    csrf_token = _extract_csrf(r.text)
    snapshot   = _extract_portal_snapshot(r.text)
    dates      = _extract_dates(r.text)
    if not csrf_token:
        raise RuntimeError("WINZERER: CSRF-Token nicht im HTML gefunden")
    if snapshot is None:
        raise RuntimeError("WINZERER: wire:snapshot nicht im HTML gefunden")
    return csrf_token, snapshot, dates


def check_winzerer():
    """
    Prüft verfügbare Winzerer Fähndl-Slots via Livewire (kein Login nötig).
    Gibt {uid: slot_dict} zurück, kompatibel mit bot.py run_check().
    Wirft RuntimeError("WINZERER_RATELIMIT") bei HTTP 429.

    Pro Datum: frischer GET (sauberer Snapshot), POST 1 (date),
    POST 2 (booking_list_id) → Areas DYNAMISCH aus Response extrahieren.
    """
    session = _mk_session()

    print("  [Winzerer Fähndl] GET /reservierung …", end=" ", flush=True)
    csrf_token, snapshot, dates = _fetch_portal(session)
    print(f"{len(dates)} Datum/-Daten: {dates}", flush=True)

    slots = {}

    for i, datum in enumerate(dates):
        # Ab dem 2. Datum: frischer GET, damit der Snapshot sauber ist
        # (sonst klebt der booking_list_id-State vom vorigen Datum drin)
        if i > 0:
            time.sleep(_POST_DELAY)
            print(f"  [Winzerer Fähndl] GET (refresh) für {datum} …", end=" ", flush=True)
            csrf_token, snapshot, _ = _fetch_portal(session)
            print("ok", flush=True)

        # POST 1: Datum setzen → Schicht-Optionen
        time.sleep(_POST_DELAY)
        print(f"  [Winzerer Fähndl] POST 1 {datum} (date) …", end=" ", flush=True)
        snapshot, html_frag = _post_livewire(
            session, snapshot, csrf_token,
            {"data.createBookingStepOneForm.date": datum},
        )
        bl_options = _extract_bl_options(html_frag)
        print(f"{len(bl_options)} Schicht(en)", flush=True)

        if not bl_options:
            print(f"  [Winzerer Fähndl] Warnung: {datum} hat 0 Schichten – überspringe")
            continue

        # POST 2 pro Schicht: Areas dynamisch holen
        for bl_id, bl_name in bl_options:
            time.sleep(_POST_DELAY)
            print(f"  [Winzerer Fähndl] POST 2 {datum} bl_id={bl_id} ({bl_name}) …", end=" ", flush=True)
            snapshot, html_frag2 = _post_livewire(
                session, snapshot, csrf_token,
                {"data.createBookingStepOneForm.booking_list_id": int(bl_id)},
            )
            area_options = _extract_area_options(html_frag2)
            print(f"{len(area_options)} Area(s): {[n for _, n in area_options]}", flush=True)

            if not area_options:
                print(f"  [Winzerer Fähndl] Hinweis: {datum} Schicht '{bl_name}' hat 0 Areas (ausgebucht/gesperrt)")
                continue

            if "mittag" not in bl_name.lower():
                print(f"  [Winzerer Fähndl] HINWEIS: Schicht '{bl_name}' ist nicht 'Mittag' – Zeit-Default 11:00 stimmt evtl. nicht")

            start_str, end_str = _times_for_shift(bl_name)
            start_utc = _to_utc_iso(datum, start_str)
            end_utc   = _to_utc_iso(datum, end_str)

            for area_id, area_name in area_options:
                uid = f"winzerer_{datum}_{area_id}_{start_str.replace(':', '')}"
                slots[uid] = {
                    "uid":            uid,
                    "name":           f"Winzerer Fähndl {bl_name} {datum} {area_name}",
                    "date":           datum,
                    "areas":          [{"label": area_name, "start": start_utc, "end": end_utc}],
                    "earliest_start": start_utc,
                }

    return slots
