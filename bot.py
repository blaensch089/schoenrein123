#!/usr/bin/env python3
"""
Schottenhamel Wiesn-Reservierungs-Monitor
Pollt /lp/guestlists alle N Minuten, filtert auf relevante Schichten,
pusht via Telegram.

Filter (Münchner Zeit):
  ≥ 17:00          → immer pushen ("🌙 ABENDSCHICHT")
  13:00 – 16:59    → nur Fr/Sa/So pushen
  < 13:00          → kein Push

Usage:
  python3 bot.py          # normaler Polling-Betrieb
  python3 bot.py --test   # Startup-Report + simulierter Test-Push
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo

# ── .env ohne externe Abhängigkeit ────────────────────────────────────────────
def _load_env(path=".env"):
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip().strip('"\''))
    except FileNotFoundError:
        pass

_load_env()

# ── Konfiguration ──────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")
POLL_INTERVAL  = int(os.environ.get("POLL_INTERVAL_SECONDS", "480"))  # 8 Minuten

API_BASE     = "https://schottenhamel-api.festzelt-os.com"
BOOKING_URL  = "https://reservierung.festhalle-schottenhamel.de/reservation/"
CACHE_FILE   = "definitions_cache.json"
STATE_FILE   = "state.json"
MUNICH_TZ    = ZoneInfo("Europe/Berlin")

_HEADERS = {
    "x-festzelt-os-company": "KDLWJDR",
    "Accept": "application/json",
    "Referer": "https://reservierung.festhalle-schottenhamel.de/",
    "Origin":  "https://reservierung.festhalle-schottenhamel.de",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}
_WEEKDAY_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
               "Freitag", "Samstag", "Sonntag"]


# ── Zeitzone ───────────────────────────────────────────────────────────────────
def to_munich(iso_utc):
    """ISO-UTC-String → datetime in Europe/Berlin. Gibt None zurück bei None."""
    if not iso_utc:
        return None
    return datetime.fromisoformat(iso_utc).astimezone(MUNICH_TZ)


# ── Filter ─────────────────────────────────────────────────────────────────────
def classify(earliest_start_utc):
    """
    "evening"   → ≥ 17:00 Uhr München
    "afternoon" → 13:00–16:59 Uhr München, nur Fr/Sa/So
    None        → kein Push
    """
    dt = to_munich(earliest_start_utc)
    if dt is None:
        return None
    hour = dt.hour + dt.minute / 60
    if hour >= 17:
        return "evening"
    if 13 <= hour < 17 and dt.weekday() in (4, 5, 6):  # Fr=4, Sa=5, So=6
        return "afternoon"
    return None


# ── HTTP-Helpers ───────────────────────────────────────────────────────────────
def _get(url):
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def fetch_guestlists():
    """Gibt {uid: shift_obj} zurück; bei 429 einmal 90 s warten."""
    for attempt in range(2):
        try:
            data = _get(f"{API_BASE}/lp/guestlists")
            return {s["uid"]: s for s in data["data"]}
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 0:
                print("  429 — warte 90 s ...")
                time.sleep(90)
            else:
                raise
    return {}


# ── Telegram ───────────────────────────────────────────────────────────────────
def telegram_send(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("  [Telegram] Kein Token/Chat-ID konfiguriert → Push übersprungen.")
        return False
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read())
            if not result.get("ok"):
                print(f"  [Telegram] API-Fehler: {result}")
            return result.get("ok", False)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  [Telegram] HTTP {e.code}: {body[:200]}")
        return False
    except Exception as ex:
        print(f"  [Telegram] Fehler: {ex}")
        return False


# ── Nachricht formatieren ──────────────────────────────────────────────────────
def format_push(cached, classification):
    uid   = cached["uid"]
    name  = cached.get("name", uid)
    date  = cached.get("date", "")      # "2026-09-21"
    areas = cached.get("areas", [])

    # Datum schön formatieren
    try:
        dt_date = datetime.fromisoformat(date)
        wochentag = _WEEKDAY_DE[dt_date.weekday()]
        datum_str = f"{wochentag}, {date[8:10]}.{date[5:7]}.{date[:4]}"
    except Exception:
        datum_str = date

    # Area-Zeilen mit Münchner Zeiten
    area_lines = []
    for a in sorted(areas, key=lambda x: x.get("start") or ""):
        s = to_munich(a.get("start"))
        e = to_munich(a.get("end"))
        if s and e:
            area_lines.append(f"  • {a['label']}: {s.strftime('%H:%M')}–{e.strftime('%H:%M')}")
        elif a.get("label"):
            area_lines.append(f"  • {a['label']}")
    areas_text = "\n".join(area_lines) if area_lines else "  (keine Bereichsdaten)"

    if classification == "evening":
        header = "🌙 <b>ABENDSCHICHT VERFÜGBAR!</b>"
    else:
        header = "🕓 <b>Nachmittag-Schicht frei (Fr/Sa/So)</b>"

    return (
        f"{header}\n\n"
        f"<b>{datum_str}</b>\n"
        f"{name}\n\n"
        f"<b>Bereiche &amp; Uhrzeiten (München):</b>\n{areas_text}\n\n"
        f"UID: <code>{uid}</code>\n"
        f'<a href="{BOOKING_URL}">👉 Jetzt buchen</a>'
    )


# ── State ──────────────────────────────────────────────────────────────────────
def state_load():
    try:
        with open(STATE_FILE) as f:
            return set(json.load(f)["uids"])
    except FileNotFoundError:
        return None


def state_save(uid_set):
    with open(STATE_FILE, "w") as f:
        json.dump({
            "uids": sorted(uid_set),
            "updated": datetime.now(MUNICH_TZ).isoformat(),
        }, f, indent=2)


# ── Startup-Report ─────────────────────────────────────────────────────────────
def print_startup_report(current_shifts, cache):
    print()
    print("=" * 72)
    print("SCHOTTENHAMEL WIESN-MONITOR — Startup-Report")
    print(f"Stand: {datetime.now(MUNICH_TZ).strftime('%Y-%m-%d %H:%M:%S')} (München)")
    print("=" * 72)
    header = f"{'#':<3} {'Datum':<12} {'Label':<12} {'Start MUC':<10} {'Filter':<14} Name"
    print(header)
    print("-" * 72)

    match_count = 0
    for i, (uid, shift) in enumerate(
        sorted(current_shifts.items(), key=lambda x: x[1]["date"]), 1
    ):
        cached = cache.get(uid, {})
        earliest = cached.get("earliest_start")
        dt_m = to_munich(earliest)
        time_str = dt_m.strftime("%H:%M") if dt_m else "?"
        clf = classify(earliest)
        clf_label = {"evening": "🌙 ABEND", "afternoon": "🕓 NACHM."}.get(clf, "—")
        if clf:
            match_count += 1
        print(f"{i:<3} {shift['date'][:10]:<12} {shift['shift']['label']:<12} "
              f"{time_str:<10} {clf_label:<14} {shift['name']}")

    print("-" * 72)
    print(f"Aktive Schichten im Filter: {match_count}")
    if match_count == 0:
        print("→ Kein Match — Bot wartet auf ausgebuchte Abendschichten die wiederkehren.")
    else:
        print("→ Diese Schichten sind bereits aktiv und werden beim nächsten neuen Auftauchen gepusht.")
        print("  (Beim ersten Start wird kein Push ausgelöst — nur Änderungen danach zählen.)")
    print()


# ── Test-Push ──────────────────────────────────────────────────────────────────
def run_test_push():
    print("[TEST] Simuliere Abendschicht Sa 19.09.2026 19:00 Uhr ...")
    fake = {
        "uid": "TEST001",
        "name": "TEST — Samstag, 19.09.2026 - Abend",
        "date": "2026-09-19",
        "areas": [
            {"label": "Halle Süd/Mitte",
             "start": "2026-09-19T17:00:00+00:00", "end": "2026-09-19T21:30:00+00:00"},
            {"label": "Galerie",
             "start": "2026-09-19T17:00:00+00:00", "end": "2026-09-19T21:00:00+00:00"},
            {"label": "Balkon",
             "start": "2026-09-19T17:00:00+00:00", "end": "2026-09-19T21:00:00+00:00"},
        ],
        "earliest_start": "2026-09-19T17:00:00+00:00",
    }
    msg = format_push(fake, "evening")
    print()
    print("─── Nachricht (Preview) ───────────────────────────────")
    print(msg)
    print("───────────────────────────────────────────────────────")
    print()
    ok = telegram_send(msg)
    status = "✓ Zugestellt" if ok else "✗ Fehlgeschlagen (Token/Chat-ID in .env prüfen)"
    print(f"[TEST] Telegram-Versand: {status}")


# ── Ein Poll-Zyklus ────────────────────────────────────────────────────────────
def run_check(current, last_uids, cache):
    """Vergleicht aktuellen Stand mit last_uids, pusht bei Treffern.
    Gibt aktuelle UID-Menge zurück."""
    ts = datetime.now(MUNICH_TZ).strftime("%H:%M:%S")
    current_uids = set(current.keys())
    appeared = current_uids - last_uids

    if not appeared:
        print(f"[{ts}] Keine Änderung — {len(current_uids)} Schichten aktiv.")
    else:
        print(f"[{ts}] {len(appeared)} neue Schicht(en): {appeared}")
        for uid in appeared:
            cached = cache.get(uid)
            if cached is None:
                shift_obj = current.get(uid, {})
                cached = {
                    "uid": uid,
                    "name": shift_obj.get("name", uid),
                    "date": shift_obj.get("date", "")[:10],
                    "areas": [],
                    "earliest_start": None,
                }
                print(f"  ! UID {uid} nicht im Cache — kein Zeitfilter möglich, Push wird unterdrückt.")
                print(f"    Bitte crawl_definitions.py erneut ausführen um den Cache zu aktualisieren.")
                continue

            clf = classify(cached.get("earliest_start"))
            if clf:
                msg = format_push(cached, clf)
                print(f"  → Push [{clf}]: {cached['name']}")
                telegram_send(msg)
            else:
                start_str = cached.get("earliest_start", "?")
                print(f"  → Kein Push (Filter): {cached['name']} "
                      f"[Start: {to_munich(start_str).strftime('%H:%M') if to_munich(start_str) else '?'} Uhr]")

    state_save(current_uids)
    return current_uids


# ── Haupt-Loop ─────────────────────────────────────────────────────────────────
def main():
    test_mode = "--test" in sys.argv
    once_mode = "--once" in sys.argv

    if not os.path.exists(CACHE_FILE):
        print(f"Fehler: {CACHE_FILE} nicht gefunden.")
        print("Bitte zuerst crawl_definitions.py ausführen.")
        sys.exit(1)

    with open(CACHE_FILE) as f:
        cache = json.load(f)

    print("Lade aktuelle Schicht-Liste von der API ...")
    current = fetch_guestlists()
    print(f"  → {len(current)} Schichten empfangen.")

    print_startup_report(current, cache)

    if test_mode:
        run_test_push()
        return

    last_uids = state_load()
    if last_uids is None:
        print("Kein State-File gefunden — initialisiere mit aktuellem Stand.")
        last_uids = set(current.keys())
        state_save(last_uids)
        print(f"State gespeichert: {len(last_uids)} Schichten.")

    if once_mode:
        run_check(current, last_uids, cache)
        return

    print(f"Polling-Intervall: {POLL_INTERVAL} s. Strg+C zum Beenden.\n")

    while True:
        time.sleep(POLL_INTERVAL)
        ts = datetime.now(MUNICH_TZ).strftime("%H:%M:%S")

        try:
            current = fetch_guestlists()
        except Exception as e:
            print(f"[{ts}] API-Fehler: {e}")
            continue

        last_uids = run_check(current, last_uids, cache)


if __name__ == "__main__":
    main()
