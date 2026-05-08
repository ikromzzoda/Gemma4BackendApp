# Error Responses Documentation

This document describes exactly what each endpoint returns in three failure scenarios:

1. **OpenWeatherMap API unavailable** (no internet, timeout, HTTP error)
2. **Firestore (Firebase DB) unavailable**
3. **Ollama (AI) unavailable** — only relevant for `/api/advice/`

---

## How to read this document

Each endpoint section shows the exact JSON the frontend receives for each scenario, which `except` block fires, and whether the endpoint continues to work partially or fails completely.

---

## 1. POST /api/users/create/

### Scenario 1 — OpenWeatherMap unavailable
**Not applicable.** This endpoint makes no external API calls.

### Scenario 2 — Firestore unavailable

`user.save()` raises an exception → caught by `except Exception as e`.

**HTTP 500**
```json
{
  "status": "error",
  "error": "Internal server error",
  "detail": "<Firestore exception message>"
}
```
Endpoint **fails completely**. No data is returned.

### Scenario 3 — Ollama unavailable
**Not applicable.** This endpoint does not use Ollama.

---

## 2. PUT /api/users/\<uid\>/update/

### Scenario 1 — OpenWeatherMap unavailable
**Not applicable.** This endpoint makes no external API calls.

### Scenario 2 — Firestore unavailable

`User.collection.filter("uid", "==", uid).get()` raises an exception → caught by `except Exception as e`.

**HTTP 500**
```json
{
  "status": "error",
  "error": "Internal server error",
  "detail": "<Firestore exception message>"
}
```
Endpoint **fails completely** before reaching the update logic.

### Scenario 3 — Ollama unavailable
**Not applicable.**

---

## 3. GET /api/users/\<uid\>/

### Scenario 1 — OpenWeatherMap unavailable
**Not applicable.** This endpoint makes no external API calls.

### Scenario 2 — Firestore unavailable

`User.collection.filter("uid", "==", uid).get()` raises an exception → caught by `except Exception as e`.

**HTTP 500**
```json
{
  "status": "error",
  "error": "Internal server error",
  "detail": "<Firestore exception message>"
}
```
Endpoint **fails completely**.

### Scenario 3 — Ollama unavailable
**Not applicable.**

---

## 4. GET /api/air-pollution/

### Scenario 1 — OpenWeatherMap unavailable

`requests.get(...)` raises `requests.exceptions.RequestException` → caught by `except requests.exceptions.RequestException as e` inside `fetch_and_save_air_pollution()`. The caller view adds `"city"` to the result dict.

**HTTP 500**
```json
{
  "error": "API request failed: <requests exception message>",
  "city": "Dushanbe"
}
```
> Note: no `"status"` field — this endpoint intentionally omits it.

Endpoint **fails completely**.

### Scenario 2 — Firestore unavailable

The API call succeeds, then `AirPollution.collection.filter(...).fetch()` raises an exception → caught by `except Exception as e` inside `fetch_and_save_air_pollution()`.

**HTTP 500**
```json
{
  "error": "Error processing data: <Firestore exception message>",
  "city": "Dushanbe"
}
```
Endpoint **fails completely**. The successfully fetched API data is not returned to the frontend.

### Scenario 3 — Ollama unavailable
**Not applicable.**

---

## 5. GET /api/air-pollution/all/

### Scenario 1 — OpenWeatherMap unavailable
**Not applicable.** This endpoint reads only from Firestore.

### Scenario 2 — Firestore unavailable

`AirPollution.collection.fetch()` raises an exception → caught by `except Exception as e`.

**HTTP 500**
```json
{
  "error": "Error fetching data: <Firestore exception message>"
}
```
> Note: no `"status"` field.

Endpoint **fails completely**.

### Scenario 3 — Ollama unavailable
**Not applicable.**

---

## 6. GET /api/air-pollution/location/

### Scenario 1 — OpenWeatherMap unavailable

`requests.get(...)` raises `requests.exceptions.RequestException` → caught by the explicit `except requests.exceptions.RequestException as e` block.

