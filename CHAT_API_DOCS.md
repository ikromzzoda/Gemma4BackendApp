# Chat API Documentation

> **Base URL:** `/api/chat/`  
> **Format:** JSON  
> **Auth:** Firebase ID token — заголовок `Authorization: Bearer <id_token>` обязателен для всех endpoints  
> **Swagger UI:** `/api/chat/swagger/` · **OpenAPI spec:** `/api/chat/openapi.json`

---

## Содержание

- [Обзор](#обзор)
- [Авторизация](#авторизация)
- [Модели данных](#модели-данных)
- [Формат ошибок](#формат-ошибок)
- [Sessions (Сессии)](#sessions-сессии)
  - [POST /api/chat/sessions/](#post-apichatsessions)
  - [GET /api/chat/users/\<user\_uid\>/sessions/](#get-apichatusersuser_uidsessions)
  - [DELETE /api/chat/sessions/\<chat\_id\>/delete](#delete-apichatsessionschat_iddelete)
  - [PATCH /api/chat/sessions/\<chat\_id\>/title/](#patch-apichatsessionschat_idtitle)
- [Messages (Сообщения)](#messages-сообщения)
  - [GET /api/chat/sessions/\<chat\_id\>/messages/](#get-apichatsessionschat_idmessages)
  - [POST /api/chat/sessions/\<chat\_id\>/send/](#post-apichatsessionschat_idsend)

---

## Обзор

**AI-ассистент — Airi**, работает на базе модели Gemma 4.

Каждое сообщение обрабатывается по следующей схеме:

1. Загружается профиль пользователя из Firestore (имя, город, здоровье, активность)
2. Получаются реальные данные AQI для города пользователя (кэш 1 час → live API)
3. Данные AQI незаметно добавляются в контекст запроса к модели
4. Последние **30 сообщений** переписки передаются в Gemma 4 для поддержания контекста
5. Ответ ассистента сохраняется и возвращается клиенту (при ошибке AI — `502`, ничего не сохраняется)

**Иерархия данных в Firestore:**

```
chat_sessions/
  {chat_id}/
    ├── user_uid
    ├── title
    ├── created_at
    ├── updated_at
    └── messages/          ← subcollection
          {message_id}/
              ├── role       ("user" | "assistant")
              ├── content
              ├── user_uid
              └── created_at
```

**Auto-title:** если при отправке первого сообщения title сессии равен `"New Chat"`, он автоматически заменяется первыми 60 символами сообщения пользователя.

---

## Авторизация

Все endpoints требуют Firebase ID token в заголовке:

```
Authorization: Bearer <firebase_id_token>
```

Токен получается на клиенте после входа через Firebase Auth (например, `FirebaseAuth.instance.currentUser.getIdToken()` во Flutter). Сервер проверяет токен через Firebase Admin SDK и извлекает из него `uid`.

Правила доступа:

- `POST /sessions/` — сессия создаётся для `uid` из токена, поле `user_uid` в теле больше не используется.
- `GET /users/<user_uid>/sessions/` — `user_uid` в пути должен совпадать с `uid` из токена, иначе `403`.
- Все операции с `<chat_id>` доступны только владельцу сессии, иначе `403`.

| Код | Причина |
|---|---|
| `401` | Заголовок отсутствует, токен невалиден или истёк |
| `403` | Токен валиден, но ресурс принадлежит другому пользователю |

---

## Модели данных

### ChatSession

```json
{
  "chat_id":    "xKpL9mNqRt",
  "user_uid":   "firebase-uid",
  "title":      "New Chat",
  "created_at": "2026-06-15 10:00:00.000000+05:00",
  "updated_at": "2026-06-15 10:05:00.000000+05:00"
}
```

| Поле | Тип | Описание |
|---|---|---|
| `chat_id` | string | Firestore document ID, используется как ID сессии |
| `user_uid` | string | Firebase Auth UID владельца |
| `title` | string | Название сессии |
| `created_at` | string (datetime) | Время создания |
| `updated_at` | string \| null | Время последнего обновления |

### Message

```json
{
  "id":         "3f2a1b9c-8d4e-4f5a-9b1c-2d3e4f5a6b7c",
  "chat_id":    "xKpL9mNqRt",
  "role":       "user",
  "content":    "What is the AQI today?",
  "created_at": "2026-06-15 10:05:00.000000+05:00"
}
```

| Поле | Тип | Описание |
|---|---|---|
| `id` | string (UUID v4) | ID сообщения |
| `chat_id` | string | ID сессии-владельца |
| `role` | `"user"` \| `"assistant"` | Автор сообщения |
| `content` | string | Текст сообщения |
| `created_at` | string (datetime) | Время создания |

### AQI Context (debug)

Возвращается в поле `aqi_used` в ответе `/send/`. Показывает данные AQI, которые были переданы в Gemma 4.

```json
{
  "city":      "Dushanbe",
  "aqi":       87,
  "aqi_label": "Moderate",
  "pm25":      24.5,
  "pm10":      38.2,
  "no2":       12.1,
  "o3":        55.0,
  "so2":       4.3,
  "co":        210.0,
  "source":    "cache"
}
```

| Поле | Описание |
|---|---|
| `aqi` | Индекс AQI по шкале US |
| `aqi_label` | Текстовая метка (`Good`, `Moderate`, `Unhealthy for Sensitive Groups`, `Unhealthy`, `Very Unhealthy`, `Hazardous`) |
| `source` | `"cache"` — данные из Firestore (< 1 часа), `"live"` — получены из API |

---

## Формат ошибок

Все ошибки возвращаются в едином формате:

```json
{
  "status": "error",
  "error":  "Human-readable message"
}
```

| Код | Причина |
|---|---|
| `400` | Отсутствует обязательное поле или невалидный JSON |
| `401` | Отсутствует или невалиден Firebase ID token |
| `403` | Ресурс принадлежит другому пользователю |
| `404` | Сессия с указанным `chat_id` не найдена |
| `405` | Неверный HTTP-метод |
| `429` | Исчерпан дневной лимит AI (10 000 выходных токенов на пользователя в день) |
| `500` | Внутренняя ошибка (детали пишутся в лог сервера, клиенту не раскрываются) |
| `502` | Gemma недоступна / таймаут — сообщение не сохранено, запрос можно повторить |

---

## Sessions (Сессии)

---

### POST /api/chat/sessions/

Создаёт новую сессию. Возвращает объект `ChatSession` с присвоенным `chat_id`.

**Request Body**

```json
{
  "title": "Air Quality Questions"
}
```

| Поле | Тип | Обязательность | Описание |
|---|---|---|---|
| `title` | string | Опционально | Название сессии. По умолчанию `"New Chat"` |

> `user_uid` берётся из Firebase-токена; поле в теле запроса игнорируется.

**Responses**

| Код | Описание |
|---|---|
| `201` | Сессия создана |
| `400` | Невалидный JSON |
| `401` | Нет/невалиден токен |
| `405` | Запрос не POST |
| `500` | Ошибка Firestore |

**Response 201**

```json
{
  "status": "success",
  "data": {
    "chat_id":    "xKpL9mNqRt",
    "user_uid":   "abc123uid",
    "title":      "Air Quality Questions",
    "created_at": "2026-06-15 10:00:00.000000+05:00",
    "updated_at": null
  }
}
```

---

### GET /api/chat/users/\<user\_uid\>/sessions/

Возвращает все сессии пользователя, отсортированные по `updated_at` (новые первыми).

**Path Parameters**

| Параметр | Тип | Описание |
|---|---|---|
| `user_uid` | string | Firebase Auth UID |

**Responses**

| Код | Описание |
|---|---|
| `200` | Список сессий (пустой массив если нет) |
| `401` | Нет/невалиден токен |
| `403` | `user_uid` в пути не совпадает с uid из токена |
| `405` | Запрос не GET |
| `500` | Ошибка Firestore |

**Response 200**

```json
{
  "status": "success",
  "data": [
    {
      "chat_id":    "xKpL9mNqRt",
      "user_uid":   "abc123uid",
      "title":      "Какой сегодня AQI?",
      "created_at": "2026-06-15 10:00:00.000000+05:00",
      "updated_at": "2026-06-15 10:05:00.000000+05:00"
    },
    {
      "chat_id":    "yZrM2pQsWu",
      "user_uid":   "abc123uid",
      "title":      "New Chat",
      "created_at": "2026-06-14 08:30:00.000000+05:00",
      "updated_at": null
    }
  ]
}
```

---

### DELETE /api/chat/sessions/\<chat\_id\>/delete

Удаляет сессию и **все её сообщения** через Firestore batch. Операция **необратима**.

**Path Parameters**

| Параметр | Тип | Описание |
|---|---|---|
| `chat_id` | string | ID сессии |

**Responses**

| Код | Описание |
|---|---|
| `200` | Сессия и сообщения удалены |
| `401` | Нет/невалиден токен |
| `403` | Сессия принадлежит другому пользователю |
| `404` | Сессия не найдена |
| `405` | Запрос не DELETE |
| `500` | Ошибка Firestore |

**Response 200**

```json
{
  "status":  "success",
  "message": "Session and 12 message(s) deleted"
}
```

**Response 404**

```json
{
  "status": "error",
  "error":  "Session not found"
}
```

---

### PATCH /api/chat/sessions/\<chat\_id\>/title/

Переименовывает сессию. Обновляет `title` и `updated_at`.

**Path Parameters**

| Параметр | Тип | Описание |
|---|---|---|
| `chat_id` | string | ID сессии |

**Request Body**

```json
{
  "title": "Dushanbe Air Quality"
}
```

| Поле | Тип | Обязательность | Описание |
|---|---|---|---|
| `title` | string | **Обязательно** | Новое название (не пустая строка) |

**Responses**

| Код | Описание |
|---|---|
| `200` | Обновлённый объект сессии |
| `400` | `title` не передан или пустая строка |
| `401` | Нет/невалиден токен |
| `403` | Сессия принадлежит другому пользователю |
| `404` | Сессия не найдена |
| `405` | Запрос не PATCH |
| `500` | Ошибка Firestore |

**Response 200**

```json
{
  "status": "success",
  "data": {
    "chat_id":    "xKpL9mNqRt",
    "user_uid":   "abc123uid",
    "title":      "Dushanbe Air Quality",
    "created_at": "2026-06-15 10:00:00.000000+05:00",
    "updated_at": "2026-06-15 10:10:00.000000+05:00"
  }
}
```

---

## Messages (Сообщения)

---

### GET /api/chat/sessions/\<chat\_id\>/messages/

Возвращает все сообщения сессии, отсортированные **от старых к новым** по `created_at`.

**Path Parameters**

| Параметр | Тип | Описание |
|---|---|---|
| `chat_id` | string | ID сессии |

**Responses**

| Код | Описание |
|---|---|
| `200` | Массив сообщений (пустой если нет) |
| `401` | Нет/невалиден токен |
| `403` | Сессия принадлежит другому пользователю |
| `404` | Сессия не найдена |
| `405` | Запрос не GET |
| `500` | Ошибка Firestore |

**Response 200**

```json
{
  "status":  "success",
  "chat_id": "xKpL9mNqRt",
  "data": [
    {
      "id":         "3f2a1b9c-8d4e-4f5a-9b1c-2d3e4f5a6b7c",
      "chat_id":    "xKpL9mNqRt",
      "role":       "user",
      "content":    "What is the AQI in Dushanbe today?",
      "created_at": "2026-06-15 10:05:00.000000+05:00"
    },
    {
      "id":         "9a8b7c6d-5e4f-3a2b-1c0d-e9f8a7b6c5d4",
      "chat_id":    "xKpL9mNqRt",
      "role":       "assistant",
      "content":    "The AQI in Dushanbe right now is 87 (Moderate). PM2.5 is at 24.5 µg/m³. Consider limiting prolonged outdoor activity.",
      "created_at": "2026-06-15 10:05:03.000000+05:00"
    }
  ]
}
```

---

### POST /api/chat/sessions/\<chat\_id\>/send/

Главный endpoint. Отправляет сообщение пользователя в Gemma 4 и возвращает ответ ассистента.

**Пайплайн обработки:**

```
Auth + validate session ownership
  → Load user profile (Firestore)
    → Fetch AQI for user's city (cache → live API, параллельно)
      → Build personalised system prompt
        → Load last 30 messages of history
          → Call Gemma 4 (history + AQI context)   ← при ошибке 502, ничего не сохраняется
            → Save user message + AI reply
              → Update session updated_at + auto-title
```

**Path Parameters**

| Параметр | Тип | Описание |
|---|---|---|
| `chat_id` | string | ID сессии |

**Request Body**

```json
{
  "message": "Какой сегодня AQI в Душанбе?"
}
```

| Поле | Тип | Обязательность | Описание |
|---|---|---|---|
| `message` | string | **Обязательно** | Текст сообщения пользователя (не пустая строка) |

**Responses**

| Код | Описание |
|---|---|
| `200` | Сообщение сохранено, ответ AI получен |
| `400` | `message` пустой или невалидный JSON |
| `401` | Нет/невалиден токен |
| `403` | Сессия принадлежит другому пользователю |
| `404` | Сессия не найдена |
| `405` | Запрос не POST |
| `429` | Исчерпан дневной лимит AI — 10 000 выходных токенов на пользователя в день |
| `502` | Gemma недоступна/таймаут — ничего не сохранено, запрос можно повторить |

**Response 200**

```json
{
  "status":  "success",
  "chat_id": "xKpL9mNqRt",
  "data": {
    "user_message": {
      "id":         "3f2a1b9c-8d4e-4f5a-9b1c-2d3e4f5a6b7c",
      "chat_id":    "xKpL9mNqRt",
      "role":       "user",
      "content":    "Какой сегодня AQI в Душанбе?",
      "created_at": "2026-06-15 10:05:00.000000+05:00"
    },
    "ai_message": {
      "id":         "9a8b7c6d-5e4f-3a2b-1c0d-e9f8a7b6c5d4",
      "chat_id":    "xKpL9mNqRt",
      "role":       "assistant",
      "content":    "AQI в Душанбе сейчас 87 — умеренный уровень загрязнения. PM2.5 составляет 24.5 µg/m³. Рекомендую ограничить длительные прогулки на улице.",
      "created_at": "2026-06-15 10:05:03.000000+05:00"
    },
    "session_title": "Какой сегодня AQI в Душанбе?",
    "aqi_used": {
      "city":      "Dushanbe",
      "aqi":       87,
      "aqi_label": "Moderate",
      "pm25":      24.5,
      "pm10":      38.2,
      "no2":       12.1,
      "o3":        55.0,
      "so2":       4.3,
      "co":        210.0,
      "source":    "cache"
    }
  }
}
```

**Response 400**

```json
{
  "status": "error",
  "error":  "message is required"
}
```

**Response 429**

```json
{
  "status": "error",
  "error":  "Daily AI usage limit reached. Try again tomorrow.",
  "tokens_used_today": 10240,
  "daily_limit": 10000
}
```

> **Лимиты AI:** один ответ модели ограничен 1000 выходных токенов; суммарно на пользователя — 10 000 выходных токенов в день (счётчик сбрасывается в полночь UTC).

> **Примечание по `aqi_used`:** показывает данные AQI, которые были реально переданы в Gemma 4 для этого запроса. Если данные недоступны (API недоступен, неизвестный город), поле будет `null` — ассистент ответит без актуальных данных. Поле предназначено для отладки.

---

## Полный пример использования

```bash
# Firebase ID token, полученный на клиенте после входа
TOKEN="<firebase_id_token>"

# 1. Создать сессию
curl -X POST http://localhost:8000/api/chat/sessions/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Мои вопросы об AQI"}'

# 2. Отправить сообщение
curl -X POST http://localhost:8000/api/chat/sessions/xKpL9mNqRt/send/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Какой AQI сегодня в Душанбе?"}'

# 3. Получить историю
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/chat/sessions/xKpL9mNqRt/messages/

# 4. Переименовать сессию
curl -X PATCH http://localhost:8000/api/chat/sessions/xKpL9mNqRt/title/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Качество воздуха"}'

# 5. Список всех сессий пользователя
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/chat/users/abc123uid/sessions/

# 6. Удалить сессию
curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/chat/sessions/xKpL9mNqRt/delete
```
