# Login-Analyse: Schützenfestzelt — Technischer Mechanismus

**Datum:** 2026-05-15  
**Methode:** Statische JS-Bundle-Analyse (kein Login-Versuch, keine Zugangsdaten)

---

## Zusammenfassung

Der Login ist ein einfacher JSON-POST ohne CSRF-Token. Kein Browser nötig — `requests` reicht.

---

## 1. Login-URL und HTTP-Methode

**Vollständige URL:**
```
POST https://schuetzen-api.festzelt-os.com/lp/auth/login
```

Gefunden in Bundle 3 (`f178119.js`), Nuxt-Auth-Modul-Konfiguration:
```javascript
endpoints: {
  login:  { url: "auth/login",       method: "post" },
  logout: { url: "auth/logout",      method: "post" },
  user:   { url: "contact/profile",  method: "get"  }
},
name: "local"
```

Die Basis-URL des Axios-Clients lautet `https://schuetzen-api.festzelt-os.com/lp`, daher:
- Login:   `POST https://schuetzen-api.festzelt-os.com/lp/auth/login`
- Logout:  `POST https://schuetzen-api.festzelt-os.com/lp/auth/logout`
- Profil:  `GET  https://schuetzen-api.festzelt-os.com/lp/contact/profile`

---

## 2. Login-Formular-Felder

**Kein E-Mail-Feld! Login erfolgt mit Kundennummer + Passwort.**

Gefunden in Chunk `4ec0ece.js`, Modul 572 (AuthInlineLoginForm-Component):

```javascript
// Vue-Component data():
data: function() {
  return {
    customer_number: "",
    password: ""
  }
},

// Submit-Handler:
e.$auth.login({
  data: {
    customer_number: e.customer_number,
    password: e.password
  }
})
```

**POST-Body (JSON):**
```json
{
  "customer_number": "XXXXXXXX",
  "password": "YYYYYYYY"
}
```

**Formular-Validierung:**
- `customer_number`: required
- `password`: required

---

## 3. CSRF-Token

**Kein CSRF-Token erforderlich.**

Das Nuxt-Auth-Modul (local strategy) schickt keinen CSRF-Token. Es gibt keinen Hidden-Input,
kein Cookie-to-Header-Muster, keine `X-CSRF-Token`-Logik im Login-Flow. Direkter JSON-POST reicht.

---

## 4. Session-Mechanismus nach dem Login

**Bearer-Token in `Authorization`-Header.**

Auth-Modul-Konfiguration (`f178119.js`):
```javascript
token: {
  property:          "token",         // JSON-Feld in der Login-Response
  type:              "Bearer",
  name:              "Authorization", // Header-Name
  maxAge:            1800,            // Token-Gültigkeit: 30 Minuten
  global:            true,            // Wird bei ALLEN Requests mitgeschickt
  required:          true,
  prefix:            "_token.",
  expirationPrefix:  "_token_expiration."
}
```

**Ablauf:**
1. `POST /lp/auth/login` → Response enthält `{ "token": "eyJ..." }`
2. Token wird gespeichert
3. Alle folgenden Requests erhalten: `Authorization: Bearer eyJ...`
4. Nach 1800 Sekunden (30 Min) ist der Token abgelaufen → Neu-Login nötig

**Kein Refresh-Token:** Die App-Konfiguration enthält keinen `refresh`-Endpunkt. Bei Ablauf muss der Login-POST wiederholt werden.

---

## 5. Vollständige Request-Headers

Beim Login müssen folgende Headers gesetzt werden (Axios-Default-Konfiguration aus `22ff6a7.js`):

```python
headers = {
    "Accept":                "application/json, text/plain, */*",
    "Content-Type":          "application/json",
    "x-festzelt-os-Company": "M5RN1H1",   # Mandanten-ID Schützenfestzelt
}
```

Nach dem Login kommt für alle weiteren Requests dazu:
```python
headers["Authorization"] = f"Bearer {token}"
```

---

## 6. API-Konfiguration (vollständig)

Aus Bundle 4 (`22ff6a7.js`), eingebettet in die App-Config:

```javascript
env: {
  onlinePaymentEnabled: false,
  BASE_URL:    "https://reservierung.schuetzen-festzelt.com",
  API_BASE_URL: "https://schuetzen-api.festzelt-os.com/lp",
  COMPANY_UID: "M5RN1H1",
  APP_NAME:    "Schützen-Festzelt Reinbold OHG",
  CONTACT_FORM_ACTIVE: "0",
  ALWAYS_ENABLE_PROFILE_UPDATE: "1",
}
```

---