**HTTP 500**
```json
{
  "error": "API request failed: <requests exception message>"
}
```
> Note: no `"status"` field.

Endpoint **fails completely**.

### Scenario 2 — Firestore unavailable

The API call succeeds and returns data. Then `AirPollution.collection.filter(...).fetch()` raises → caught by `except Exception as e`.

**HTTP 500**
```json
{
  "error": "Error fetching data: <Firestore exception message>"
}
```
Endpoint **fails completely**. The `fresh_data_from_api` that was already fetched is not returned to the frontend.

### Scenario 3 — Ollama unavailable
**Not applicable.**

---

## 7. GET /api/forecast/

### Scenario 1 — OpenWeatherMap unavailable

`requests.get(...)` raises `requests.exceptions.RequestException` → caught by the explicit `except requests.exceptions.RequestException` block (note: the exception is not bound to a variable here).

**HTTP 503**
```json
{
  "status": "error",
  "error": "OpenWeatherMap API unavailable"
}
```
Endpoint **fails completely**.

### Scenario 2 — Firestore unavailable
**Not applicable.** This endpoint makes **no Firestore calls**. It reads only from the OpenWeatherMap forecast API. Firestore being down has zero effect.

### Scenario 3 — Ollama unavailable
**Not applicable.**

---

## 8. GET /api/advice/

### Scenario 1 — OpenWeatherMap unavailable

`requests.get(...)` raises `requests.exceptions.RequestException` → caught by the explicit `except requests.exceptions.RequestException` block.

**HTTP 503**
```json
{
  "status": "error",
  "error": "OpenWeatherMap API unavailable"
}
```
Endpoint **fails completely** before Ollama is ever called.

### Scenario 2 — Firestore unavailable
**Not applicable.** This endpoint makes **no Firestore calls**. Firestore being down has zero effect.

### Scenario 3 — Ollama unavailable

`requests.post(settings.OLLAMA_URL + "/api/generate", ...)` raises any exception (connection refused, timeout after 30s, HTTP error, etc.) → caught by the bare `except Exception` inside `generate_advice()`.

**The endpoint returns HTTP 200** with a fallback advice string instead of AI-generated text:

```json
{
  "status": "success",
  "data": {
    "city": "Dushanbe",
    "aqi": 2,
    "aqi_label": "Fair",
    "health_condition": "Asthma",
    "activity_level": "Active",
    "advice": "AQI is 2 (Fair). Please check local air quality guidelines for your health condition and activity level."
  }
}
```

The fallback template is:
```
"AQI is {aqi} ({aqi_label}). Please check local air quality guidelines for your health condition and activity level."
```

The frontend **cannot distinguish** between an AI-generated and a fallback response — both return `200` with the same JSON shape. There is no `"is_fallback"` flag.

---

## 9. GET /api/home/

### Scenario 1 — OpenWeatherMap unavailable

Both API calls (air pollution + weather) are inside a single try block. If either raises `requests.exceptions.RequestException` → caught by the explicit `except requests.exceptions.RequestException` block.

**HTTP 503**
```json
{
  "status": "error",
  "error": "OpenWeatherMap API unavailable"
}
```
Endpoint **fails completely**. Neither pollution nor weather data is returned.

### Scenario 2 — Firestore unavailable

Both API calls succeed. Then Firestore operations (`AirPollution.collection.filter(...).fetch()`, `.save()`, `WeatherData.collection.filter(...).fetch()`, `.save()`) are in the inner `try` block → any exception caught by `except Exception as e`.

**HTTP 500**
```json
{
  "status": "error",
  "error": "Internal server error",
  "detail": "<Firestore exception message>"
}
```
Endpoint **fails completely**. The successfully fetched API data is not returned to the frontend, even though it was retrieved.

### Scenario 3 — Ollama unavailable
**Not applicable.**

---

## 10. GET /api/map/

### Scenario 1 — OpenWeatherMap unavailable

Each city is processed in its own try/except loop. If `requests.get(...)` raises `requests.exceptions.RequestException` for a city → caught by `except requests.exceptions.RequestException` for that city only.

**HTTP 200** — The endpoint always returns 200. Failing cities produce a partial entry:

