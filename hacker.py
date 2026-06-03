"""
Hacker Festzelt Livewire-Checker für den Wiesn-Bot.
check_hacker() → {uid: slot_dict}, kompatibel mit bot.py run_check().

UID-Format: hacker_{datum}_{booking_list_id}_{area_id}

Variante (Tag 14, 03.06.2026 verifiziert): MISCHFORM
  POST 1 (Datum)  → booking_list_id-Dropdown (Schichten, z.B. 1679 = "Mittag")
  POST 2 (Schicht)→ seatplan_area_id-Dropdown (Bereiche, dynamisch ausgelesen)
Reservierungs-URL: /reservierung (nicht /reservation/ wie bei Bräurosl)

Bereiche werden DYNAMISCH aus der POST-2-Response gelesen (kein KNOWN_AREAS mehr) —
so werden auch Storno-Slots für bereits gebuchte Bereiche erfasst.
Die <option>-Tags stecken in Livewire-Kommentaren (<!--[if BLOCK]>-->) und über
mehrere Zeilen — daher zweistufiges Parsen (_parse_options): erst Kommentare
entfernen, dann value+Text auslesen.
"""
import html as htmllib
import re
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

_BOOKING_URL = "https://reservierung.derhimmelderbayern.de/reservierung"
_BASE        = "https://reservierung.derhimmelderbayern.de"
_UA          = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_MUNICH_TZ   = ZoneInfo("Europe/Berlin")
_POST_DELAY  = 3

# Schicht-Zeiten-Default (Münchner Zeit). Start steuert den Push-Filter:
#   Mittag-Start 12:00 → "afternoon" → Push nur Fr/Sa/So
#   Abend-Start  17:00 → "evening"   → Push jeden Tag
_MITTAG_START = "12:00"
_MITTAG_END   = "16:45"
_ABEND_START  = "17:00"
_ABEND_END    = "22:30"


def _mk_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent":      _UA,
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9",
    })
    return s


def _find_select(html, field_id):
    m = re.search(
        rf'id="{re.escape(field_id)}"[^>]*>(.*?)</select>',
        html, re.DOTALL | re.IGNORECASE,
    )
    return m.group(1) if m else ""


def _parse_options(select_inner_html):
    """Zweistufig: Livewire-Kommentare entfernen, dann (value, name) je <option>.
    Leere Platzhalter-Option (value="") und leere Namen werden übersprungen."""
    clean = re.sub(r'<!--\[if [^\]]*\]><!\[endif\]-->', '', select_inner_html)
    out = []
    for val, inner in re.findall(
        r'<option[^>]*\svalue="([^"]*)"[^>]*>(.*?)</option>',
        clean, re.DOTALL,
    ):
        name = htmllib.unescape(re.sub(r'<[^>]+>', '', inner)).strip()
        if val.strip() and name:
            out.append((val.strip(), name))
    return out


def _extract_csrf(html):
    m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    return m.group(1) if m else ""


def _extract_portal_snapshot(html):
    for raw in re.findall(r'wire:snapshot="([^"]+)"', html):
        decoded = htmllib.unescape(raw)
        if "createBookingStepOneForm" in decoded:
            return decoded
    return None


def _extract_dates(html):
    block = _find_select(html, "data.createBookingStepOneForm.date")
    return re.findall(r'value="(\d{4}-\d{2}-\d{2})"', block) if block else []


def _extract_bl_options(html_frag):
    """Schichten (booking_list_id) aus POST-1-Response. (bl_id, name)-Tupel."""
    return _parse_options(_find_select(html_frag, "data.createBookingStepOneForm.booking_list_id"))


def _extract_areas(html_frag):
    """Bereiche (seatplan_area_id) aus POST-2-Response. Liste von {id, name}."""
    return [
        {"id": aid, "name": name}
        for aid, name in _parse_options(
            _find_select(html_frag, "data.createBookingStepOneForm.seatplan_area_id")
        )
    ]


