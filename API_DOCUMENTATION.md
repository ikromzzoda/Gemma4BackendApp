# API Documentation

**Base URL:** `/api/`  
**Stack:** Django · Firebase Firestore · OpenWeatherMap · Ollama (local LLM) · Gemma4 API (Google Generative Language)  
**Format:** All requests and responses use `application/json`

---

## AQI Reference Table

| AQI | Label |
|-----|-------|
| 1 | Good |
| 2 | Fair |
| 3 | Moderate |
| 4 | Unhealthy for Sensitive Groups |
| 5 | Very Unhealthy |

---

## Valid Enumerated Values

| Field | Valid values |
|-------|-------------|
| `city` | `"Dushanbe"`, `"Khujand"`, `"Bokhtar"`, `"Kulob"`, `"Istaravshan"`, `"Panjakent"`, `"Khorugh"`, `"Tursunzoda"`, `"Hisor"` |
| `ageGroup` | `"Under 18"`, `"18 - 24"`, `"25 - 34"`, `"35 - 44"`, `"45 - 54"`, `"55 - 64"`, `"65+"` |
| `healthCondition` | `"Asthma"`, `"Allergies"`, `"Bronchitis"`, `"COPD"`, `"Heart Condition"`, `"None"`, `"Others"` |
| `activityLevel` | `"Sedentary"`, `"Lightly Active"`, `"Active"`, `"Very Active"` |
| `pollutant` | `"AQI"`, `"PM2.5"`, `"PM10"`, `"O3"`, `"NO2"` |
| `period` | `"today"`, `"tomorrow"`, `"7days"` |

---

## Endpoints

---

### 1. POST /api/users/create/

Creates a new user profile in Firestore.

**CSRF:** Exempt

#### Request Body

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `uid` | string | **Yes** | — | Firebase Auth UID |
| `firstName` | string | **Yes** | — | |
| `surname` | string | **Yes** | — | |
| `email` | string | **Yes** | — | |
| `location` | string | No | `"Dushanbe"` | Must be a valid city |
| `ageGroup` | string | No | `"18 - 24"` | See valid values |
| `healthCondition` | string | No | `"None"` | See valid values |
| `activityLevel` | string | No | `"Active"` | See valid values |
| `notificationsEnabled` | boolean | No | `true` | |
| `dailyForecastEnabled` | boolean | No | `true` | |
| `healthTipsEnabled` | boolean | No | `false` | |
| `profilePicUrl` | string | No | `""` | Any URL string |

**Example request:**
```json
{
  "uid": "firebase_uid_abc123",
  "firstName": "Ali",
  "surname": "Nazarov",
  "email": "ali@example.com",
  "location": "Dushanbe",
  "ageGroup": "25 - 34",
  "healthCondition": "Asthma",
  "activityLevel": "Active"
}
```

#### Success Response — `201 Created`

```json
{
  "status": "success",
  "data": {
    "uid": "firebase_uid_abc123",
    "firstName": "Ali",
    "surname": "Nazarov",
    "email": "ali@example.com",
    "location": "Dushanbe",
    "ageGroup": "25 - 34",
    "healthCondition": "Asthma",
    "activityLevel": "Active",
    "notificationsEnabled": true,
    "dailyForecastEnabled": true,
    "healthTipsEnabled": false,
    "profilePicUrl": ""
  }
}
```

---

### 2. PUT /api/users/\<uid\>/update/

Updates one or more fields of an existing user profile.

**CSRF:** Exempt

#### URL Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `uid` | string | **Yes** | Firebase Auth UID |

#### Request Body

Send only the fields you want to change. All fields are optional.

| Field | Type | Valid values |
|-------|------|-------------|
| `location` | string | City list |
| `ageGroup` | string | Age group list |
| `healthCondition` | string | Health condition list |
| `activityLevel` | string | Activity level list |
| `notificationsEnabled` | boolean | `true` / `false` |
| `dailyForecastEnabled` | boolean | `true` / `false` |
| `healthTipsEnabled` | boolean | `true` / `false` |
| `profilePicUrl` | string | Any URL string |

