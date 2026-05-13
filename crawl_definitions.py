"""
Einmaliger Definitions-Crawl für alle Schottenhamel-Schichten.
Speichert Area-Zeiten pro UID in definitions_cache.json.
"""
import json, time, urllib.request, urllib.error

HEADERS = {
    "x-festzelt-os-company": "KDLWJDR",
    "Accept": "application/json",
    "Referer": "https://reservierung.festhalle-schottenhamel.de/",
    "Origin":  "https://reservierung.festhalle-schottenhamel.de",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}
BASE = "https://schottenhamel-api.festzelt-os.com"
DELAY = 3      # Sekunden zwischen Calls
COOLDOWN = 90  # Sekunden nach 429


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def fetch_definitions(uid):
    return fetch(f"{BASE}/lp/guestlists/{uid}/definitions")


def main():
    with open("shift_baseline.json") as f:
        guestlists = json.load(f)["data"]

    # Bestehenden Cache laden (für Fortsetzung nach Abbruch)
    try:
        with open("definitions_cache.json") as f:
            cache = json.load(f)
        print(f"Bestehender Cache geladen: {len(cache)} Einträge.")
    except FileNotFoundError:
        cache = {}

    total = len(guestlists)
    for i, shift in enumerate(guestlists):
        uid = shift["uid"]
        label = shift["name"]

        if uid in cache:
            print(f"[{i+1}/{total}] {uid} ({label}) — übersprungen (im Cache)")
            continue

        print(f"[{i+1}/{total}] {uid} ({label}) — abrufen ...", end=" ", flush=True)
        retry = 0
        while True:
            try:
                data = fetch_definitions(uid)
                areas = data["data"]["areas"]
                cache[uid] = {
                    "uid": uid,
                    "name": label,
                    "date": shift["date"][:10],
                    "shift_label": shift["shift"]["label"],
                    "shift_id": shift["shift"]["id"],
                    "areas": [
                        {
                            "id": a["id"],
                            "label": a["label"],
                            "start": a.get("start"),
                            "end":   a.get("end"),
                        }
                        for a in areas
                    ],
                }
                # Früheste Startzeit dieser Schicht (über alle Areas)
                starts = [a["start"] for a in cache[uid]["areas"] if a["start"]]
                cache[uid]["earliest_start"] = min(starts) if starts else None
                print(f"OK ({len(areas)} Areas, frühester Start: {cache[uid]['earliest_start']})")
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and retry < 2:
                    print(f"\n  429 — warte {COOLDOWN}s ...", end=" ", flush=True)
                    time.sleep(COOLDOWN)
                    retry += 1
                    continue
                else:
                    print(f"FEHLER {e.code} — übersprungen")
                    break
            except Exception as ex:
                print(f"FEHLER {ex} — übersprungen")
                break

        # Cache nach jedem Eintrag speichern
        with open("definitions_cache.json", "w") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

        if i < total - 1:
            time.sleep(DELAY)

    print(f"\nFertig. Cache: {len(cache)}/{total} Schichten gespeichert.")

    # Kompakte Übersicht ausgeben
    print("\n=== Definitions-Cache Übersicht ===")
    print(f"{'UID':<10} {'Datum':<12} {'Schicht':<12} {'Frühester Start':<22} {'Areas'}")
    print("-" * 75)
    for uid, d in sorted(cache.items(), key=lambda x: x[1]["date"]):
        area_labels = ", ".join(a["label"] for a in d["areas"])
        print(f"{uid:<10} {d['date']:<12} {d['shift_label']:<12} {str(d['earliest_start']):<22} {area_labels}")


if __name__ == "__main__":
    main()