```json
{
  "status": "success",
  "data": {
    "pollutant": "AQI",
    "cities": [
      {
        "city": "Dushanbe",
        "lat": 38.5598,
        "lon": 68.7738,
        "aqi": 2,
        "aqi_label": "Fair",
        "pm25": 14.2,
        "pm10": 21.5,
        "o3": 55.41,
        "no2": 6.32,
        "temperature": 24.5
      },
      {
        "city": "Khorugh",
        "lat": 37.4897,
        "lon": 71.5528,
        "error": "Data unavailable"
      }
    ]
  }
}
```

If all 9 cities fail, all 9 entries will have `"error": "Data unavailable"` but the HTTP status is still `200`.

**Frontend must check** for the presence of `"error"` on each city object before reading pollutant values.

### Scenario 2 — Firestore unavailable
**Not applicable.** This endpoint makes **no Firestore calls**. Firestore being down has zero effect.

### Scenario 3 — Ollama unavailable
**Not applicable.**

---

## Summary Table

| Endpoint | Scenario | HTTP Status | Behavior |
|----------|----------|-------------|----------|
| `POST /api/users/create/` | OWM unavailable | — | Not affected |
| `POST /api/users/create/` | Firestore unavailable | **500** | Fails completely |
| `PUT /api/users/<uid>/update/` | OWM unavailable | — | Not affected |
| `PUT /api/users/<uid>/update/` | Firestore unavailable | **500** | Fails completely |
| `GET /api/users/<uid>/` | OWM unavailable | — | Not affected |
| `GET /api/users/<uid>/` | Firestore unavailable | **500** | Fails completely |
| `GET /api/air-pollution/` | OWM unavailable | **500** | Fails completely |
| `GET /api/air-pollution/` | Firestore unavailable | **500** | Fails completely (API data lost) |
| `GET /api/air-pollution/all/` | OWM unavailable | — | Not affected |
| `GET /api/air-pollution/all/` | Firestore unavailable | **500** | Fails completely |
| `GET /api/air-pollution/location/` | OWM unavailable | **500** | Fails completely |
| `GET /api/air-pollution/location/` | Firestore unavailable | **500** | Fails completely (API data lost) |
| `GET /api/forecast/` | OWM unavailable | **503** | Fails completely |
| `GET /api/forecast/` | Firestore unavailable | — | **Not affected** |
| `GET /api/advice/` | OWM unavailable | **503** | Fails completely |
| `GET /api/advice/` | Firestore unavailable | — | **Not affected** |
| `GET /api/advice/` | Ollama unavailable | **200** | Returns fallback advice string |
| `GET /api/home/` | OWM unavailable | **503** | Fails completely |
| `GET /api/home/` | Firestore unavailable | **500** | Fails completely (API data lost) |
| `GET /api/map/` | OWM unavailable | **200** | Partial data — failing cities get `"error": "Data unavailable"` |
| `GET /api/map/` | Firestore unavailable | — | **Not affected** |

---

## Key Observations for Frontend

1. **`/api/map/` is the most resilient** — always returns `200`, even when all cities fail. Always check for `"error"` on each city before reading values.

2. **`/api/advice/` gracefully handles Ollama failure** — returns `200` with a fallback `advice` string. The response shape is identical; there is no flag to detect fallback mode.

3. **`/api/forecast/` and `/api/advice/` are Firestore-independent** — they work purely from the OpenWeatherMap API. Firestore outages do not affect them at all.

4. **Inconsistent error format in air pollution endpoints** — `GET /api/air-pollution/`, `GET /api/air-pollution/all/`, and `GET /api/air-pollution/location/` return errors without a `"status"` field (just `"error": "message"`). All other endpoints include `"status": "error"`.

5. **`/api/home/` loses API data when Firestore fails** — the OWM data is fetched successfully but the DB write attempt crashes before the response is sent. The frontend gets a 500 instead of the weather data.

6. **`/api/air-pollution/` and `/api/air-pollution/location/` have the same problem** — if Firestore fails during the cache check, the already-fetched API data is lost and the frontend gets 500.
