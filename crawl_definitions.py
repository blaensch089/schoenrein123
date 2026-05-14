"""
Definitions-Crawl für alle Festzelt-OS Typ-A-Zelte.
Speichert Area-Zeiten pro UID in definitions_cache_<id>.json.
Zelte mit vorhandenem Cache werden übersprungen.
"""
import json, os, shutil, time, urllib.request, urllib.error

DELAY    = 3    # Sekunden zwischen API-Calls
COOLDOWN = 90   # Sekunden nach 429

TENTS = [
    {
        "id":       "schottenhamel",
        "name":     "Schottenhamel",
        "api_base": "https://schottenhamel-api.festzelt-os.com",
        "company":  "KDLWJDR",
        "referer":  "https://reservierung.festhalle-schottenhamel.de/",
        "origin":   "https://reservierung.festhalle-schottenhamel.de",
    },
    {
        "id":       "schuetzen",
        "name":     "Schützenfestzelt",
        "api_base": "https://schuetzen-api.festzelt-os.com",
        "company":  "M5RN1H1",
        "referer":  "https://reservierung.schuetzenfestzelt.com/",
        "origin":   "https://reservierung.schuetzenfestzelt.com",
    },
    {
        "id":       "marstall",
        "name":     "Marstall",
        "api_base": "https://marstall-api.festzelt-os.com",
        "company":  "J12J1KA",
        "referer":  "https://reservierung.marstall-oktoberfest.de/",
        "origin":   "https://reservierung.marstall-oktoberfest.de",
    },
    {
        "id":       "weinzelt",
        "name":     "Weinzelt",
        "api_base": "https://api.festzelt-os.com",
        "company":  "FOSKUFW4711",
        "referer":  "https://reservierung.weinzelt.com/",
        "origin":   "https://reservierung.weinzelt.com",
    },
]


def make_headers(tent):
    return {
        "x-festzelt-os-company": tent["company"],
        "Accept":     "application/json",
        "Referer":    tent["referer"],
        "Origin":     tent["origin"],
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }


def fetch(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def crawl_tent(tent):
    cache_file = f"definitions_cache_{tent['id']}.json"
    headers    = make_headers(tent)

    # Schottenhamel: Migration aus altem Dateinamen
    if tent["id"] == "schottenhamel" and not os.path.exists(cache_file):
        if os.path.exists("definitions_cache.json"):
            shutil.copy2("definitions_cache.json", cache_file)
            print(f"  Cache migriert: definitions_cache.json → {cache_file}")

    if os.path.exists(cache_file):
        with open(cache_file) as f:
            n = len(json.load(f))
        print(f"  {tent['name']}: Cache vorhanden ({n} Einträge) — übersprungen.")
        return

    print(f"\n{'='*60}")
    print(f"Crawle: {tent['name']}")
    print(f"{'='*60}")

    print("  Lade Guestlists …", end=" ", flush=True)
    guestlists = fetch(f"{tent['api_base']}/lp/guestlists", headers)["data"]
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
            except urllib.error.HTTPError as e:
                if e.code == 429 and retry < 2:
                    print(f"\n  429 — warte {COOLDOWN}s …", end=" ", flush=True)
                    time.sleep(COOLDOWN)
                    retry += 1
                else:
                    print(f"FEHLER HTTP {e.code} — übersprungen")
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
