#!/usr/bin/env python3
"""
Wiesn-Reservierungs-Monitor — 4 Festzelte (Typ A: festzelt-os.com REST-API)

Usage:
  python3 bot.py               # Polling-Betrieb
  python3 bot.py --once        # einmaliger Check (GitHub Actions)
  python3 bot.py --once --test # Test-Push ohne echten API-Check
"""
import json, os, sys, time, shutil
from datetime import datetime
from zoneinfo import ZoneInfo

import requests


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

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")
POLL_INTERVAL  = int(os.environ.get("POLL_INTERVAL_SECONDS", "480"))
TENT_DELAY     = 3  # Sekunden zwischen Zelten

MUNICH_TZ   = ZoneInfo("Europe/Berlin")
STATE_FILE  = "state.json"
_WEEKDAY_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
               "Freitag", "Samstag", "Sonntag"]

TENTS = [
    {
        "id":          "schottenhamel",
        "name":        "Schottenhamel",
        "api_base":    "https://schottenhamel-api.festzelt-os.com",
        "company":     "KDLWJDR",
        "referer":     "https://reservierung.festhalle-schottenhamel.de/",
        "origin":      "https://reservierung.festhalle-schottenhamel.de",
        "booking_url": "https://reservierung.festhalle-schottenhamel.de/reservation/",
        "needs_login": False,
    },
    {
        "id":              "schuetzen",
        "name":            "Schützenfestzelt",
        "api_base":        "https://schuetzen-api.festzelt-os.com",
        "company":         "M5RN1H1",
        "referer":         "https://reservierung.schuetzenfestzelt.com/",
        "origin":          "https://reservierung.schuetzenfestzelt.com",
        "booking_url":     "https://reservierung.schuetzenfestzelt.com/reservation/",
        "needs_login":     True,
        "login_endpoint":  "https://schuetzen-api.festzelt-os.com/lp/auth/login",
        "cred_number_env": "SCHUETZEN_CUSTOMER_NUMBER",
        "cred_password_env": "SCHUETZEN_PASSWORD",
    },
    {
        "id":          "marstall",
        "name":        "Marstall",
        "api_base":    "https://marstall-api.festzelt-os.com",
        "company":     "J12J1KA",
        "referer":     "https://reservierung.marstall-oktoberfest.de/",
        "origin":      "https://reservierung.marstall-oktoberfest.de",
        "booking_url": "https://reservierung.marstall-oktoberfest.de/reservation",
        "needs_login": False,
    },
    {
        "id":          "weinzelt",
        "name":        "Weinzelt",
        "api_base":    "https://api.festzelt-os.com",
        "company":     "FOSKUFW4711",
        "referer":     "https://reservierung.weinzelt.com/",
        "origin":      "https://reservierung.weinzelt.com",
        "booking_url": "https://reservierung.weinzelt.com/reservation/",
        "needs_login": False,
    },
]

INITIAL_BURST_THRESHOLD = 10


# ── Zeitzone / Filter ──────────────────────────────────────────────────────────
def to_munich(iso_utc):
    if not iso_utc:
        return None
    return datetime.fromisoformat(iso_utc).astimezone(MUNICH_TZ)


def classify(earliest_start_utc):
    dt = to_munich(earliest_start_utc)
    if dt is None:
        return None
    hour = dt.hour + dt.minute / 60
    if hour >= 17:
        return "evening"
    if 13 <= hour < 17 and dt.weekday() in (4, 5, 6):
        return "afternoon"
    return None


# ── HTTP ───────────────────────────────────────────────────────────────────────
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _headers(tent):
    return {
        "Accept":                "application/json, text/plain, */*",
        "x-festzelt-os-Company": tent["company"],
        "Referer":               tent["referer"],
        "Origin":                tent["origin"],
        "User-Agent":            _UA,
    }