**Example request:**
```json
{
  "location": "Khujand",
  "healthTipsEnabled": true,
  "activityLevel": "Lightly Active"
}
```

#### Success Response — `200 OK`

Returns the complete updated user object (same shape as create):

```json
{
  "status": "success",
  "data": {
    "uid": "firebase_uid_abc123",
    "firstName": "Ali",
    "surname": "Nazarov",
    "email": "ali@example.com",
    "location": "Khujand",
    "ageGroup": "25 - 34",
    "healthCondition": "Asthma",
    "activityLevel": "Lightly Active",
    "notificationsEnabled": true,
    "dailyForecastEnabled": true,
    "healthTipsEnabled": true,
    "profilePicUrl": ""
  }
}
```

---

### 3. GET /api/users/\<uid\>/

Returns a user profile by UID.

#### URL Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `uid` | string | **Yes** | Firebase Auth UID |

#### Success Response — `200 OK`

```json
{
  "status": "success",
  "data": {
    "uid": "firebase_uid_abc123",
    "firstName": "Ali",
    "surname": "Nazarov",
    "email": "ali@example.com",
    "location": "Dushanbe",
    "ageGroup": "25 - 34",
    "healthCondition": "Asthma",
    "activityLevel": "Active",
    "notificationsEnabled": true,
    "dailyForecastEnabled": true,
    "healthTipsEnabled": false,
    "profilePicUrl": ""
  }
}
```

---

### 4. GET /api/air-pollution/

Fetches current air pollution data from OpenWeatherMap for a Tajik city.  
Saves a new Firestore record only if no record exists for that city in the last **12 hours**.

#### Query Parameters

| Parameter | Type | Required | Default | Valid values |
|-----------|------|----------|---------|-------------|
| `city` | string | No | `"Dushanbe"` | City list |

#### Success Response

**`201 Created`** — when a new record was saved to Firestore:

```json
{
  "message": "Saved to DB",
  "saved_to_db": true,
  "city": "Dushanbe",
  "data": {
    "lat": 38.5598,
    "lon": 68.7738,
    "pm25": 12.5,
    "pm10": 18.3,
    "no2": 4.21,
    "no": 0.05,
    "o3": 68.12,
    "so2": 1.14,
    "co": 201.67,
    "nh3": 0.53,
    "aqi": 1,
    "dt": "2026-05-08 06:00:00+05:00"
  }
}
```

**`200 OK`** — when cache is still fresh (record exists within last 12 hours):

```json
{
  "message": "Not saved (less than 12 hours)",
  "saved_to_db": false,
  "city": "Dushanbe",
  "data": {
    "lat": 38.5598,
    "lon": 68.7738,
    "pm25": 12.5,
    "pm10": 18.3,
    "no2": 4.21,
    "no": 0.05,
    "o3": 68.12,
    "so2": 1.14,
    "co": 201.67,
    "nh3": 0.53,
    "aqi": 1,
    "dt": "2026-05-08 06:00:00+05:00"
  }
}
```

> **Note:** This endpoint does not include a `"status"` field in its response — unlike other endpoints.

---

### 5. GET /api/air-pollution/all/

Returns all air pollution records stored in Firestore across all cities.

#### Query Parameters

None.

#### Success Response — `200 OK`

```json
{
  "count": 42,
  "data": [
    {
      "id": "firestore_doc_id_abc",
      "lat": 38.5598,
      "lon": 68.7738,
      "pm25": 12.5,
      "pm10": 18.3,
      "no2": 4.21,
      "no": 0.05,
      "o3": 68.12,
      "so2": 1.14,
      "co": 201.67,
      "nh3": 0.53,
      "aqi": 1,
      "dt": "2026-05-08 06:00:00+05:00",
      "created_at": "2026-05-08 07:12:34+05:00"
    }
  ]
}
```

