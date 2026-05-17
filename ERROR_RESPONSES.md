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

## 3b. POST /api/users/\<uid\>/fcm-token/

### Scenario 1 — OpenWeatherMap unavailable
**Not applicable.** This endpoint makes no external API calls.

### Scenario 2 — Firestore unavailable

`User.collection.filter("uid", "==", uid).get()` raises → caught by `except Exception as e`.

**HTTP 500**
```json
{
  "status": "error",
  "error": "Internal server error",
  "detail": "<Firestore exception message>"
}
```
Endpoint **fails completely**.

If lookup succeeds but `user.update()` raises → same `except Exception as e` block, same 500 shape.

### Scenario 3 — Gemma4 / FCM unavailable
**Not applicable.** This endpoint does not call any AI or FCM API.

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

---

## 11. POST /api/chat/sessions/create/

### Scenario 1 — OpenWeatherMap unavailable
**Not applicable.** This endpoint makes no external API calls.

### Scenario 2 — Firestore unavailable

`session.save()` raises an exception → caught by `except Exception as e`.

**HTTP 500**
```json
{
  "status": "error",
  "error": "<Firestore exception message>"
}
```
Endpoint **fails completely**. No session is created.

### Scenario 3 — Gemma4 API unavailable
**Not applicable.** This endpoint does not call the AI API.

---

## 12. GET /api/chat/users/\<user_uid\>/sessions/

### Scenario 1 — OpenWeatherMap unavailable
**Not applicable.**

### Scenario 2 — Firestore unavailable

`ChatSession.collection.filter("user_uid", "==", user_uid).fetch()` raises → caught by `except Exception as e`.

**HTTP 500**
```json
{
  "status": "error",
  "error": "<Firestore exception message>"
}
```
Endpoint **fails completely**.

### Scenario 3 — Gemma4 API unavailable
**Not applicable.**

---

## 13. GET /api/chat/sessions/\<session_id\>/messages/

### Scenario 1 — OpenWeatherMap unavailable
**Not applicable.**

### Scenario 2 — Firestore unavailable

`Message.collection.filter("chat_id", "==", session_id).fetch()` raises → caught by `except Exception as e`.

**HTTP 500**
```json
{
  "status": "error",
  "error": "<Firestore exception message>"
}
```
Endpoint **fails completely**.

### Scenario 3 — Gemma4 API unavailable
**Not applicable.**

---

## 14. POST /api/chat/sessions/\<session_id\>/message/

This is the most complex endpoint. Failure can occur at three separate stages.

### Scenario 1 — OpenWeatherMap unavailable
**Not applicable.** This endpoint makes no OWM calls.

### Scenario 2 — Firestore unavailable

**Stage A — session lookup fails:**  
`ChatSession.collection.get(session_id)` raises → caught by bare `except Exception`, `session` is set to `None`.

**HTTP 404**
```json
{
  "status": "error",
  "error": "Session not found"
}
```

**Stage B — message history load fails:**  
`Message.collection.filter("chat_id", "==", session_id).fetch()` raises → caught by `except Exception`, `history` falls back to `[]`. The endpoint **continues** with empty history. The AI reply is still generated and both messages are saved.

**Stage C — saving user or AI message fails:**  
`user_msg.save()` or `ai_msg.save()` raises → **not caught at message level**. The exception propagates to the outer `try` block in `send_message`. Because there is no outer try/except wrapping the save operations, this would cause an **unhandled 500**.

> **Note:** `session.update()` failure at the end is caught by its own `except Exception` and only logs a warning — the `200` response is still returned.

### Scenario 3 — Gemma4 API unavailable

`requests.post(...)` raises any exception → caught by `except Exception as e` inside `_call_gemma()`.

A **retry** is attempted without the `systemInstruction` field. If the retry also fails → caught by the inner `except Exception as e2`.

**The endpoint returns HTTP 200** with a fallback reply:

```json
{
  "status": "success",
  "data": {
    "user_message": { "...user message object..." },
    "ai_message": {
      "id": "chat_messages/...",
      "chat_id": "chat_sessions/...",
      "role": "assistant",
      "content": "Sorry, I couldn't process your request right now. Please try again.",
      "created_at": "2026-05-16 09:01:03+05:00"
    },
    "session_title": "..."
  }
}
```

**On read timeout specifically** (>60 s, `requests.exceptions.ReadTimeout`):

```json
{
  "ai_message": {
    "content": "Sorry, I'm taking too long to respond. Please try again."
  }
}
```

The user message **is always saved** to Firestore before the AI call. The fallback response **is also saved** as an `"assistant"` message. The frontend **cannot distinguish** fallback from real AI output — there is no `"is_fallback"` flag.

---

## 15. DELETE /api/chat/sessions/\<session_id\>/delete/

### Scenario 1 — OpenWeatherMap unavailable
**Not applicable.**

### Scenario 2 — Firestore unavailable

**Stage A — session lookup fails:**  
`ChatSession.collection.get(session_id)` raises → caught by bare `except Exception`, `session` set to `None`.

**HTTP 404**
```json
{
  "status": "error",
  "error": "Session not found"
}
```

