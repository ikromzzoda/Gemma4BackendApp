# Chat API — Airi

**Base URL:** `/api`  
**Format:** `Content-Type: application/json`

---

## 1. Создать сессию

**POST** `/api/chat/sessions/create/`

**Запрос:**
```json
{
  "user_uid": "device-uuid-здесь",
  "title": "New Chat"
}
```

**Ответ `201`:**
```json
{
  "status": "success",
  "data": {
    "id": "chat_sessions/AbCdEfGhIj",
    "user_uid": "device-uuid-здесь",
    "title": "New Chat",
    "created_at": "2026-05-17 09:00:00+05:00",
    "updated_at": null
  }
}
```

> Сохрани `id` — он нужен для всех остальных запросов.

---

## 2. Получить список сессий пользователя

**GET** `/api/chat/users/<user_uid>/sessions/`

**Запрос:** без тела

**Ответ `200`:**
```json
{
  "status": "success",
  "data": [
    {
      "id": "chat_sessions/AbCdEfGhIj",
      "user_uid": "device-uuid-здесь",
      "title": "What is AQI?",
      "created_at": "2026-05-17 09:00:00+05:00",
      "updated_at": "2026-05-17 09:05:00+05:00"
    }
  ]
}
```

> Отсортировано от новых к старым. Если сессий нет — `"data": []`.

---

## 3. Получить сообщения сессии

**GET** `/api/chat/sessions/<session_id>/messages/`

**Запрос:** без тела

**Ответ `200`:**
```json
{
  "status": "success",
  "data": [
    {
      "id": "chat_messages/Msg001",
      "chat_id": "chat_sessions/AbCdEfGhIj",
      "role": "user",
      "content": "What is AQI 3?",
      "created_at": "2026-05-17 09:01:00+05:00"
    },
    {
      "id": "chat_messages/Msg002",
      "chat_id": "chat_sessions/AbCdEfGhIj",
      "role": "assistant",
      "content": "AQI 3 is Moderate. Sensitive groups should limit outdoor time.",
      "created_at": "2026-05-17 09:01:03+05:00"
    }
  ]
}
```

> Отсортировано от старых к новым. `role` — либо `"user"` либо `"assistant"`.

---

## 4. Отправить сообщение

**POST** `/api/chat/sessions/<session_id>/message/`

**Запрос:**
```json
{
  "message": "What is AQI 3?"
}
```

**Ответ `200`:**
```json
{
  "status": "success",
  "data": {
    "user_message": {
      "id": "chat_messages/Msg001",
      "chat_id": "chat_sessions/AbCdEfGhIj",
      "role": "user",
      "content": "What is AQI 3?",
      "created_at": "2026-05-17 09:01:00+05:00"
    },
    "ai_message": {
      "id": "chat_messages/Msg002",
      "chat_id": "chat_sessions/AbCdEfGhIj",
      "role": "assistant",
      "content": "AQI 3 is Moderate. Sensitive groups should limit outdoor time.",
      "created_at": "2026-05-17 09:01:03+05:00"
    },
    "session_title": "What is AQI 3?"
  }
}
```

> Если Gemma API недоступен — бэкенд всё равно возвращает `200` с fallback текстом в `ai_message.content`.  
> Если это первое сообщение — `session_title` автоматически устанавливается из текста сообщения (до 60 символов).

---

## 5. Переименовать сессию

**PATCH** `/api/chat/sessions/<session_id>/title/`

**Запрос:**
```json
{
  "title": "AQI questions"
}
```

**Ответ `200`:**
```json
{
  "status": "success",
  "data": {
    "id": "chat_sessions/AbCdEfGhIj",
    "user_uid": "device-uuid-здесь",
    "title": "AQI questions",
    "created_at": "2026-05-17 09:00:00+05:00",
    "updated_at": "2026-05-17 09:10:00+05:00"
  }
}
```

---

## 6. Удалить сессию

**DELETE** `/api/chat/sessions/<session_id>/delete/`

**Запрос:** без тела

**Ответ `200`:**
```json
{
  "status": "success",
  "message": "Session deleted"
}
```

> Удаляет сессию и все её сообщения безвозвратно.

---

## Ошибки

| Статус | Причина | Ответ |
|--------|---------|-------|
| `400` | Пустое сообщение или отсутствует поле | `{"status": "error", "error": "message is required"}` |
| `404` | Сессия не найдена | `{"status": "error", "error": "Session not found"}` |
| `405` | Неверный HTTP метод | `{"status": "error", "error": "Method not allowed"}` |
| `500` | Внутренняя ошибка сервера | `{"status": "error", "error": "Internal server error"}` |