## 7. Login-Seite im Frontend

Route im Vue Router: `/auth`  
URL: `https://reservierung.schuetzenfestzelt.com/auth`

Weitere Auth-Routen:
- `/auth/forgot` — Passwort vergessen (benötigt Kundennummer, schickt Reset-Mail)
- `/auth/forgot/update` — Neues Passwort setzen

---

## 8. Lässt sich das mit `requests` lösen?

**Ja, vollständig mit `requests` (oder `urllib`). Kein Playwright nötig.**

Der gesamte Ablauf ist reines HTTP:

```python
import requests, time

SESSION_DURATION = 1700  # etwas weniger als 1800s, um Ablauf zu vermeiden

BASE_API = "https://schuetzen-api.festzelt-os.com/lp"
HEADERS_BASE = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "x-festzelt-os-Company": "M5RN1H1",
}

def login(customer_number: str, password: str) -> str:
    """Gibt den Bearer-Token zurück."""
    resp = requests.post(
        f"{BASE_API}/auth/login",
        json={"customer_number": customer_number, "password": password},
        headers=HEADERS_BASE,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["token"]   # Token-Property laut Auth-Config: "token"

def get_guestlists(token: str) -> list:
    """Gibt die Guestlists zurück (eingeloggt → vermutlich 16 Schichten)."""
    headers = {**HEADERS_BASE, "Authorization": f"Bearer {token}"}
    resp = requests.get(
        f"{BASE_API}/guestlists",
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])
```

---

## 9. Token-Ablauf und Re-Login-Strategie für den Bot

Da der Token nach 30 Minuten abläuft und kein Refresh-Mechanismus existiert,
muss der Bot bei jedem Polling-Zyklus prüfen, ob ein Re-Login nötig ist.

Empfohlene Implementierung:

```python
import time

token = None
token_expiry = 0

def ensure_token(customer_number, password):
    global token, token_expiry
    if time.time() > token_expiry - 60:  # 60s Puffer vor Ablauf
        token = login(customer_number, password)
        token_expiry = time.time() + 1700
    return token
```

---

## 10. Offene Fragen / Nächste Schritte

| Frage | Status |
|-------|--------|
| Gibt es tatsächlich 16 Tage bei auth. `/lp/guestlists`? | Zu verifizieren (erster echte Login-Test) |
| Unterschied anonymous vs. auth bei `/lp/guestlists`? | Zu verifizieren |
| Ist der Response-Key `"token"` oder `"data"."token"`? | Fast sicher `"token"` (Auth-Config: `property:"token"`) |
| Braucht `/lp/guestlists` Auth oder reicht anon+Mandant? | Anon liefert 2, Auth soll 16 liefern |
| Rate-Limit beim Login-Endpoint? | Unbekannt, defensiv ≥3s Pause einhalten |

---

## Anhang: Relevante Code-Stellen

### A. Axios-Basis-Konfiguration (Bundle 4, `22ff6a7.js`)
```javascript
var e = ml({
  baseURL: "https://schuetzen-api.festzelt-os.com/lp",
  headers: {
    common: { Accept: "application/json, text/plain, */*" },
    "x-festzelt-os-Company": "M5RN1H1"
  }
});
```

### B. Auth-Modul-Konfiguration (Bundle 3, `f178119.js`)
```javascript
// Standard Nuxt-Auth-Default (Basis):
{
  endpoints: {
    login:  { url: "/api/auth/login",  method: "post" },
    logout: { url: "/api/auth/logout", method: "post" },
    user:   { url: "/api/auth/user",   method: "get"  }
  },
  token: {
    property: "token", type: "Bearer", name: "Authorization",
    maxAge: 1800, global: true, required: true,
    prefix: "_token.", expirationPrefix: "_token_expiration."
  },
  user: { property: "user", autoFetch: true },
  clientId: false, grantType: false, scope: false
}

// App-spezifische Überschreibung (aktiv):
{
  user: { property: "data" },
  endpoints: {
    login:  { url: "auth/login",      method: "post" },
    logout: { url: "auth/logout",     method: "post" },
    user:   { url: "contact/profile", method: "get"  }
  },
  name: "local"
}
```

### C. AuthInlineLoginForm Submit-Logik (Chunk `4ec0ece.js`, Modul 572)
```javascript
// data()
{ customer_number: "", password: "" }

// submit()
e.$auth.login({
  data: {
    customer_number: e.customer_number,
    password:        e.password
  }
})

// Fehlerbehandlung: 401 → Alert "Ungültige Zugangsdaten"
// Gesperrte Accounts → Alert "Benutzerkonto gesperrt"
```