> **Note:** This endpoint does not include a `"status"` field in its response.

---

### 6. GET /api/air-pollution/location/

Fetches fresh air pollution data for any coordinates (not limited to Tajik cities).  
Also returns all previously cached Firestore records for those exact coordinates.

#### Query Parameters

| Parameter | Type | Required | Valid range | Notes |
|-----------|------|----------|-------------|-------|
| `lat` | float | **Yes** | `-90` to `90` | Latitude |
| `lon` | float | **Yes** | `-180` to `180` | Longitude |

#### Success Response — `200 OK`

```json
{
  "location": {
    "lat": 41.2995,
    "lon": 69.2401
  },
  "fresh_data_from_api": {
    "lat": 41.2995,
    "lon": 69.2401,
    "pm25": 14.2,
    "pm10": 21.5,
    "no2": 6.32,
    "no": 0.08,
    "o3": 55.41,
    "so2": 2.01,
    "co": 245.33,
    "nh3": 0.71,
    "aqi": 2,
    "dt": "2026-05-08 08:00:00+05:00"
  },
  "last_cached_record": {
    "id": "firestore_doc_id_xyz",
    "lat": 41.2995,
    "lon": 69.2401,
    "pm25": 13.1,
    "pm10": 19.8,
    "no2": 5.11,
    "no": 0.06,
    "o3": 60.21,
    "so2": 1.87,
    "co": 230.45,
    "nh3": 0.62,
    "aqi": 2,
    "dt": "2026-05-08 06:00:00+05:00",
    "created_at": "2026-05-08 06:15:00+05:00"
  },
  "all_records_history": [
    { "...same shape as last_cached_record..." }
  ],
  "total_records": 5
}
```

`last_cached_record` is `null` if no record was saved for those coordinates within the last 12 hours.  
`all_records_history` is sorted newest-first.

> **Note:** This endpoint does not include a `"status"` field in its response.

---

### 7. GET /api/forecast/

Returns air pollution forecast data for a Tajik city, grouped by time period.  
Data source: OpenWeatherMap 5-day/hourly forecast API.

#### Query Parameters

| Parameter | Type | Required | Default | Valid values |
|-----------|------|----------|---------|-------------|
| `city` | string | No | `"Dushanbe"` | City list |
| `period` | string | No | `"today"` | `"today"`, `"tomorrow"`, `"7days"` |

#### Success Response — `200 OK`

**For `period=today` or `period=tomorrow`** — hourly forecast points:

```json
{
  "status": "success",
  "data": {
    "city": "Dushanbe",
    "period": "today",
    "max_aqi": 2,
    "max_aqi_label": "Fair",
    "max_pm25": 18.7,
    "forecast_points": [
      {
        "time": "2026-05-08 06:00",
        "aqi": 1,
        "aqi_label": "Good",
        "pm25": 12.5,
        "pm10": 18.3
      },
      {
        "time": "2026-05-08 09:00",
        "aqi": 2,
        "aqi_label": "Fair",
        "pm25": 18.7,
        "pm10": 24.1
      }
    ]
  }
}
```

**For `period=7days`** — daily aggregated forecast (max AQI, average PM2.5/PM10 per day):

```json
{
  "status": "success",
  "data": {
    "city": "Dushanbe",
    "period": "7days",
    "max_aqi": 3,
    "max_aqi_label": "Moderate",
    "max_pm25": 22.4,
    "forecast_points": [
      {
        "date": "2026-05-08",
        "aqi": 2,
        "aqi_label": "Fair",
        "pm25": 15.3,
        "pm10": 20.1
      },
      {
        "date": "2026-05-09",
        "aqi": 3,
        "aqi_label": "Moderate",
        "pm25": 22.4,
        "pm10": 30.7
      }
    ]
  }
}
```

