# OpenAPI 3.0 спецификация Chat API.
# Отдаётся по GET /api/chat/openapi.json и рендерится в Swagger UI на /api/chat/swagger/

_ERROR_SCHEMA = {"$ref": "#/components/schemas/Error"}

def _error_response(description: str, example: str) -> dict:
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": _ERROR_SCHEMA,
                "example": {"status": "error", "error": example},
            }
        },
    }


_SESSION_EXAMPLE = {
    "chat_id":    "xKpL9mNqRt",
    "user_uid":   "abc123uid",
    "title":      "Air Quality Questions",
    "created_at": "2026-06-15 10:00:00.000000+05:00",
    "updated_at": "2026-06-15 10:05:00.000000+05:00",
}

_USER_MESSAGE_EXAMPLE = {
    "id":         "3f2a1b9c-8d4e-4f5a-9b1c-2d3e4f5a6b7c",
    "chat_id":    "xKpL9mNqRt",
    "role":       "user",
    "content":    "Какой сегодня AQI в Душанбе?",
    "created_at": "2026-06-15 10:05:00.000000+05:00",
}

_AI_MESSAGE_EXAMPLE = {
    "id":         "9a8b7c6d-5e4f-3a2b-1c0d-e9f8a7b6c5d4",
    "chat_id":    "xKpL9mNqRt",
    "role":       "assistant",
    "content":    "AQI в Душанбе сейчас 87 — умеренный уровень загрязнения. PM2.5 составляет 24.5 µg/m³.",
    "created_at": "2026-06-15 10:05:03.000000+05:00",
}

_AQI_EXAMPLE = {
    "city": "Dushanbe", "aqi": 87, "aqi_label": "Moderate",
    "pm25": 24.5, "pm10": 38.2, "no2": 12.1,
    "o3": 55.0, "so2": 4.3, "co": 210.0, "source": "cache",
}

_CHAT_ID_PARAM = {
    "name": "chat_id",
    "in": "path",
    "required": True,
    "schema": {"type": "string"},
    "example": "xKpL9mNqRt",
    "description": "ID сессии (Firestore document ID из поля `chat_id`)",
}

_401 = {"401": _error_response(
    "Нет или невалиден Firebase ID token",
    "Authentication required: pass a Firebase ID token in the Authorization: Bearer header",
)}
_403 = {"403": _error_response(
    "Ресурс принадлежит другому пользователю",
    "Forbidden: session belongs to another user",
)}
_404 = {"404": _error_response("Сессия не найдена", "Session not found")}
_405 = {"405": _error_response("Неверный HTTP-метод", "Method not allowed")}
_500 = {"500": _error_response("Внутренняя ошибка сервера", "Internal server error")}


OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "Chat API — Airi",
        "version": "1.0.0",
        "description": (
            "AI-чат с контекстом качества воздуха (Gemma 4).\n\n"
            "**Авторизация обязательна для всех endpoints**: заголовок "
            "`Authorization: Bearer <firebase_id_token>`.\n"
            "Токен берётся на клиенте после входа через Firebase Auth "
            "(во Flutter: `FirebaseAuth.instance.currentUser.getIdToken()`).\n\n"
            "Нажмите **Authorize** и вставьте ID token, чтобы пробовать запросы прямо отсюда."
        ),
    },
    "servers": [{"url": "/", "description": "Текущий хост"}],
    "tags": [
        {"name": "Sessions", "description": "Управление чат-сессиями"},
        {"name": "Messages", "description": "Сообщения и общение с AI"},
    ],
    "security": [{"firebaseAuth": []}],
    "components": {
        "securitySchemes": {
            "firebaseAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Firebase ID token пользователя",
            }
        },
        "schemas": {
            "Error": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["error"]},
                    "error":  {"type": "string"},
                },
                "required": ["status", "error"],
            },
            "ChatSession": {
                "type": "object",
                "properties": {
                    "chat_id":    {"type": "string", "description": "Firestore document ID, используется как ID сессии"},
                    "user_uid":   {"type": "string", "description": "Firebase Auth UID владельца"},
                    "title":      {"type": "string"},
                    "created_at": {"type": "string", "nullable": True},
                    "updated_at": {"type": "string", "nullable": True},
                },
                "example": _SESSION_EXAMPLE,
            },
            "Message": {
                "type": "object",
                "properties": {
                    "id":         {"type": "string", "format": "uuid"},
                    "chat_id":    {"type": "string"},
                    "role":       {"type": "string", "enum": ["user", "assistant"]},
                    "content":    {"type": "string"},
                    "created_at": {"type": "string"},
                },
                "example": _USER_MESSAGE_EXAMPLE,
            },
            "AQIData": {
                "type": "object",
                "nullable": True,
                "description": "Данные AQI, реально переданные в Gemma (поле для отладки)",
                "properties": {
                    "city":      {"type": "string"},
                    "aqi":       {"type": "number", "nullable": True, "description": "AQI по шкале US"},
                    "aqi_label": {"type": "string", "description": "Good / Moderate / Unhealthy for Sensitive Groups / Unhealthy / Very Unhealthy / Hazardous"},
                    "pm25":      {"type": "number", "nullable": True},
                    "pm10":      {"type": "number", "nullable": True},
                    "no2":       {"type": "number", "nullable": True},
                    "o3":        {"type": "number", "nullable": True},
                    "so2":       {"type": "number", "nullable": True},
                    "co":        {"type": "number", "nullable": True},
                    "source":    {"type": "string", "enum": ["cache", "live"], "description": "cache — из Firestore (< 1 часа), live — из внешних API"},
                },
                "example": _AQI_EXAMPLE,
            },
        },
    },
    "paths": {
        "/api/chat/sessions/": {
            "post": {
                "tags": ["Sessions"],
                "summary": "Создать сессию",
                "description": "Создаёт новую чат-сессию. `user_uid` берётся из Firebase-токена, поле в теле игнорируется.",
                "operationId": "createSession",
                "requestBody": {
                    "required": False,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string", "description": "Название сессии, по умолчанию \"New Chat\""},
                                },
                            },
                            "example": {"title": "Air Quality Questions"},
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "Сессия создана",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string", "enum": ["success"]},
                                        "data":   {"$ref": "#/components/schemas/ChatSession"},
                                    },
                                },
                                "example": {
                                    "status": "success",
                                    "data": {**_SESSION_EXAMPLE, "updated_at": None},
                                },
                            }
                        },
                    },
                    "400": _error_response("Невалидный JSON", "Invalid JSON body"),
                    **_401, **_405, **_500,
                },
            }
        },
        "/api/chat/users/{user_uid}/sessions/": {
            "get": {
                "tags": ["Sessions"],
                "summary": "Список сессий пользователя",
                "description": "Все сессии пользователя, новые первыми. `user_uid` должен совпадать с uid из токена.",
                "operationId": "listSessions",
                "parameters": [{
                    "name": "user_uid",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                    "example": "abc123uid",
                    "description": "Firebase Auth UID (должен совпадать с uid из токена)",
                }],
                "responses": {
                    "200": {
                        "description": "Список сессий (пустой массив, если нет)",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string", "enum": ["success"]},
                                        "data": {
                                            "type": "array",
                                            "items": {"$ref": "#/components/schemas/ChatSession"},
                                        },
                                    },
                                },
                                "example": {"status": "success", "data": [_SESSION_EXAMPLE]},
                            }
                        },
                    },
                    **_401, **_403, **_405, **_500,
                },
            }
        },
        "/api/chat/sessions/{chat_id}/delete": {
            "delete": {
                "tags": ["Sessions"],
                "summary": "Удалить сессию",
                "description": "Удаляет сессию и **все её сообщения**. Операция необратима.",
                "operationId": "deleteSession",
                "parameters": [_CHAT_ID_PARAM],
                "responses": {
                    "200": {
                        "description": "Сессия и сообщения удалены",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status":  {"type": "string", "enum": ["success"]},
                                        "message": {"type": "string"},
                                    },
                                },
                                "example": {"status": "success", "message": "Session and 12 message(s) deleted"},
                            }
                        },
                    },
                    **_401, **_403, **_404, **_405, **_500,
                },
            }
        },
        "/api/chat/sessions/{chat_id}/title/": {
            "patch": {
                "tags": ["Sessions"],
                "summary": "Переименовать сессию",
                "operationId": "renameSession",
                "parameters": [_CHAT_ID_PARAM],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {"title": {"type": "string"}},
                                "required": ["title"],
                            },
                            "example": {"title": "Dushanbe Air Quality"},
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Обновлённая сессия",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string", "enum": ["success"]},
                                        "data":   {"$ref": "#/components/schemas/ChatSession"},
                                    },
                                },
                                "example": {
                                    "status": "success",
                                    "data": {**_SESSION_EXAMPLE, "title": "Dushanbe Air Quality"},
                                },
                            }
                        },
                    },
                    "400": _error_response("`title` не передан или пустой", "title is required"),
                    **_401, **_403, **_404, **_405, **_500,
                },
            }
        },
        "/api/chat/sessions/{chat_id}/messages/": {
            "get": {
                "tags": ["Messages"],
                "summary": "История сообщений",
                "description": "Все сообщения сессии от старых к новым.",
                "operationId": "getMessages",
                "parameters": [_CHAT_ID_PARAM],
                "responses": {
                    "200": {
                        "description": "Массив сообщений (пустой, если нет)",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status":  {"type": "string", "enum": ["success"]},
                                        "chat_id": {"type": "string"},
                                        "data": {
                                            "type": "array",
                                            "items": {"$ref": "#/components/schemas/Message"},
                                        },
                                    },
                                },
                                "example": {
                                    "status":  "success",
                                    "chat_id": "xKpL9mNqRt",
                                    "data": [_USER_MESSAGE_EXAMPLE, _AI_MESSAGE_EXAMPLE],
                                },
                            }
                        },
                    },
                    **_401, **_403, **_404, **_405, **_500,
                },
            }
        },
        "/api/chat/sessions/{chat_id}/send/": {
            "post": {
                "tags": ["Messages"],
                "summary": "Отправить сообщение и получить ответ AI",
                "description": (
                    "Главный endpoint. В Gemma передаются последние 30 сообщений истории и "
                    "реальные данные AQI города пользователя. При недоступности AI возвращается "
                    "`502` и **ничего не сохраняется** — запрос можно безопасно повторить.\n\n"
                    "Auto-title: если title сессии ещё \"New Chat\", он заменяется первыми "
                    "60 символами сообщения."
                ),
                "operationId": "sendMessage",
                "parameters": [_CHAT_ID_PARAM],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {"message": {"type": "string"}},
                                "required": ["message"],
                            },
                            "example": {"message": "Какой сегодня AQI в Душанбе?"},
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Сообщение сохранено, ответ AI получен",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status":  {"type": "string", "enum": ["success"]},
                                        "chat_id": {"type": "string"},
                                        "data": {
                                            "type": "object",
                                            "properties": {
                                                "user_message":  {"$ref": "#/components/schemas/Message"},
                                                "ai_message":    {"$ref": "#/components/schemas/Message"},
                                                "session_title": {"type": "string"},
                                                "aqi_used":      {"$ref": "#/components/schemas/AQIData"},
                                            },
                                        },
                                    },
                                },
                                "example": {
                                    "status":  "success",
                                    "chat_id": "xKpL9mNqRt",
                                    "data": {
                                        "user_message":  _USER_MESSAGE_EXAMPLE,
                                        "ai_message":    _AI_MESSAGE_EXAMPLE,
                                        "session_title": "Какой сегодня AQI в Душанбе?",
                                        "aqi_used":      _AQI_EXAMPLE,
                                    },
                                },
                            }
                        },
                    },
                    "400": _error_response("`message` пустой или невалидный JSON", "message is required"),
                    **_401, **_403, **_404, **_405,
                    "429": {
                        "description": "Исчерпан дневной лимит AI (10 000 выходных токенов на пользователя в день)",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status":            {"type": "string", "enum": ["error"]},
                                        "error":             {"type": "string"},
                                        "tokens_used_today": {"type": "integer"},
                                        "daily_limit":       {"type": "integer"},
                                    },
                                },
                                "example": {
                                    "status": "error",
                                    "error":  "Daily AI usage limit reached. Try again tomorrow.",
                                    "tokens_used_today": 10240,
                                    "daily_limit": 10000,
                                },
                            }
                        },
                    },
                    "502": _error_response(
                        "Gemma недоступна или таймаут — ничего не сохранено",
                        "AI service is temporarily unavailable. Please try again.",
                    ),
                },
            }
        },
    },
}