**Stage B — delete loop fails:**  
`Message.collection.filter(...).fetch()` or any `msg.delete()` or `session.delete()` raises → caught by `except Exception as e`.

**HTTP 500**
```json
{
  "status": "error",
  "error": "<Firestore exception message>"
}
```
The session and/or some messages may have been partially deleted before the error.

### Scenario 3 — Gemma4 API unavailable
**Not applicable.**

---

## 16. PATCH /api/chat/sessions/\<session_id\>/title/

### Scenario 1 — OpenWeatherMap unavailable
**Not applicable.**

### Scenario 2 — Firestore unavailable

**Stage A — session lookup fails:**  
Same pattern as other endpoints — `session` set to `None` → **HTTP 404**.

**Stage B — update fails:**  
`session.update()` raises → caught by `except Exception as e`.

**HTTP 500**
```json
{
  "status": "error",
  "error": "<Firestore exception message>"
}
```
Endpoint **fails completely**.

### Scenario 3 — Gemma4 API unavailable
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
| `POST /api/users/<uid>/fcm-token/` | OWM unavailable | — | Not affected |
| `POST /api/users/<uid>/fcm-token/` | Firestore unavailable | **500** | Fails completely |
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
| `POST /api/chat/sessions/create/` | OWM unavailable | — | Not affected |
| `POST /api/chat/sessions/create/` | Firestore unavailable | **500** | Fails completely |
| `GET /api/chat/users/<uid>/sessions/` | OWM unavailable | — | Not affected |
| `GET /api/chat/users/<uid>/sessions/` | Firestore unavailable | **500** | Fails completely |
| `GET /api/chat/sessions/<id>/messages/` | OWM unavailable | — | Not affected |
| `GET /api/chat/sessions/<id>/messages/` | Firestore unavailable | **500** | Fails completely |
| `POST /api/chat/sessions/<id>/message/` | OWM unavailable | — | Not affected |
| `POST /api/chat/sessions/<id>/message/` | Firestore unavailable (lookup) | **404** | Session appears not found |
| `POST /api/chat/sessions/<id>/message/` | Firestore unavailable (history) | **200** | Continues with empty history |
| `POST /api/chat/sessions/<id>/message/` | Gemma4 API unavailable | **200** | Returns fallback reply string |
| `DELETE /api/chat/sessions/<id>/delete/` | OWM unavailable | — | Not affected |
| `DELETE /api/chat/sessions/<id>/delete/` | Firestore unavailable (lookup) | **404** | Session appears not found |
| `DELETE /api/chat/sessions/<id>/delete/` | Firestore unavailable (delete) | **500** | Partial delete possible |
| `PATCH /api/chat/sessions/<id>/title/` | OWM unavailable | — | Not affected |
| `PATCH /api/chat/sessions/<id>/title/` | Firestore unavailable | **500** | Fails completely |

---

## Key Observations for Frontend

1. **`/api/map/` is the most resilient** — always returns `200`, even when all cities fail. Always check for `"error"` on each city before reading values.

2. **`/api/advice/` gracefully handles Ollama failure** — returns `200` with a fallback `advice` string. The response shape is identical; there is no flag to detect fallback mode.

3. **`/api/forecast/` and `/api/advice/` are Firestore-independent** — they work purely from the OpenWeatherMap API. Firestore outages do not affect them at all.

4. **Inconsistent error format in air pollution endpoints** — `GET /api/air-pollution/`, `GET /api/air-pollution/all/`, and `GET /api/air-pollution/location/` return errors without a `"status"` field (just `"error": "message"`). All other endpoints include `"status": "error"`.

5. **`/api/home/` loses API data when Firestore fails** — the OWM data is fetched successfully but the DB write attempt crashes before the response is sent. The frontend gets a 500 instead of the weather data.

6. **`/api/air-pollution/` and `/api/air-pollution/location/` have the same problem** — if Firestore fails during the cache check, the already-fetched API data is lost and the frontend gets 500.

7. **`POST /api/chat/sessions/<id>/message/` gracefully handles Gemma4 failure** — the endpoint always returns `200`. On any AI API error (including timeout), a human-readable fallback string is saved as the assistant message. There is no `"is_fallback"` flag.

8. **History-load failure in `/api/chat/sessions/<id>/message/` is silent** — if Firestore fails when loading conversation history, the endpoint continues with an empty history. The AI reply will lack context but the user won't see an error.

9. **`DELETE /api/chat/sessions/<id>/delete/` can leave orphan messages** — if Firestore fails mid-loop, some messages may be deleted while others remain. There is no transaction or rollback.

10. **All chat endpoints use `"status": "error"` in error responses** — consistent with the users, forecast, advice, home, and map endpoints, unlike the air-pollution group.

11. **`POST /api/users/<uid>/fcm-token/` is Firestore-only** — no OWM or AI calls. The only failure mode is a Firestore error (500). An invalid/missing `fcmToken` body field returns 400 before any DB call.

12. **`send_weather_advice_notifications` (background task) never crashes the whole batch** — per-user FCM failures are caught individually and logged. OpenWeatherMap failures for a specific user increment the `failed` counter and skip to the next user. The task logs a `notified=N, failed=N` summary on completion.