**Field notes:**
- `max_aqi` / `max_aqi_label` — worst AQI across all forecast points in the requested period
- `max_pm25` — highest PM2.5 value across all points
- `time` format: `"YYYY-MM-DD HH:MM"` (UTC)
- `date` format: `"YYYY-MM-DD"`
- For `7days`: `pm25` and `pm10` are averages across all hourly points that day; `aqi` is the daily maximum

---

### 8. GET /api/advice/

Returns current AQI and AI-generated personalized health advice via Ollama (Gemma4 model).  
If Ollama is unavailable the endpoint still returns `200` with a fallback advice string.

#### Query Parameters

| Parameter | Type | Required | Default | Valid values |
|-----------|------|----------|---------|-------------|
| `city` | string | No | `"Dushanbe"` | City list |
| `health_condition` | string | No | `"None"` | Health condition list |
| `activity_level` | string | No | `"Active"` | Activity level list |

#### Success Response — `200 OK`

```json
{
  "status": "success",
  "data": {
    "city": "Dushanbe",
    "aqi": 2,
    "aqi_label": "Fair",
    "health_condition": "Asthma",
    "activity_level": "Active",
    "advice": "With Fair air quality and asthma, limit prolonged outdoor exertion. Carry your rescue inhaler if going outside for more than 30 minutes. Morning hours typically have better air quality."
  }
}
```

**Fallback `advice` when Ollama is down** (status still `200`):
```
"AQI is 2 (Fair). Please check local air quality guidelines for your health condition and activity level."
```

---

### 9. GET /api/home/

Returns combined weather and air quality data for a city in a single call.  
Automatically saves data to Firestore if cache is stale:
- Pollution data: saves if no record in the last **12 hours**
- Weather data: saves if no record in the last **1 hour**

#### Query Parameters

| Parameter | Type | Required | Default | Valid values |
|-----------|------|----------|---------|-------------|
| `city` | string | No | `"Dushanbe"` | City list |

#### Success Response — `200 OK`

```json
{
  "status": "success",
  "data": {
    "city": "Dushanbe",
    "lat": 38.5598,
    "lon": 68.7738,
    "aqi": 2,
    "aqi_label": "Fair",
    "pm25": 14.2,
    "pm10": 21.5,
    "no2": 6.32,
    "o3": 55.41,
    "co": 245.33,
    "temperature": 24.5,
    "feels_like": 23.1,
    "humidity": 38,
    "wind_speed": 3.2,
    "weather_description": "clear sky",
    "weather_icon": "01d",
    "saved_pollution_to_db": false,
    "saved_weather_to_db": true
  }
}
```

**Field notes:**
- `temperature` / `feels_like` — in °C
- `humidity` — in % (integer)
- `wind_speed` — in m/s
- `weather_icon` — OpenWeatherMap icon code (e.g. `"01d"`, `"10n"`)
- `saved_pollution_to_db` / `saved_weather_to_db` — whether a new record was written this request

---

### 10. GET /api/map/

Returns current air quality and temperature data for all 9 Tajik cities simultaneously.  
Individual city failures are isolated — a single city's API error does not abort the whole response.

#### Query Parameters

| Parameter | Type | Required | Default | Valid values |
|-----------|------|----------|---------|-------------|
| `pollutant` | string | No | `"AQI"` | `"AQI"`, `"PM2.5"`, `"PM10"`, `"O3"`, `"NO2"` |

> The `pollutant` parameter indicates what the frontend wants to display on the map. The backend always returns all pollutant fields regardless of the selected value.

