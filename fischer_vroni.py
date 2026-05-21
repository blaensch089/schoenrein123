import re, json, time, requests
from datetime import datetime
from zoneinfo import ZoneInfo

PORTAL_URL   = "https://reservierung.fischer-vroni.de/reservation"
LIVEWIRE_URL = "https://reservierung.fischer-vroni.de/livewire/update"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9",
}

_MUNICH_TZ = ZoneInfo("Europe/Berlin")
_WDAY_DE   = ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"]


def _parse_options(html, field_id):
    pattern = rf'<select[^>]+id="{re.escape(field_id)}"[^>]*>(.*?)</select>'
    m = re.search(pattern, html, re.DOTALL)
    if not m:
        return []
    inner = re.sub(r'<!--.*?-->', '', m.group(1), flags=re.DOTALL)
    opts  = re.findall(r'<option[^>]+value="([^"]*)"[^>]*>(.*?)</option>', inner, re.DOTALL)
    result = []
    for val, label in opts:
        val   = val.strip()
        label = re.sub(r'<[^>]+>', '', label).strip()
        if val:
            result.append((val, label))
    return result


def get_available_slots(tent):
    session = requests.Session()
    slots   = []

    resp = session.get(PORTAL_URL, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    html = resp.text

    csrf_m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    if not csrf_m:
        raise RuntimeError("Fischer Vroni: CSRF-Token nicht gefunden")
    csrf_token = csrf_m.group(1)

    snap_m = re.search(r'wire:snapshot="([^"]+)"', html)
    if not snap_m:
        raise RuntimeError("Fischer Vroni: Livewire-Snapshot nicht gefunden")
    snapshot = json.loads(snap_m.group(1).replace("&quot;", '"'))

    date_opts = _parse_options(html, "data.createBookingStepOneForm.date")
    if not date_opts:
        return []

    lw_headers = {
        **_HEADERS,
        "X-Csrf-Token": csrf_token,
        "X-Livewire":   "true",
        "Content-Type": "application/json",
        "Accept":       "text/html, application/xhtml+xml",
        "Referer":      PORTAL_URL,
    }

    for date_val, _date_label in date_opts:
        time.sleep(2)
        payload = {
            "components": [{
                "snapshot": json.dumps(snapshot),
                "updates":  {"data.createBookingStepOneForm.date": date_val},
                "calls":    []
            }]
        }
        resp2 = session.post(LIVEWIRE_URL, headers=lw_headers,
                             json=payload, timeout=20)
        if resp2.status_code == 429:
            print(f"  [Fischer Vroni] 429 – überspringe {date_val}")
            time.sleep(60)
            continue
        resp2.raise_for_status()

        try:
            j          = resp2.json()
            components = j.get("components", [])
            if not components:
                continue
            comp      = components[0]
            html_frag = (comp.get("effects") or {}).get("html") or ""
            new_snap  = comp.get("snapshot")
            if new_snap:
                snapshot = json.loads(new_snap)
            shift_opts = _parse_options(
                html_frag, "data.createBookingStepOneForm.booking_list_id"
            )
            for shift_val, shift_label in shift_opts:
                if "mittag" in shift_label.lower():
                    start_time, end_time = "11:00", "16:45"
                else:
                    start_time, end_time = "17:00", "22:30"
                slots.append({
                    "uid":        f"{date_val}_{shift_val}",
                    "date":       date_val,
                    "shift_name": shift_label,
                    "areas":      [shift_label],
                    "start_time": start_time,
                    "end_time":   end_time,
                })
        except Exception as e:
            print(f"  [Fischer Vroni] Fehler bei {date_val}: {e}")
            continue

    return slots


def check_fischer_vroni():
    """Gibt {uid: slot_dict} zurück — Format identisch zu anderen Livewire-Modulen."""
    slots  = get_available_slots({})
    result = {}
    for s in slots:
        date_val = s["date"]
        dt_start = datetime.strptime(
            f"{date_val} {s['start_time']}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=_MUNICH_TZ)
        dt_end   = datetime.strptime(
            f"{date_val} {s['end_time']}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=_MUNICH_TZ)
        try:
            d         = datetime.fromisoformat(date_val)
            datum_str = (f"{_WDAY_DE[d.weekday()]}, "
                         f"{date_val[8:10]}.{date_val[5:7]}.{date_val[:4]}")
        except Exception:
            datum_str = date_val
        uid = s["uid"]
        result[uid] = {
            "uid":            uid,
            "date":           date_val,
            "name":           f"{s['shift_name']} — {datum_str}",
            "areas":          [{"label": s["shift_name"],
                                "start": dt_start.isoformat(),
                                "end":   dt_end.isoformat()}],
            "earliest_start": dt_start.isoformat(),
        }
    return result
