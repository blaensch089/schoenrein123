"""
Bräurosl Livewire-Checker für den Wiesn-Bot.
check_braeurosl() → {uid: slot_dict}, kompatibel mit bot.py run_check().

UID-Format: braeurosl_{datum}_{area_id}_{startzeit_hhmm}

Sitzplan-Bereiche aus Recherche (Mai 2026): alle 10 Daten haben
konstant dieselben 4 Areas (629/630/632/634). seatplan_area SELECT
erscheint erst nach zwei POSTs (date + booking_list_id), daher werden
bekannte Areas per Fallback eingesetzt.

Schichtzeit: 11:00–16:45 Uhr (Mittag, konsistent laut Phantom-Check).
"""
import html as htmllib
import re
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

_BOOKING_URL = "https://reservierung.braeurosl.de/reservation/"
_BASE        = "https://reservierung.braeurosl.de"
_UA          = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_MUNICH_TZ   = ZoneInfo("Europe/Berlin")
_POST_DELAY  = 3

# Sitzplan-Bereiche aus Recherche (konstant für Bräurosl Oktoberfest 2026)
_AREAS = [
    {"id": "629", "name": "Boxen"},
    {"id": "630", "name": "Brauerei Box"},
    {"id": "632", "name": "Mittelschiff Ost"},
    {"id": "634", "name": "Mittelschiff West"},
]
_DEFAULT_START = "11:00"
_DEFAULT_END   = "16:45"


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


def _extract_bl_options(html_frag):
    """booking_list_id-Optionen (Schicht-Optionen) aus POST-Response-HTML."""
    block = _find_select(html_frag, "data.createBookingStepOneForm.booking_list_id")
    if not block:
        return []
    return [
        (bid, name.strip())
        for bid, name in re.findall(r'value="(\d+)"[^>]*>([^<]+)', block)
    ]


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
        raise RuntimeError("BRAEUROSL_RATELIMIT")
    r.raise_for_status()

    new_snap  = snapshot
    html_frag = ""
    for comp in r.json().get("components", []):
        if comp.get("snapshot"):
            new_snap = comp["snapshot"]
        html_frag += comp.get("effects", {}).get("html", "")
    return new_snap, html_frag


def check_braeurosl():
    """
    Prüft verfügbare Bräurosl-Slots via Livewire (kein Login nötig).
    Gibt {uid: slot_dict} zurück, kompatibel mit bot.py run_check().
    Wirft RuntimeError("BRAEUROSL_RATELIMIT") bei HTTP 429.
    """
    session = _mk_session()

    print("  [Bräurosl] GET /reservation/ …", end=" ", flush=True)
    r0 = session.get(_BOOKING_URL, timeout=20)
    r0.raise_for_status()
    print(f"HTTP {r0.status_code}", flush=True)

    csrf_token = _extract_csrf(r0.text)
    snapshot   = _extract_portal_snapshot(r0.text)
    dates      = _extract_dates(r0.text)

    if not csrf_token:
        raise RuntimeError("BRAEUROSL: CSRF-Token nicht im HTML gefunden")
    if snapshot is None:
        raise RuntimeError("BRAEUROSL: wire:snapshot nicht im HTML gefunden")

    print(f"  [Bräurosl] {len(dates)} Datum/-Daten im SELECT: {dates}")

    slots = {}

    for i, datum in enumerate(dates):
        if i > 0:
            time.sleep(_POST_DELAY)
        print(f"  [Bräurosl] POST {datum} …", end=" ", flush=True)

        snapshot, html_frag = _post_livewire(
            session, snapshot, csrf_token,
            {"data.createBookingStepOneForm.date": datum},
        )

        bl_options = _extract_bl_options(html_frag)
        print(f"{len(bl_options)} Schicht(en)", flush=True)

        if not bl_options:
            print(f"  [Bräurosl] Warnung: {datum} im SELECT, aber keine Schicht-Option in Response")
            continue

        start_utc = _to_utc_iso(datum, _DEFAULT_START)
        end_utc   = _to_utc_iso(datum, _DEFAULT_END)

        for area in _AREAS:
            uid = f"braeurosl_{datum}_{area['id']}_{_DEFAULT_START.replace(':', '')}"
            slots[uid] = {
                "uid":            uid,
                "name":           f"Bräurosl Mittag {datum} {area['name']}",
                "date":           datum,
                "areas":          [{"label": area["name"], "start": start_utc, "end": end_utc}],
                "earliest_start": start_utc,
            }

    return slots