#### Success Response — `200 OK`

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
        "city": "Khujand",
        "lat": 40.2827,
        "lon": 69.6223,
        "aqi": 1,
        "aqi_label": "Good",
        "pm25": 8.1,
        "pm10": 12.3,
        "o3": 61.2,
        "no2": 3.11,
        "temperature": 22.1
      }
    ]
  }
}
```

**When a city's API call fails**, that city's object contains only:

```json
{
  "city": "Khorugh",
  "lat": 37.4897,
  "lon": 71.5528,
  "error": "Data unavailable"
}
```

The response is always `200 OK` even if all cities fail individually.

---

---

## Chat Endpoints

The chat module provides a multi-turn AI conversation feature powered by the **Gemma4 API** (Google Generative Language). The AI persona is named **Airi** — a helpful assistant specialised in air quality, health impacts of pollution, weather patterns, and personalised health recommendations.

**Firestore collections used:**
- `chat_sessions` — session metadata (title, owner, timestamps)
- `chat_messages` — individual messages with roles `"user"` / `"assistant"`

---

### 11. POST /api/chat/sessions/create/

Creates a new chat session for a user.

**CSRF:** Exempt (class-based view routing, no decorator needed)

#### Request Body

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `user_uid` | string | **Yes** | — | Firebase Auth UID of the session owner |
| `title` | string | No | `"New Chat"` | Session display name. Auto-generated from the first message if this default is kept. |

**Example request:**
```json
{
  "user_uid": "firebase_uid_abc123",
  "title": "My air quality questions"
}
```

#### Success Response — `201 Created`

```json
{
  "status": "success",
  "data": {
    "id": "chat_sessions/AbCdEfGhIj",
    "user_uid": "firebase_uid_abc123",
    "title": "My air quality questions",
    "created_at": "2026-05-16 09:00:00+05:00",
    "updated_at": null
  }
}
```

> `id` is the Firestore document path returned by Fireo (e.g. `"chat_sessions/AbCdEfGhIj"`).

---

### 12. GET /api/chat/users/\<user_uid\>/sessions/

Returns all chat sessions owned by a user, sorted newest-first by `created_at`.

#### URL Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_uid` | string | **Yes** | Firebase Auth UID |

#### Success Response — `200 OK`

```json
{
  "status": "success",
  "data": [
    {
      "id": "chat_sessions/AbCdEfGhIj",
      "user_uid": "firebase_uid_abc123",
      "title": "Why is AQI high today?",
      "created_at": "2026-05-16 09:00:00+05:00",
      "updated_at": "2026-05-16 09:05:00+05:00"
    },
    {
      "id": "chat_sessions/XyZwVuTsRq",
      "user_uid": "firebase_uid_abc123",
      "title": "New Chat",
      "created_at": "2026-05-15 14:30:00+05:00",
      "updated_at": null
    }
  ]
}
```

Returns an empty array `[]` inside `"data"` if the user has no sessions.

---

### 13. GET /api/chat/sessions/\<session_id\>/messages/

Returns all messages in a session, sorted oldest-first by `created_at`.

#### URL Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | **Yes** | Firestore document ID of the session |

#### Success Response — `200 OK`

```json
{
  "status": "success",
  "data": [
    {
      "id": "chat_messages/Msg001",
      "chat_id": "chat_sessions/AbCdEfGhIj",
      "role": "user",
      "content": "What does AQI 3 mean for someone with asthma?",
      "created_at": "2026-05-16 09:01:00+05:00"
    },
    {
      "id": "chat_messages/Msg002",
      "chat_id": "chat_sessions/AbCdEfGhIj",
      "role": "assistant",
      "content": "AQI 3 is Moderate. For asthma sufferers, prolonged outdoor exertion is not advised...",
      "created_at": "2026-05-16 09:01:03+05:00"
    }
  ]
}
```

**`role` values:** `"user"` | `"assistant"`

---

### 14. POST /api/chat/sessions/\<session_id\>/message/

Sends a user message, fetches an AI reply from Gemma4, saves both to Firestore, and returns both in the same response.

**AI behaviour:**
- Full conversation history is loaded and sent to Gemma4 as multi-turn context.
- System prompt instructs the model to act as **Airi** (air quality assistant).
- If `systemInstruction` is rejected by the model, the request is automatically retried without it.
- On timeout (>60 s) or any other error, a safe fallback reply is returned — the endpoint always returns `200`.
- If the session title is still `"New Chat"` and this is the first message, the title is auto-set to the first 60 characters of the user's message.

