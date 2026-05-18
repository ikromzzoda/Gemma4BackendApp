# Chat API - Airi

Полная документация REST API для работы с чатом и диалогами с AI-ассистентом.

---

## Общая информация

- **Базовый URL:** `/api`
- **Content-Type:** `application/json`
- **Аутентификация:** user_uid в запросе
- **Формат даты/времени:** ISO 8601 с часовым поясом

---

## Структура ответов

### Успешный ответ
```json
{
  "status": "success",
  "data": { /* данные */ }
}
```

### Ошибка
```json
{
  "status": "error",
  "error": "Описание ошибки"
}
```

---

## API Endpoints

### 1. Создать новую сессию чата

Инициирует новую сессию для пользователя.

**Метод:** `POST`  
**Путь:** `/api/chat/sessions/`

**Параметры запроса:**
```json
{
  "user_uid": "string",  // UUID устройства пользователя (требуется)
  "title": "string"      // Название сессии (опционально, по умолчанию "New Chat")
}
```

**Успешный ответ (201 Created):**
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

**Примечания:**
- Сохрани `id` сессии — он нужен для всех остальных операций
- Каждая сессия изолирована и привязана к `user_uid`

---

### 2. Получить все сессии пользователя

Список всех чат-сессий для конкретного пользователя.

**Метод:** `GET`  
**Путь:** `/chat/users/<str:user_uid>/sessions/`

**Параметры запроса:** нет

**Успешный ответ (200 OK):**
```json
{
  "status": "success",
  "data": [
    {
      "id": "chat_sessions/AbCdEfGhIj",
      "user_uid": "device-uuid-здесь",
      "title": "Вопросы об AQI",
      "created_at": "2026-05-17 09:00:00+05:00",
      "updated_at": "2026-05-17 09:05:00+05:00"
    },
    {
      "id": "chat_sessions/XyZ123KlM",
      "user_uid": "device-uuid-здесь",
      "title": "Погода завтра",
      "created_at": "2026-05-16 14:30:00+05:00",
      "updated_at": "2026-05-16 14:35:00+05:00"
    }
  ]
}
```

**Примечания:**
- Сессии отсортированы по времени обновления (новые сверху)
- Если сессий нет, возвращается пустой массив: `"data": []`
- Максимальный размер без пагинации: 100 сессий

---

### 3. Получить историю сообщений сессии

Полная история всех сообщений в конкретной сессии.

**Метод:** `GET`  
**Путь:** `/api/chat/sessions/<str:chat_id>/messages/`

**Параметры запроса:** нет

**Успешный ответ (200 OK):**
```json
{
  "status": "success",
  "data": [
    {
      "id": "chat_messages/Msg001",
      "chat_id": "chat_sessions/AbCdEfGhIj",
      "role": "user",
      "content": "Что такое AQI 3?",
      "created_at": "2026-05-17 09:01:00+05:00"
    },
    {
      "id": "chat_messages/Msg002",
      "chat_id": "chat_sessions/AbCdEfGhIj",
      "role": "assistant",
      "content": "AQI 3 — это умеренный уровень загрязнения воздуха. Уязвимым группам рекомендуется ограничить время на улице.",
      "created_at": "2026-05-17 09:01:03+05:00"
    }
  ]
}
```

**Примечания:**
- Сообщения отсортированы по времени (старые → новые)
- `role` может быть: `"user"` или `"assistant"`
- Сообщения сохраняются автоматически в порядке диалога

---

### 4. Отправить сообщение

Отправить сообщение в сессию и получить ответ от AI-ассистента.

**Метод:** `POST`  
**Путь:** `/api/chat/sessions/<str:chat_id>/send/`

**Параметры запроса:**
```json
{
  "message": "string"  // Текст сообщения пользователя (требуется, не пусто)
}
```

**Успешный ответ (200 OK):**
```json
{
  "status": "success",
  "data": {
    "user_message": {
      "id": "chat_messages/Msg001",
      "chat_id": "chat_sessions/AbCdEfGhIj",
      "role": "user",
      "content": "Что такое AQI 3?",
      "created_at": "2026-05-17 09:01:00+05:00"
    },
    "ai_message": {
      "id": "chat_messages/Msg002",
      "chat_id": "chat_sessions/AbCdEfGhIj",
      "role": "assistant",
      "content": "AQI 3 — это умеренный уровень загрязнения воздуха...",
      "created_at": "2026-05-17 09:01:03+05:00"
    },
    "session_title": "Что такое AQI 3?"
  }
}
```

