"""
Armbrustschützenzelt "Spontan"-Checker für den Wiesn-Bot.
check_armbrust_spontan() → {uid: slot_dict}, kompatibel mit bot.py run_check().

Das Spontan-Portal (servus.armbrustschuetzenzelt.de) ist KEIN Livewire-Portal,
sondern statisches HTML. Es werden ausschließlich GETs gemacht, keine POSTs.

UID-Format: armbrust_spontan_{datum}_{schicht}
  schicht = HHMM der frühesten gefundenen Uhrzeit, sonst "unbekannt".

Ablauf:
1. GET /reservierung → Kalender-HTML. Jeder Tag ist ein
   <div class="cal-day ..."> mit <a href="/reservierung/termin/<ID>"> und
   dem Datum als Text ("TT.MM.").
2. Für jeden Tag, dessen Klassen NICHT "disabled" enthalten: GET auf
   /reservierung/termin/<ID>, Inhalt des .card-body auswerten (min. 3s Pause
   zwischen den Abrufen).
3. Ist der card-body nicht leer, gilt der Tag als frei. Uhrzeiten im Format
   HH:MM werden gesucht; ohne Treffer bleibt earliest_start None und der Slot
   wird als "Uhrzeit unbekannt" markiert (soll trotzdem gepusht werden).
"""
import re
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

_BASE      = "https://servus.armbrustschuetzenzelt.de"
_CAL_URL   = f"{_BASE}/reservierung"
_UA        = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_MUNICH_TZ = ZoneInfo("Europe/Berlin")
_GET_DELAY = 3

_DAY_RE  = re.compile(
    r'<div class="([^"]*\bcal-day\b[^"]*)">.*?'
    r'<a[^>]*href="(/reservierung/termin/[^"]+)"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_DATE_RE = re.compile(r'(\d{1,2})\.(\d{1,2})\.')
_TIME_RE = re.compile(r'\b([01]\d|2[0-3]):([0-5]\d)\b')


def _mk_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent":      _UA,
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9",
    })
    return s


def _guess_year(day, month):
    """Ordnet einem TT.MM.-Datum (ohne Jahr) das passende Jahr zu.

    Kalender-Tage liegen immer in der (nahen) Zukunft. Liegt das Datum mit dem
    aktuellen Jahr weit (>60 Tage) in der Vergangenheit, gehört es ins nächste
    Jahr (Silvester-Rollover).
    """
    today = datetime.now(_MUNICH_TZ).date()
    year = today.year
    try:
        candidate = datetime(year, month, day).date()
    except ValueError:
        candidate = datetime(year + 1, month, day).date()
        return candidate.isoformat()
    if (today - candidate).days > 60:
        candidate = datetime(year + 1, month, day).date()
    return candidate.isoformat()


def _extract_days(html):
    """Liste von (datum_iso, termin_id, ist_frei) aus dem Kalender-HTML."""
    days = []
    for classes, href, inner in _DAY_RE.findall(html):
        m = _DATE_RE.search(inner)
        if not m:
            continue
        day, month = int(m.group(1)), int(m.group(2))
        datum = _guess_year(day, month)
        termin_id = href.rsplit("/", 1)[-1]
        ist_frei = "disabled" not in classes.split()
        days.append((datum, termin_id, ist_frei))
    return days


def _extract_card_body(html):
    """Innerer Text des ersten .card-body-Divs (Tag-Zählung, robust gegen
    verschachteltes HTML). None, wenn kein card-body gefunden wurde."""
    m = re.search(r'<div[^>]*class="[^"]*\bcard-body\b[^"]*"[^>]*>', html)
    if not m:
        return None
    pos = m.end()
    depth = 1
    for tag in re.finditer(r'<div\b|</div>', html[pos:]):
        if tag.group(0) == "</div>":
            depth -= 1
            if depth == 0:
                inner = html[pos:pos + tag.start()]
                return re.sub(r'<[^>]+>', ' ', inner)
        else:
            depth += 1
    return re.sub(r'<[^>]+>', ' ', html[pos:])


def _to_utc_iso(datum, uhrzeit):
    dt = datetime(
        int(datum[:4]), int(datum[5:7]), int(datum[8:10]),
        int(uhrzeit[:2]), int(uhrzeit[3:5]),
        tzinfo=_MUNICH_TZ,
    )
    return dt.astimezone(timezone.utc).isoformat()


def check_armbrust_spontan():
    """
    Prüft die Armbrust-Spontan-Seite (statisches HTML, kein Login, nur GETs).
    Gibt {uid: slot_dict} zurück, kompatibel mit bot.py run_check().
    """
    session = _mk_session()

    print("  [Armbrust-Spontan] GET /reservierung …", end=" ", flush=True)
    r = session.get(_CAL_URL, timeout=20)
    r.raise_for_status()
    days = _extract_days(r.text)
    offene_tage = [d for d in days if d[2]]
    print(f"{len(days)} Tag(e) im Kalender, {len(offene_tage)} nicht 'disabled'.", flush=True)

    slots = {}

    for datum, termin_id, _frei in offene_tage:
        time.sleep(_GET_DELAY)
        url = f"{_BASE}/reservierung/termin/{termin_id}"
        print(f"  [Armbrust-Spontan] GET {datum} ({termin_id}) …", end=" ", flush=True)
        try:
            r = session.get(url, timeout=20)
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"HTTP-Fehler: {e}")
            continue

        body_text = _extract_card_body(r.text)
        body_text = re.sub(r'\s+', ' ', body_text).strip() if body_text else ""
        if not body_text:
            print("kein Inhalt / ausgebucht.")
            continue

        times = sorted({f"{h}:{m}" for h, m in _TIME_RE.findall(body_text)})

        if times:
            start_str    = times[0]
            end_str      = times[-1] if len(times) > 1 else None
            schicht      = start_str.replace(":", "")
            zeit_hinweis = ""
        else:
            start_str    = None
            end_str      = None
            schicht      = "unbekannt"
            zeit_hinweis = " (Uhrzeit unbekannt)"

        start_utc = _to_utc_iso(datum, start_str) if start_str else None
        end_utc   = _to_utc_iso(datum, end_str) if end_str else None

        uid = f"armbrust_spontan_{datum}_{schicht}"
        slots[uid] = {
            "uid":            uid,
            "name":           f"Armbrustschützenzelt Spontan {datum}{zeit_hinweis}",
            "date":           datum,
            "areas":          [{"label": "Spontan", "start": start_utc, "end": end_utc}],
            "earliest_start": start_utc,
        }
        print(f"frei{zeit_hinweis}.", flush=True)

    return slots


if __name__ == "__main__":
    for uid, slot in check_armbrust_spontan().items():
        print(uid, "→", slot)
