"""
Hacker Festzelt Livewire-Checker für den Wiesn-Bot.
check_hacker() → {uid: slot_dict}, kompatibel mit bot.py run_check().

UID-Format: hacker_{datum}_{area_id}_{startzeit_hhmm}

booking_list_group_id=55 liegt fest im Livewire-Snapshot.
Reservierungs-URL: /reservierung (nicht /reservation/ wie bei Bräurosl)

TODO (nach Münchner-Kontingent-Vergabe 19.05.2026 ab 10:00 Uhr):
  KNOWN_AREAS mit echten Area-IDs und -Namen aus dem Portal befüllen.
  Bis dahin liefert check_hacker() 0 Slots → keine Pushes.
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

# TODO: nach Kontingent-Vergabe 19.05.2026 befüllen (Area-IDs aus Portal-Response)
KNOWN_AREAS = []

_DEFAULT_START = "11:00"
_DEFAULT_END   = "22:00"  # Hacker: Abendschichten möglich — Fallback bis Recherche


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
    block = _find_select(html_frag, "data.createBookingStepOneForm.booking_list_id")
    if not block:
        return []
    return [
        (bid, name.strip())
        for bid, name in re.findall(r'value="(\d+)"[^>]*>([^<]+)', block)
    ]


def _extract_areas(html_frag):
    """Seatplan-Areas aus POST-Response-HTML (nach Freischaltung verfügbar)."""
    block = _find_select(html_frag, "data.createBookingStepOneForm.seatplan_area_id")
    if not block:
        return []
    return [
        {"id": aid, "name": name.strip()}
        for aid, name in re.findall(r'value="(\d+)"[^>]*>([^<\n]+)', block)
        if aid and name.strip()
    ]


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

    Solange KNOWN_AREAS leer ist (TODO noch offen), werden 0 Slots
    zurückgegeben — kein Push, aber Datum-SELECT wird bereits geloggt.
    """
    session = _mk_session()

    print("  [Hacker] GET /reservierung …", end=" ", flush=True)
    r0 = session.get(_BOOKING_URL, timeout=20)
    r0.raise_for_status()
    print(f"HTTP {r0.status_code}", flush=True)

    csrf_token = _extract_csrf(r0.text)
    snapshot   = _extract_portal_snapshot(r0.text)
    dates      = _extract_dates(r0.text)

    if not csrf_token:
        raise RuntimeError("HACKER: CSRF-Token nicht im HTML gefunden")
    if snapshot is None:
        raise RuntimeError("HACKER: wire:snapshot nicht im HTML gefunden")

    if not dates:
        print("  [Hacker] 0 Daten im SELECT — Portal noch gesperrt (Vergabe 19.05.2026)")
        return {}

    print(f"  [Hacker] {len(dates)} Datum/-Daten im SELECT: {dates}")

    if not KNOWN_AREAS:
        print(f"  [Hacker] {len(dates)} Daten gefunden, aber KNOWN_AREAS leer — TODO offen")
        return {}

    slots = {}

    for i, datum in enumerate(dates):
        if i > 0:
            time.sleep(_POST_DELAY)
        print(f"  [Hacker] POST {datum} …", end=" ", flush=True)

        snapshot, html_frag = _post_livewire(
            session, snapshot, csrf_token,
            {"data.createBookingStepOneForm.date": datum},
        )

        bl_options = _extract_bl_options(html_frag)
        print(f"{len(bl_options)} Schicht(en)", flush=True)

        if not bl_options:
            continue

        start_utc = _to_utc_iso(datum, _DEFAULT_START)
        end_utc   = _to_utc_iso(datum, _DEFAULT_END)

        for area in KNOWN_AREAS:
            uid = f"hacker_{datum}_{area['id']}_{_DEFAULT_START.replace(':', '')}"
            slots[uid] = {
                "uid":            uid,
                "name":           f"Hacker {datum} {area['name']}",
                "date":           datum,
                "areas":          [{"label": area["name"], "start": start_utc, "end": end_utc}],
                "earliest_start": start_utc,
            }

    return slots
