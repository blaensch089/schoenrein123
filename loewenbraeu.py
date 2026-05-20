"""
Löwenbräuzelt Livewire-Checker für den Wiesn-Bot.
check_loewenbraeu() → {uid: slot_dict}, kompatibel mit bot.py run_check().

UID-Format: loewenbraeu_{datum}_{booking_list_id}

Das Portal hat KEINEN Bereichs-Select (seatplan_area_id / seatplan_group_id).
Die Tischauswahl erfolgt über ein interaktives Canvas-Element — für den
Verfügbarkeits-Monitor nicht nötig. Prüfung daher auf (Datum + Schicht)-Ebene:
1× GET (Daten), dann pro Datum 1× POST (date → Schicht-Optionen).

Schichtzeiten: "Mittag" → 11:00–16:45 (Push-Filter ignoriert).
Andere Schichten → 17:00–22:30 → Abend-Filter in bot.py → garantierter Push.
"""
import html as htmllib
import re
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

_BOOKING_URL = "https://reservierung.loewenbraeuzelt.de/reservierung"
_BASE        = "https://reservierung.loewenbraeuzelt.de"
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
        raise RuntimeError("LOEWENBRAEU_RATELIMIT")
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
        raise RuntimeError("LOEWENBRAEU: CSRF-Token nicht im HTML gefunden")
    if snapshot is None:
        raise RuntimeError("LOEWENBRAEU: wire:snapshot nicht im HTML gefunden")
    return csrf_token, snapshot, dates


def check_loewenbraeu():
    """
    Prüft verfügbare Löwenbräuzelt-Slots via Livewire (kein Login nötig).
    Gibt {uid: slot_dict} zurück, kompatibel mit bot.py run_check().
    Wirft RuntimeError("LOEWENBRAEU_RATELIMIT") bei HTTP 429.

    Pro Datum: frischer GET (sauberer Snapshot), dann 1× POST (date)
    → Schicht-Optionen aus booking_list_id-SELECT. Kein 2. POST nötig,
    da das Portal keinen Bereichs-Select hat (Canvas-basierte Tischauswahl).
    """
    session = _mk_session()

    print("  [Löwenbräuzelt] GET /reservierung …", end=" ", flush=True)
    csrf_token, snapshot, dates = _fetch_portal(session)
    print(f"{len(dates)} Datum/-Daten: {dates}", flush=True)

    slots = {}

    for i, datum in enumerate(dates):
        # Ab dem 2. Datum: frischer GET, damit der Snapshot sauber ist
        # (sonst klebt der booking_list_id-State vom vorigen Datum drin)
        if i > 0:
            time.sleep(_POST_DELAY)
            print(f"  [Löwenbräuzelt] GET (refresh) für {datum} …", end=" ", flush=True)
            csrf_token, snapshot, _ = _fetch_portal(session)
            print("ok", flush=True)

        # POST: Datum setzen → Schicht-Optionen
        time.sleep(_POST_DELAY)
        print(f"  [Löwenbräuzelt] POST {datum} (date) …", end=" ", flush=True)
        snapshot, html_frag = _post_livewire(
            session, snapshot, csrf_token,
            {"data.createBookingStepOneForm.date": datum},
        )
        bl_options = _extract_bl_options(html_frag)
        print(f"{len(bl_options)} Schicht(en)", flush=True)

        if not bl_options:
            print(f"  [Löwenbräuzelt] Warnung: {datum} hat 0 Schichten – überspringe")
            continue

        for bl_id, bl_name in bl_options:
            if "mittag" not in bl_name.lower():
                print(f"  [Löwenbräuzelt] HINWEIS: Schicht '{bl_name}' ist nicht 'Mittag' – Zeit-Default 17:00")

            start_str, end_str = _times_for_shift(bl_name)
            start_utc = _to_utc_iso(datum, start_str)
            end_utc   = _to_utc_iso(datum, end_str)

            uid = f"loewenbraeu_{datum}_{bl_id}"
            slots[uid] = {
                "uid":            uid,
                "name":           f"Löwenbräuzelt {bl_name} {datum}",
                "date":           datum,
                "areas":          [{"label": bl_name, "start": start_utc, "end": end_utc}],
                "earliest_start": start_utc,
            }

    return slots