def _shift_times(shift_name):
    """Default-Zeiten je Schicht. 'mittag' → 12:00–16:45, sonst → 17:00–22:30."""
    if "mittag" in shift_name.lower():
        return _MITTAG_START, _MITTAG_END
    return _ABEND_START, _ABEND_END


def _to_utc_iso(datum, uhrzeit):
    dt = datetime(
        int(datum[:4]), int(datum[5:7]), int(datum[8:10]),
        int(uhrzeit[:2]), int(uhrzeit[3:5]),
        tzinfo=_MUNICH_TZ,
    )
    return dt.astimezone(timezone.utc).isoformat()


def _post_livewire(session, snapshot, csrf_token, updates):
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
        raise RuntimeError("HACKER_RATELIMIT")
    r.raise_for_status()

    new_snap  = snapshot
    html_frag = ""
    for comp in r.json().get("components", []):
        if comp.get("snapshot"):
            new_snap = comp["snapshot"]
        html_frag += comp.get("effects", {}).get("html", "")
    return new_snap, html_frag


def check_hacker():
    """
    Prüft verfügbare Hacker-Slots via Livewire (kein Login nötig).
    Gibt {uid: slot_dict} zurück, kompatibel mit bot.py run_check().
    Wirft RuntimeError("HACKER_RATELIMIT") bei HTTP 429.

    Ablauf pro Datum: POST 1 (Datum) → Schichten; je Schicht POST 2 → Bereiche
    dynamisch. Pro (Datum, Schicht, Bereich) eine UID.
    """
    session = _mk_session()

    print("  [Hacker] GET /reservierung …", end=" ", flush=True)
    r0 = session.get(_BOOKING_URL, timeout=20)
    r0.raise_for_status()
    print(f"HTTP {r0.status_code}", flush=True)

    csrf_token    = _extract_csrf(r0.text)
    base_snapshot = _extract_portal_snapshot(r0.text)
    dates         = _extract_dates(r0.text)

    if not csrf_token:
        raise RuntimeError("HACKER: CSRF-Token nicht im HTML gefunden")
    if base_snapshot is None:
        raise RuntimeError("HACKER: wire:snapshot nicht im HTML gefunden")
    if not dates:
        print("  [Hacker] 0 Daten im SELECT — Portal noch gesperrt")
        return {}

    print(f"  [Hacker] {len(dates)} Datum/-Daten im SELECT: {dates}")

    slots = {}
    for i, datum in enumerate(dates):
        if i > 0:
            time.sleep(_POST_DELAY)
        print(f"  [Hacker] POST {datum} …", end=" ", flush=True)
        snap1, html1 = _post_livewire(
            session, base_snapshot, csrf_token,
            {"data.createBookingStepOneForm.date": datum},
        )
        shifts = _extract_bl_options(html1)
        print(f"{len(shifts)} Schicht(en)", flush=True)
        if not shifts:
            continue

        for bl_id, shift_name in shifts:
            time.sleep(_POST_DELAY)
            print(f"  [Hacker]   POST Schicht '{shift_name}' …", end=" ", flush=True)
            _snap2, html2 = _post_livewire(
                session, snap1, csrf_token,
                {"data.createBookingStepOneForm.booking_list_id": bl_id},
            )
            areas = _extract_areas(html2)
            print(f"{len(areas)} Bereich(e)", flush=True)
            if not areas:
                continue

            start_hhmm, end_hhmm = _shift_times(shift_name)
            start_utc = _to_utc_iso(datum, start_hhmm)
            end_utc   = _to_utc_iso(datum, end_hhmm)

            for area in areas:
                uid = f"hacker_{datum}_{bl_id}_{area['id']}"
                slots[uid] = {
                    "uid":            uid,
                    "name":           f"Hacker {datum} {shift_name} – {area['name']}",
                    "date":           datum,
                    "areas":          [{"label": area["name"], "start": start_utc, "end": end_utc}],
                    "earliest_start": start_utc,
                }

    return slots