#### URL Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | **Yes** | Firestore document ID of the session |

#### Request Body

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `message` | string | **Yes** | The user's message text (whitespace-only counts as empty) |

**Example request:**
```json
{
  "message": "What does AQI 3 mean for someone with asthma?"
}
```

#### Success Response — `200 OK`

```json
{
  "status": "success",
  "data": {
    "user_message": {
      "id": "chat_messages/Msg001",
      "chat_id": "chat_sessions/AbCdEfGhIj",
      "role": "user",
      "content": "What does AQI 3 mean for someone with asthma?",
      "created_at": "2026-05-16 09:01:00+05:00"
    },
    "ai_message": {
      "id": "chat_messages/Msg002",
      "chat_id": "chat_sessions/AbCdEfGhIj",
      "role": "assistant",
      "content": "AQI 3 is Moderate. For asthma sufferers, prolonged outdoor exertion is not advised...",
      "created_at": "2026-05-16 09:01:03+05:00"
    },
    "session_title": "What does AQI 3 mean for s..."
  }
}
```

**`session_title`** reflects the (possibly just-updated) title after this call.

**Fallback `ai_message.content` when Gemma4 is unreachable:**
```
"Sorry, I couldn't process your request right now. Please try again."
```

**Fallback on read timeout (>60 s):**
```
"Sorry, I'm taking too long to respond. Please try again."
```

Both fallbacks still return `HTTP 200` and the same JSON shape. There is no `"is_fallback"` flag.

---

### 15. DELETE /api/chat/sessions/\<session_id\>/delete/

Deletes a chat session and **all messages** that belong to it.

#### URL Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | **Yes** | Firestore document ID of the session |

#### Success Response — `200 OK`

```json
{
  "status": "success",
  "message": "Session deleted"
}
```

> This is a hard delete — messages are deleted individually before the session document is removed. There is no recovery.

---

### 16. PATCH /api/chat/sessions/\<session_id\>/title/

Renames a chat session.

#### URL Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | **Yes** | Firestore document ID of the session |

#### Request Body

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `title` | string | **Yes** | New title. Whitespace-only counts as empty and is rejected. |

**Example request:**
```json
{
  "title": "PM2.5 health questions"
}
```

#### Success Response — `200 OK`

Returns the updated session object:

```json
{
  "status": "success",
  "data": {
    "id": "chat_sessions/AbCdEfGhIj",
    "user_uid": "firebase_uid_abc123",
    "title": "PM2.5 health questions",
    "created_at": "2026-05-16 09:00:00+05:00",
    "updated_at": "2026-05-16 09:10:00+05:00"
  }
}
```

---

## Common Error Responses

| HTTP Status | When | Response shape |
|-------------|------|----------------|
| `400 Bad Request` | Invalid query param, missing required field, invalid JSON body | `{"status": "error", "error": "...", "valid_values": [...]}` |
| `404 Not Found` | User UID not found in Firestore | `{"status": "error", "error": "User not found"}` |
| `405 Method Not Allowed` | Wrong HTTP method | `{"status": "error", "error": "Method not allowed"}` |
| `500 Internal Server Error` | Unhandled exception (DB error, parsing error) | `{"status": "error", "error": "Internal server error", "detail": "..."}` |
| `503 Service Unavailable` | OpenWeatherMap API unreachable | `{"status": "error", "error": "OpenWeatherMap API unavailable"}` |

**Validation error example** (invalid enum value):
```json
{
  "status": "error",
  "error": "Invalid city",
  "valid_cities": ["Dushanbe", "Khujand", "Bokhtar", "Kulob", "Istaravshan", "Panjakent", "Khorugh", "Tursunzoda", "Hisor"]
}
```