**Примечания:**
- Оба сообщения (пользователя и AI) создаются и возвращаются в одном ответе
- Если это первое сообщение в сессии, `session_title` автоматически устанавливается из текста (макс. 60 символов)
- Если Gemma API недоступен, возвращается fallback текст в `ai_message.content`
- Всегда возвращается статус `200`, даже при ошибке Gemma (graceful degradation)

---

### 5. Переименовать сессию

Обновить название существующей сессии.

**Метод:** `PATCH`  
**Путь:** `/api/chat/sessions/<str:chat_id>/title/`

**Параметры запроса:**
```json
{
  "title": "string"  // Новое название (требуется, макс. 255 символов)
}
```

**Успешный ответ (200 OK):**
```json
{
  "status": "success",
  "data": {
    "id": "chat_sessions/AbCdEfGhIj",
    "user_uid": "device-uuid-здесь",
    "title": "Вопросы об AQI",
    "created_at": "2026-05-17 09:00:00+05:00",
    "updated_at": "2026-05-17 09:10:00+05:00"
  }
}
```

**Примечания:**
- Поле `updated_at` обновляется автоматически
- `created_at` не изменяется
- Максимальная длина названия: 255 символов

---

### 6. Удалить сессию

Удалить сессию и всю её историю сообщений.

**Метод:** `DELETE`  
**Путь:** `api/chat/sessions/<str:chat_id>/delete`

**Параметры запроса:** нет

**Успешный ответ (200 OK):**
```json
{
  "status": "success",
  "message": "Session deleted"
}
```

**Примечания:**
- Операция необратима
- Удаляются сессия и все её сообщения
- При удалении несуществующей сессии возвращается 404

---

## Коды ошибок

| Код | Причина | Пример ответа |
|-----|---------|---|
| **400** | Некорректные параметры запроса | `{"status": "error", "error": "message is required"}` |
| **400** | Пустое или отсутствует обязательное поле | `{"status": "error", "error": "title cannot be empty"}` |
| **404** | Сессия не найдена | `{"status": "error", "error": "Session not found"}` |
| **404** | Пользователь не найден | `{"status": "error", "error": "User not found"}` |
| **405** | Неверный HTTP метод | `{"status": "error", "error": "Method not allowed"}` |
| **500** | Внутренняя ошибка сервера | `{"status": "error", "error": "Internal server error"}` |
| **503** | Сервис временно недоступен | `{"status": "error", "error": "Service unavailable"}` |

---

## Примеры использования

### Полный цикл диалога

**1. Создать сессию:**
```bash
curl -X POST http://localhost:8000/api/chat/sessions/create/ \
  -H "Content-Type: application/json" \
  -d '{"user_uid": "user-123", "title": "Первый чат"}'
```

**2. Отправить сообщение:**
```bash
curl -X POST http://localhost:8000/api/chat/sessions/chat_sessions/AbCdEfGhIj/send/ \
  -H "Content-Type: application/json" \
  -d '{"message": "Как погода завтра?"}'
```

**3. Получить историю:**
```bash
curl -X GET http://localhost:8000/api/chat/sessions/chat_sessions/AbCdEfGhIj/messages/
```

**4. Переименовать сессию:**
```bash
curl -X PATCH http://localhost:8000/api/chat/sessions/chat_sessions/AbCdEfGhIj/title/ \
  -H "Content-Type: application/json" \
  -d '{"title": "Погода и AQI"}'
```

---

## Лучшие практики

1. **Сохраняй session_id** после создания — он нужен для всех операций
2. **Используй UUID** для user_uid (device identifiers)
3. **Обрабатывай graceful degradation** — AI может быть недоступен, но сообщение всё равно сохранится
4. **Проверяй статус** в каждом ответе (`"success"` или `"error"`)
5. **Не отправляй пустые сообщения** — вернётся ошибка 400
6. **Регулярно получай список сессий** для синхронизации на фронтенде
7. **Обрабатывай timeout** при отправке сообщений (рекомендуется 30+ секунд)
