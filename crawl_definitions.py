"""
Definitions-Crawl für alle Festzelt-OS Typ-A-Zelte.
Speichert Area-Zeiten pro UID in definitions_cache_<id>.json.
Bestehende Cache-Dateien werden überschrieben.
"""
import json, os, time

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

DELAY    = 3    # Sekunden zwischen API-Calls
COOLDOWN = 90   # Sekunden nach 429

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

TENTS = [
    {
        "id":          "schottenhamel",
        "name":        "Schottenhamel",
        "api_base":    "https://schottenhamel-api.festzelt-os.com",
        "company":     "KDLWJDR",
        "referer":     "https://reservierung.festhalle-schottenhamel.de/",
        "origin":      "https://reservierung.festhalle-schottenhamel.de",
        "needs_login": False,
    },
    {
        "id":              "schuetzen",
        "name":            "Schützenfestzelt",
        "api_base":        "https://schuetzen-api.festzelt-os.com",
        "company":         "M5RN1H1",
        "referer":         "https://reservierung.schuetzenfestzelt.com/",
        "origin":          "https://reservierung.schuetzenfestzelt.com",
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
        "needs_login": False,
    },
    {
        "id":          "weinzelt",
        "name":        "Weinzelt",
        "api_base":    "https://api.festzelt-os.com",
        "company":     "FOSKUFW4711",
        "referer":     "https://reservierung.weinzelt.com/",
        "origin":      "https://reservierung.weinzelt.com",
        "needs_login": False,
    },
]


def _base_headers(tent):
    return {
        "Accept":                "application/json, text/plain, */*",
        "x-festzelt-os-Company": tent["company"],
        "Referer":               tent["referer"],
        "Origin":                tent["origin"],
        "User-Agent":            _UA,
    }


def fetch_token(tent) -> str:
    """Holt Bearer-Token via POST login. Passwort wird sofort nach Verwendung gelöscht."""
    customer_number = os.environ.get(tent["cred_number_env"], "")
    password        = os.environ.get(tent["cred_password_env"], "")
    if not customer_number or not password:
        raise ValueError(
            f"Login-Daten für {tent['name']} fehlen "
            f"({tent['cred_number_env']} / {tent['cred_password_env']})"
        )
    time.sleep(DELAY)
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


def fetch(url, headers):
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def crawl_tent(tent):
    cache_file = f"definitions_cache_{tent['id']}.json"

    # Login wenn nötig
    token = None
    if tent.get("needs_login"):
        try:
            token = fetch_token(tent)
        except (ValueError, requests.exceptions.RequestException) as e:
            print(f"  {tent['name']}: Login-Fehler: {e} — überspringe.")
            return

    headers = _base_headers(tent)
    if token:
        headers["Authorization"] = f"Bearer {token}"
        del token

    print(f"\n{'='*60}")
    print(f"Crawle: {tent['name']}")
    print(f"{'='*60}")

    print("  Lade Guestlists …", end=" ", flush=True)
    try:
        guestlists = fetch(f"{tent['api_base']}/lp/guestlists", headers)["data"]
    except Exception as e:
        print(f"FEHLER: {e}")
        return
    print(f"{len(guestlists)} Schichten.")
    time.sleep(DELAY)

    cache = {}
    total = len(guestlists)
    for i, shift in enumerate(guestlists):
        uid   = shift["uid"]
        label = shift["name"]
        print(f"  [{i+1}/{total}] {uid} ({label}) …", end=" ", flush=True)

        retry = 0
        while True:
            try:
                data  = fetch(f"{tent['api_base']}/lp/guestlists/{uid}/definitions", headers)
                areas = data["data"]["areas"]
                cache[uid] = {
                    "uid":         uid,
                    "name":        label,
                    "date":        shift["date"][:10],
                    "shift_label": shift["shift"]["label"],
                    "shift_id":    shift["shift"]["id"],
                    "areas": [
                        {"id": a["id"], "label": a["label"],
                         "start": a.get("start"), "end": a.get("end")}
                        for a in areas
                    ],
                }
                starts = [a["start"] for a in cache[uid]["areas"] if a["start"]]
                cache[uid]["earliest_start"] = min(starts) if starts else None
                print(f"OK ({len(areas)} Areas)")
                break
            except requests.exceptions.HTTPError as e:
                code = e.response.status_code
                if code == 429 and retry < 2:
                    print(f"\n  429 — warte {COOLDOWN}s …", end=" ", flush=True)
                    time.sleep(COOLDOWN)
                    retry += 1
                else:
                    print(f"FEHLER HTTP {code} — übersprungen")
                    break
            except Exception as ex:
                print(f"FEHLER {ex} — übersprungen")
                break

        with open(cache_file, "w") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

        if i < total - 1:
            time.sleep(DELAY)

    print(f"\n  → {tent['name']}: {len(cache)}/{total} Einträge gecacht in {cache_file}")


def main():
    for i, tent in enumerate(TENTS):
        if i > 0:
            time.sleep(DELAY)
        crawl_tent(tent)
    print("\nFertig.")


if __name__ == "__main__":
    main()