def _get(url, headers):
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_token(tent) -> str:
    """Holt Bearer-Token via POST login. Passwort wird sofort nach Verwendung gelöscht."""
    customer_number = os.environ.get(tent["cred_number_env"], "")
    password        = os.environ.get(tent["cred_password_env"], "")
    if not customer_number or not password:
        raise ValueError(
            f"Login-Daten für {tent['name']} fehlen "
            f"({tent['cred_number_env']} / {tent['cred_password_env']})"
        )
    time.sleep(3)
    try:
        resp = requests.post(
            tent["login_endpoint"],
            json={"customer_number": customer_number, "password": password},
            headers={
                "Accept":                "application/json, text/plain, */*",
                "Content-Type":          "application/json",
                "x-festzelt-os-Company": tent["company"],
                "User-Agent":            _UA,
            },
            timeout=15,
        )
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code
        if code == 401:
            raise ValueError(f"Login fehlgeschlagen ({tent['name']}): ungültige Zugangsdaten")
        raise ValueError(f"Login HTTP {code} ({tent['name']}): {e.response.text[:200]}")
    finally:
        del password
    try:
        return resp.json()["data"]["token"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Token nicht in Login-Response ({tent['name']}): {exc}")


def fetch_guestlists(tent):
    """Gibt {uid: shift_obj} zurück; bei 429 einmal 90 s warten."""
    headers = _headers(tent)
    if tent.get("needs_login"):
        token = fetch_token(tent)
        headers["Authorization"] = f"Bearer {token}"
        del token
    for attempt in range(2):
        try:
            data = _get(f"{tent['api_base']}/lp/guestlists", headers)
            return {s["uid"]: s for s in data["data"]}
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt == 0:
                print(f"  [{tent['name']}] 429 — warte 90 s …")
                time.sleep(90)
            else:
                raise
    return {}


# ── Telegram ───────────────────────────────────────────────────────────────────
def telegram_send(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("  [Telegram] Token/Chat-ID fehlt → übersprungen.")
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id":                  TELEGRAM_CHAT,
                "text":                     text,
                "parse_mode":               "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        result = resp.json()
        if not result.get("ok"):
            print(f"  [Telegram] Fehler: {result}")
        return result.get("ok", False)
    except requests.exceptions.HTTPError as e:
        print(f"  [Telegram] HTTP {e.response.status_code}: {e.response.text[:200]}")
        return False
    except Exception as ex:
        print(f"  [Telegram] {ex}")
        return False


# ── Nachricht ──────────────────────────────────────────────────────────────────
def format_push(cached, clf, tent):
    uid   = cached["uid"]
    date  = cached.get("date", "")
    areas = cached.get("areas", [])

    try:
        d = datetime.fromisoformat(date)
        datum_str = f"{_WEEKDAY_DE[d.weekday()]}, {date[8:10]}.{date[5:7]}.{date[:4]}"
    except Exception:
        datum_str = date

    area_lines = []
    for a in sorted(areas, key=lambda x: x.get("start") or ""):
        s, e = to_munich(a.get("start")), to_munich(a.get("end"))
        if s and e:
            area_lines.append(f"  • {a['label']}: {s.strftime('%H:%M')}–{e.strftime('%H:%M')}")
        elif a.get("label"):
            area_lines.append(f"  • {a['label']}")
    areas_text = "\n".join(area_lines) or "  (keine Bereichsdaten)"

    header = ("🌙 <b>ABENDSCHICHT VERFÜGBAR!</b>"
              if clf == "evening"
              else "🕓 <b>Nachmittag-Schicht frei (Fr/Sa/So)</b>")

    return (
        f"{header}\n\n"
        f"🍺 <b>{tent['name']}</b>\n"
        f"<b>{datum_str}</b>\n"
        f"{cached.get('name', uid)}\n\n"
        f"<b>Bereiche &amp; Uhrzeiten (München):</b>\n{areas_text}\n\n"
        f"UID: <code>{uid}</code>\n"
        f'<a href="{tent["booking_url"]}">👉 Jetzt buchen</a>'
    )


def format_summary_push(tent, appeared_uids, cache, *, first_run=False):
    total   = len(appeared_uids)
    evening = sum(
        1 for uid in appeared_uids
        if cache.get(uid) and classify(cache[uid].get("earliest_start")) == "evening"
    )
    afternoon = sum(
        1 for uid in appeared_uids
        if cache.get(uid) and classify(cache[uid].get("earliest_start")) == "afternoon"
    )
    label = "Initial-Lauf" if first_run else "Bulk-Update"
    return (
        f"🍺 <b>{tent['name']}</b>: {label}, {total} Schichten erfasst.\n"
        f"Abendschichten: <b>{evening}</b>, Nachmittag-WE: <b>{afternoon}</b>.\n"
        f"Ab nächstem Lauf werden nur noch neue Treffer gemeldet."
    )


# ── State ──────────────────────────────────────────────────────────────────────
def state_load():
    try:
        with open(STATE_FILE) as f:
            raw = json.load(f)
        # Migration: altes Format hatte "uids" direkt auf top-level (nur Schottenhamel)
        if "uids" in raw and not any(t["id"] in raw for t in TENTS):
            return {"schottenhamel": set(raw["uids"])}
        return {k: set(v["uids"]) for k, v in raw.items() if isinstance(v, dict) and "uids" in v}
    except FileNotFoundError:
        return {}


def state_save(state):
    now = datetime.now(MUNICH_TZ).isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(
            {tid: {"uids": sorted(uids), "updated": now} for tid, uids in state.items()},
            f, indent=2,
        )


# ── Cache laden ────────────────────────────────────────────────────────────────
def load_caches():
    caches = {}
    for tent in TENTS:
        cf = f"definitions_cache_{tent['id']}.json"
        # Schottenhamel: Migration aus altem Dateinamen
        if tent["id"] == "schottenhamel" and not os.path.exists(cf):
            if os.path.exists("definitions_cache.json"):
                shutil.copy2("definitions_cache.json", cf)
                print(f"Cache migriert: definitions_cache.json → {cf}")
        if os.path.exists(cf):
            with open(cf) as f:
                caches[tent["id"]] = json.load(f)
            print(f"Cache: {tent['name']} — {len(caches[tent['id']])} Einträge")
        else:
            caches[tent["id"]] = {}
            print(f"WARNUNG: {cf} fehlt — crawl_definitions.py ausführen!")
    return caches


# ── Check ──────────────────────────────────────────────────────────────────────
def run_check(tent, current, last_uids, cache, *, first_run=False):
    ts = datetime.now(MUNICH_TZ).strftime("%H:%M:%S")
    current_uids = set(current.keys())
    appeared = current_uids - last_uids

    if not appeared:
        print(f"[{ts}] [{tent['name']}] Keine Änderung ({len(current_uids)} Schichten).")
    elif first_run or len(appeared) >= INITIAL_BURST_THRESHOLD:
        label = "Initial-Lauf" if first_run else "Bulk"
        print(f"[{ts}] [{tent['name']}] {label}: {len(appeared)} neu — sende Summary.")
        telegram_send(format_summary_push(tent, appeared, cache, first_run=first_run))
    else:
        print(f"[{ts}] [{tent['name']}] {len(appeared)} neu: {appeared}")
        for uid in appeared:
            cached = cache.get(uid)
            if cached is None:
                print(f"  ! {uid} nicht im Cache — Push unterdrückt.")
                continue
            clf = classify(cached.get("earliest_start"))
            if clf:
                print(f"  → Push [{clf}]: {cached['name']}")
                telegram_send(format_push(cached, clf, tent))
            else:
                dt = to_munich(cached.get("earliest_start"))
                print(f"  → Filter: {cached['name']} [{dt.strftime('%H:%M') if dt else '?'}]")
    return current_uids


# ── Test-Push ──────────────────────────────────────────────────────────────────
def run_test_push():
    print("\n[TEST] Sende simulierte Abendschicht für jedes Zelt …")
    for i, tent in enumerate(TENTS):
        if i > 0:
            time.sleep(TENT_DELAY)
        fake = {
            "uid":            f"TEST-{tent['id'][:4].upper()}",
            "name":           f"TEST — {tent['name']} Abend",
            "date":           "2026-09-19",
            "areas":          [{"label": "Halle",
                                "start": "2026-09-19T17:00:00+00:00",
                                "end":   "2026-09-19T21:30:00+00:00"}],
            "earliest_start": "2026-09-19T17:00:00+00:00",
        }
        ok = telegram_send(format_push(fake, "evening", tent))
        print(f"  [{tent['name']}] {'✓ Zugestellt' if ok else '✗ Fehlgeschlagen'}")


# ── Haupt-Loop ─────────────────────────────────────────────────────────────────
def main():
    test_mode = "--test" in sys.argv
    once_mode = "--once" in sys.argv

    caches = load_caches()

    if test_mode:
        run_test_push()
        return

    state = state_load()

    print("\nLade Schicht-Listen …")
    for i, tent in enumerate(TENTS):
        if i > 0:
            time.sleep(TENT_DELAY)
        print(f"  {tent['name']} …", end=" ", flush=True)
        try:
            current = fetch_guestlists(tent)
        except Exception as ex:
            print(f"Fehler: {ex} — übersprungen.")
            continue
        print(f"{len(current)} Schichten.")

        tid = tent["id"]
        if tid not in state:
            new_uids = run_check(tent, current, set(), caches[tid], first_run=True)
            state[tid] = new_uids
            state_save(state)
        else:
            new_uids = run_check(tent, current, state[tid], caches[tid])
            state[tid] = new_uids
            state_save(state)

    if once_mode:
        return

    print(f"\nPolling alle {POLL_INTERVAL} s. Strg+C zum Beenden.\n")
    while True:
        time.sleep(POLL_INTERVAL)
        for i, tent in enumerate(TENTS):
            if i > 0:
                time.sleep(TENT_DELAY)
            try:
                current = fetch_guestlists(tent)
            except requests.exceptions.HTTPError as e:
                print(f"  [{tent['name']}] HTTP {e.response.status_code} — übersprungen.")
                continue
            except Exception as ex:
                print(f"  [{tent['name']}] {ex} — übersprungen.")
                continue
            new_uids = run_check(tent, current, state[tent["id"]], caches[tent["id"]])
            state[tent["id"]] = new_uids
            state_save(state)


if __name__ == "__main__":
    main()
