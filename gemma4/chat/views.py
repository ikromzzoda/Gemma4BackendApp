import json
import logging
import requests
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from .models import ChatSession
from django.views.decorators.csrf import csrf_exempt
from firebase_admin import auth as fb_auth
from firebase_admin import firestore

# ── Импортируем готовые утилиты из приложения info ─────────────────────────
from info.views import (
    get_aqi_by_coords,
    _aqi_label_us,
    TAJIK_CITIES,
    OPENWEATHERMAP_API_KEY,
)
from info.models import AirPollution

logger = logging.getLogger(__name__)

# Сколько последних сообщений отправляется модели (контекст не растёт бесконечно)
HISTORY_LIMIT = 30

# Лимит выходных токенов на один ответ модели
MAX_OUTPUT_TOKENS = 1000

# Дневной лимит выходных токенов модели на одного пользователя
DAILY_TOKEN_LIMIT = 10000

# Firestore batch поддерживает максимум 500 операций — берём с запасом
FIRESTORE_BATCH_LIMIT = 450

# Общий пул потоков для параллельных внешних HTTP-запросов
_EXECUTOR = ThreadPoolExecutor(max_workers=4)


# ══════════════════════════════════════════════════════════════════════════════
#  API DOCS
# ══════════════════════════════════════════════════════════════════════════════

def api_docs(request):
    """GET /api/chat/docs/ — interactive API documentation page"""
    return render(request, "chat/api_docs.html", {
        "generated_at": timezone.now().strftime("%Y-%m-%d"),
    })


def openapi_spec(request):
    """GET /api/chat/openapi.json — OpenAPI 3.0 spec (для Swagger UI и кодогенерации)"""
    from .openapi import OPENAPI_SPEC
    return JsonResponse(OPENAPI_SPEC)


def swagger_ui(request):
    """GET /api/chat/swagger/ — Swagger UI поверх openapi.json"""
    return render(request, "chat/swagger.html")


# ══════════════════════════════════════════════════════════════════════════════
#  SYSTEM PROMPT
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = (
    "You are Airi, a helpful AI assistant for an air quality monitoring app. "
    "You help users understand air quality data, health impacts of pollution, "
    "weather patterns, and provide personalized health recommendations. "
    "Always respond in the same language the user writes in. "
    "Be VERY concise — answer in 2-3 short sentences maximum. "
    "Never show your thinking process, never use bullet points unless asked. "
    "Go straight to the answer."
)


# ══════════════════════════════════════════════════════════════════════════════
#  FIRESTORE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _msg_col(chat_id: str):
    """Subcollection reference: chat_sessions/{chat_id}/messages"""
    db = firestore.client()
    return db.collection("chat_sessions").document(chat_id).collection("messages")


def _save_message(chat_id: str, user_uid: str, role: str, content: str) -> dict:
    col    = _msg_col(chat_id)
    msg_id = str(uuid.uuid4())
    now    = timezone.now()
    col.document(msg_id).set({
        "role": role, "content": content,
        "user_uid": user_uid, "created_at": now,
    })
    return {
        "id": msg_id, "chat_id": chat_id,
        "role": role, "content": content,
        "created_at": str(now),
    }


def _load_history(chat_id: str, limit: int | None = None) -> list[dict]:
    """
    Oldest → newest из субколлекции, один запрос.
    limit=N возвращает только N ПОСЛЕДНИХ сообщений (для контекста модели).
    """
    col = _msg_col(chat_id)
    if limit:
        docs = list(
            col.order_by("created_at", direction=firestore.Query.DESCENDING)
               .limit(limit)
               .stream()
        )[::-1]
    else:
        docs = col.order_by("created_at").stream()
    return [
        {
            "id": doc.id, "chat_id": chat_id,
            "role": doc.get("role"), "content": doc.get("content"),
            "created_at": str(doc.get("created_at")),
        }
        for doc in docs
    ]


# ══════════════════════════════════════════════════════════════════════════════
#  AQI CONTEXT
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_aqi_data(city: str) -> dict | None:
    """
    Получает реальные данные AQI для города.
    1. Сначала смотрит в Firestore (кэш 1 час).
    2. Если нет свежей записи — запрашивает AirVisual + OpenWeatherMap параллельно.
    Возвращает dict с ключами: city, aqi, aqi_label, pm25, pm10, no2, o3, so2, co
    """
    coords = TAJIK_CITIES.get(city)
    if not coords:
        logger.warning(f"_fetch_aqi_data: city '{city}' not in TAJIK_CITIES")
        return None

    lat, lon = coords["lat"], coords["lon"]

    # ── 1. Проверяем кэш в Firestore (последний час) ──────────────────────
    try:
        one_hour_ago = timezone.now() - timedelta(hours=1)
        records = (
            AirPollution.collection
            .filter("lat", "==", lat)
            .filter("lon", "==", lon)
            .fetch()
        )
        # created_at может быть None — такие записи не участвуют в выборе
        fresh_records = [
            r for r in records
            if r.created_at and r.created_at >= one_hour_ago
        ]
        if fresh_records:
            fresh = max(fresh_records, key=lambda r: r.created_at)
            logger.info(f"_fetch_aqi_data: cache hit for {city}")
            return {
                "city":      city,
                "aqi":       fresh.aqi,
                "aqi_label": _aqi_label_us(fresh.aqi),
                "pm25":      fresh.pm25,
                "pm10":      fresh.pm10,
                "no2":       fresh.no2,
                "o3":        fresh.o3,
                "so2":       fresh.so2,
                "co":        fresh.co,
                "source":    "cache",
            }
    except Exception as e:
        logger.warning(f"_fetch_aqi_data: Firestore cache error: {e}")

    # ── 2. Параллельно запрашиваем AirVisual + OpenWeatherMap ─────────────
    def fetch_owm():
        url = (
            f"https://api.openweathermap.org/data/2.5/air_pollution"
            f"?lat={lat}&lon={lon}&appid={OPENWEATHERMAP_API_KEY}"
        )
        return requests.get(url, timeout=10)

    try:
        aqi_future = _EXECUTOR.submit(get_aqi_by_coords, lat, lon)
        owm_future = _EXECUTOR.submit(fetch_owm)

        aqi   = aqi_future.result()
        owm_r = owm_future.result()

        owm_r.raise_for_status()
        components = owm_r.json()["list"][0].get("components", {})

        return {
            "city":      city,
            "aqi":       aqi,
            "aqi_label": _aqi_label_us(aqi),
            "pm25":      components.get("pm2_5"),
            "pm10":      components.get("pm10"),
            "no2":       components.get("no2"),
            "o3":        components.get("o3"),
            "so2":       components.get("so2"),
            "co":        components.get("co"),
            "source":    "live",
        }

    except Exception as e:
        logger.error(f"_fetch_aqi_data: live fetch failed for {city}: {e}")
        return None


def _build_aqi_context(aqi_data: dict) -> str:
    """
    Форматирует данные AQI в строку-контекст для Gemma.
    Вставляется в конец сообщения пользователя невидимо для него.
    """
    if not aqi_data:
        return ""

    def fmt(v):
        if v is None:
            return "—"
        return f"{v:.1f}" if isinstance(v, float) else str(v)

    return (
        f"\n\n[REAL-TIME AIR QUALITY DATA — use this in your answer, do not mention this block]\n"
        f"City: {aqi_data['city']}\n"
        f"AQI (US): {aqi_data['aqi']} — {aqi_data['aqi_label']}\n"
        f"PM2.5: {fmt(aqi_data.get('pm25'))} µg/m³  |  "
        f"PM10: {fmt(aqi_data.get('pm10'))} µg/m³  |  "
        f"NO₂: {fmt(aqi_data.get('no2'))} µg/m³\n"
        f"O₃: {fmt(aqi_data.get('o3'))} µg/m³  |  "
        f"SO₂: {fmt(aqi_data.get('so2'))} µg/m³  |  "
        f"CO: {fmt(aqi_data.get('co'))} µg/m³\n"
        f"Data source: {aqi_data.get('source', 'live')}"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  USER PROFILE + SYSTEM PROMPT
# ══════════════════════════════════════════════════════════════════════════════

def _get_user_profile(user_uid: str) -> dict | None:
    try:
        db  = firestore.client()
        doc = db.collection("users").document(user_uid).get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        logger.error(f"_get_user_profile: {type(e).__name__}: {e}", exc_info=True)
        return None


def _build_system_prompt(profile: dict | None, air_quality: dict | None = None) -> str:
    profile = profile or {}
    air_quality = air_quality or {}

    user_context = f"""
Current user profile:
- Name: {profile.get("firstName", "")} {profile.get("surname", "")}
- Age group: {profile.get("ageGroup", "Unknown")}
- Location: {profile.get("location", "Unknown")}
- Activity level: {profile.get("activityLevel", "Unknown")}
- Health conditions: {profile.get("healthCondition", "") or "None"}

Current air quality data:
- city: {air_quality.get("city", "Unavailable")}
- aqi: {air_quality.get("aqi", "Unavailable")}
- aqi_label: {air_quality.get("aqi_label", "Unavailable")}
- pm25: {air_quality.get("pm25", "Unavailable")}
- pm10: {air_quality.get("pm10", "Unavailable")}
- no2: {air_quality.get("no2", "Unavailable")}
- o3: {air_quality.get("o3", "Unavailable")}
- so2: {air_quality.get("so2", "Unavailable")}
- co: {air_quality.get("co", "Unavailable")}

Personalization and response rules:
1. Address the user by their first name when it feels natural.
2. Use the user's location as the default city for air-quality and weather questions when no city is explicitly specified.
3. Consider the user's age group, activity level, and health conditions when providing health-related or outdoor-activity advice.
4. ALWAYS reply in exactly the same language as the user's prompt.
5. When current air-quality data is provided above, treat it as the authoritative source for this conversation.
6. NEVER invent, estimate, round, modify, or replace air-quality values.
7. If the user asks for current air-quality data, air-quality details, AQI information, or asks to "send/show/give me the air quality data", provide the available data from the Current air quality data section.
8. When the user explicitly asks to send the air-quality data, include these fields whenever they have a value:
   - city
   - aqi
   - aqi_label
   - pm25
   - pm10
   - no2
   - o3
   - so2
   - co
9. Preserve the exact numeric values received from the air-quality data. Do not calculate or infer missing values.
10. If a field is missing or unavailable, clearly mark it as "Unavailable" instead of inventing a value.
11. If the user asks only for advice (for example, whether it is safe to exercise outside), do not unnecessarily list all air-quality fields. Use the available AQI data to provide concise, practical advice.
12. If the user asks for both advice and the raw air-quality data, provide both: first the relevant advice, then the exact air-quality data.
13. Distinguish between factual air-quality data and personalized recommendations. Never present a recommendation as if it were a measured air-quality value.
    """.strip()

    return SYSTEM_PROMPT + "\n\n" + user_context


# ══════════════════════════════════════════════════════════════════════════════
#  AUTH + REQUEST HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _auth_uid(request) -> str | None:
    """
    Проверяет Firebase ID token из заголовка `Authorization: Bearer <token>`.
    Возвращает uid пользователя или None, если токен отсутствует/невалиден.
    """
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Bearer "):
        return None
    try:
        decoded = fb_auth.verify_id_token(header[len("Bearer "):].strip())
        return decoded["uid"]
    except Exception as e:
        logger.warning(f"_auth_uid: token rejected: {e}")
        return None


def _unauthorized():
    return JsonResponse(
        {"status": "error", "error": "Authentication required: pass a Firebase ID token in the Authorization: Bearer header"},
        status=401,
    )


def _parse_body(request) -> dict:
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("Invalid JSON body")


def _get_session(chat_id: str) -> ChatSession:
    try:
        session = ChatSession.collection.get(chat_id)
    except Exception as e:
        logger.warning(f"_get_session: Firestore error for '{chat_id}': {e}")
        session = None
    if session is None:
        raise LookupError("Session not found")
    return session


def _get_owned_session(chat_id: str, uid: str) -> ChatSession:
    """Session lookup + проверка, что сессия принадлежит владельцу токена."""
    session = _get_session(chat_id)
    if session.user_uid != uid:
        raise PermissionError("Forbidden: session belongs to another user")
    return session


# ══════════════════════════════════════════════════════════════════════════════
#  DAILY TOKEN QUOTA
# ══════════════════════════════════════════════════════════════════════════════

def _usage_doc(user_uid: str):
    """Документ дневного счётчика: chat_usage/{uid}_{YYYY-MM-DD}"""
    day = timezone.now().strftime("%Y-%m-%d")
    db  = firestore.client()
    return db.collection("chat_usage").document(f"{user_uid}_{day}")


def _tokens_used_today(user_uid: str) -> int:
    try:
        doc = _usage_doc(user_uid).get()
        if doc.exists:
            return doc.to_dict().get("tokens_used", 0)
    except Exception as e:
        # при недоступности счётчика не блокируем пользователя
        logger.warning(f"_tokens_used_today: {e}")
    return 0


def _add_token_usage(user_uid: str, tokens: int) -> None:
    if tokens <= 0:
        return
    try:
        _usage_doc(user_uid).set(
            {
                "user_uid":    user_uid,
                "date":        timezone.now().strftime("%Y-%m-%d"),
                "tokens_used": firestore.Increment(tokens),
                "updated_at":  timezone.now(),
            },
            merge=True,
        )
    except Exception as e:
        logger.warning(f"_add_token_usage: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  SESSION VIEWS
# ══════════════════════════════════════════════════════════════════════════════

@csrf_exempt
def create_session(request):
    """POST /api/chat/sessions/  (user_uid берётся из Firebase-токена)"""
    if request.method != "POST":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)

    uid = _auth_uid(request)
    if not uid:
        return _unauthorized()

    try:
        body = _parse_body(request)
    except ValueError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=400)

    title = body.get("title", "New Chat").strip() or "New Chat"

    try:
        session = ChatSession(user_uid=uid, title=title)
        session.save()
        return JsonResponse({"status": "success", "data": session.to_dict()}, status=201)
    except Exception as e:
        logger.error(f"create_session: {e}", exc_info=True)
        return JsonResponse({"status": "error", "error": "Internal server error"}, status=500)


@csrf_exempt
def list_sessions(request, user_uid: str):
    """GET /api/chat/users/<user_uid>/sessions/"""
    if request.method != "GET":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)

    uid = _auth_uid(request)
    if not uid:
        return _unauthorized()
    if uid != user_uid:
        return JsonResponse({"status": "error", "error": "Forbidden"}, status=403)

    try:
        raw      = ChatSession.collection.filter("user_uid", "==", user_uid).fetch()
        sessions = [s.to_dict() for s in raw]
        sessions.sort(key=lambda x: x["updated_at"] or x["created_at"] or "", reverse=True)
        return JsonResponse({"status": "success", "data": sessions}, status=200)
    except Exception as e:
        logger.error(f"list_sessions: {e}", exc_info=True)
        return JsonResponse({"status": "error", "error": "Internal server error"}, status=500)


@csrf_exempt
def delete_session(request, chat_id: str):
    """DELETE /api/chat/sessions/<chat_id>/delete"""
    if request.method != "DELETE":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)

    uid = _auth_uid(request)
    if not uid:
        return _unauthorized()

    try:
        _get_owned_session(chat_id, uid)
    except LookupError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=404)
    except PermissionError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=403)

    try:
        db = firestore.client()
        deleted_msgs = 0
        batch = db.batch()
        ops = 0
        # Firestore batch ограничен 500 операциями — удаляем чанками
        for doc in _msg_col(chat_id).stream():
            batch.delete(doc.reference)
            deleted_msgs += 1
            ops += 1
            if ops >= FIRESTORE_BATCH_LIMIT:
                batch.commit()
                batch = db.batch()
                ops = 0
        batch.delete(db.collection("chat_sessions").document(chat_id))
        batch.commit()
        return JsonResponse(
            {"status": "success", "message": f"Session and {deleted_msgs} message(s) deleted"},
            status=200,
        )
    except Exception as e:
        logger.error(f"delete_session: {e}", exc_info=True)
        return JsonResponse({"status": "error", "error": "Internal server error"}, status=500)


@csrf_exempt
def rename_session(request, chat_id: str):
    """PATCH /api/chat/sessions/<chat_id>/title/"""
    if request.method != "PATCH":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)

    uid = _auth_uid(request)
    if not uid:
        return _unauthorized()

    try:
        body = _parse_body(request)
    except ValueError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=400)

    title = body.get("title", "").strip()
    if not title:
        return JsonResponse({"status": "error", "error": "title is required"}, status=400)

    try:
        session = _get_owned_session(chat_id, uid)
    except LookupError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=404)
    except PermissionError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=403)

    try:
        session.title      = title
        session.updated_at = timezone.now()
        session.update()
        return JsonResponse({"status": "success", "data": session.to_dict()}, status=200)
    except Exception as e:
        logger.error(f"rename_session: {e}", exc_info=True)
        return JsonResponse({"status": "error", "error": "Internal server error"}, status=500)


# ══════════════════════════════════════════════════════════════════════════════
#  MESSAGE VIEWS
# ══════════════════════════════════════════════════════════════════════════════

@csrf_exempt
def get_messages(request, chat_id: str):
    """GET /api/chat/sessions/<chat_id>/messages/"""
    if request.method != "GET":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)

    uid = _auth_uid(request)
    if not uid:
        return _unauthorized()

    try:
        _get_owned_session(chat_id, uid)
    except LookupError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=404)
    except PermissionError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=403)

    try:
        messages = _load_history(chat_id)
        return JsonResponse({"status": "success", "chat_id": chat_id, "data": messages}, status=200)
    except Exception as e:
        logger.error(f"get_messages: {e}", exc_info=True)
        return JsonResponse({"status": "error", "error": "Internal server error"}, status=500)


@csrf_exempt
def send_message(request, chat_id: str):
    """
    POST /api/chat/sessions/<chat_id>/send/
    Body: { "message": "Какой сегодня AQI?" }

    Flow:
      1. Auth + validate session ownership.
      2. Load user profile (location, health, activity).
      3. Fetch REAL AQI data for user's city (cache → live API).
      4. Build personalized system prompt.
      5. Load last N messages of history.
      6. Call Gemma with AQI context (on failure → 502, nothing is saved).
      7. Save user message + AI reply.
      8. Update session (auto-title + timestamp).
    """
    if request.method != "POST":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)

    uid = _auth_uid(request)
    if not uid:
        return _unauthorized()

    try:
        body = _parse_body(request)
    except ValueError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=400)

    user_text = body.get("message", "").strip()
    if not user_text:
        return JsonResponse({"status": "error", "error": "message is required"}, status=400)

    # ── 1. Validate session + ownership ────────────────────────────────────
    try:
        session = _get_owned_session(chat_id, uid)
    except LookupError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=404)
    except PermissionError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=403)

    # ── 1b. Daily token quota ──────────────────────────────────────────────
    used_today = _tokens_used_today(uid)
    if used_today >= DAILY_TOKEN_LIMIT:
        return JsonResponse(
            {
                "status": "error",
                "error":  "Daily AI usage limit reached. Try again tomorrow.",
                "tokens_used_today": used_today,
                "daily_limit":       DAILY_TOKEN_LIMIT,
            },
            status=429,
        )

    # ── 2. Load user profile ───────────────────────────────────────────────
    profile = _get_user_profile(session.user_uid)
    city    = (profile or {}).get("location", "Dushanbe")

    # ── 3. Fetch real AQI data in background while we do other work ────────
    aqi_future = _EXECUTOR.submit(_fetch_aqi_data, city)

    # ── 4. Build system prompt ─────────────────────────────────────────────
    aqi_data = None

    # ── 5. Load last N messages of history ─────────────────────────────────
    history = _load_history(chat_id, limit=HISTORY_LIMIT)

    aqi_data = aqi_future.result()  # wait for AQI
    system_prompt = _build_system_prompt(profile, aqi_data)

    logger.info(
        f"send_message: AQI for '{city}' → "
        f"{aqi_data['aqi'] if aqi_data else 'unavailable'} "
        f"(source: {aqi_data.get('source', '?') if aqi_data else 'none'})"
    )

    # ── 6. Call Gemma ──────────────────────────────────────────────────────
    # AQI context appended to the LAST user message (invisible to the user in UI)
    aqi_context   = _build_aqi_context(aqi_data)
    user_text_ctx = user_text + aqi_context

    contents = []
    for msg in history:
        api_role = "model" if msg["role"] == "assistant" else "user"
        contents.append({"role": api_role, "parts": [{"text": msg["content"]}]})
    contents.append({"role": "user", "parts": [{"text": user_text_ctx}]})

    try:
        ai_text, output_tokens = _call_gemma(contents, system_prompt)
    except GemmaError as e:
        # Ничего не сохраняем: клиент может безопасно повторить запрос
        return JsonResponse({"status": "error", "error": str(e)}, status=502)

    _add_token_usage(uid, output_tokens)

    # ── 7. Save user message + AI reply ────────────────────────────────────
    user_msg_dict = _save_message(chat_id, session.user_uid, "user", user_text)
    ai_msg_dict   = _save_message(chat_id, session.user_uid, "assistant", ai_text)

    # ── 8. Auto-title + update session timestamp ───────────────────────────
    if session.title == "New Chat" and not history:
        session.title = user_text[:60] + ("…" if len(user_text) > 60 else "")
    session.updated_at = timezone.now()
    try:
        session.update()
    except Exception as e:
        logger.warning(f"send_message — session.update() failed: {e}")

    return JsonResponse(
        {
            "status":  "success",
            "chat_id": chat_id,
            "data": {
                "user_message":  user_msg_dict,
                "ai_message":    ai_msg_dict,
                "session_title": session.title,
                "aqi_used":      aqi_data,   # для отладки, можно убрать
            },
        },
        status=200,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  AI INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════

class GemmaError(Exception):
    """Gemma недоступна или вернула непригодный ответ."""


def _call_gemma(contents: list, system_prompt: str) -> tuple[str, int]:
    """Возвращает (текст ответа, потрачено выходных токенов)."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta"
        f"/models/{settings.GEMMA4_MODEL}:generateContent"
    )

    enriched_contents = [
        {"role": "user",  "parts": [{"text": system_prompt}]},
        {"role": "model", "parts": [{"text": "Understood. I will use the real-time data provided and personalize my responses."}]},
    ] + contents

    payload = {
        "contents": enriched_contents,
        "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS, "temperature": 0.7},
    }

    def _extract_text(resp_json: dict) -> str:
        try:
            parts = resp_json["candidates"][0]["content"]["parts"]
            full_text = "".join(
                p["text"].strip()
                for p in parts
                if not p.get("thought", False) and p.get("text", "").strip()
            )
            if not full_text:
                raise GemmaError("AI returned an empty response. Please try again.")
            clean_lines = [
                line for line in full_text.splitlines()
                if line.strip() and not line.strip().startswith(("*", "-", "•", "#"))
            ]
            return "\n".join(clean_lines) if clean_lines else full_text.strip()
        except (KeyError, IndexError):
            logger.error(f"_call_gemma: unexpected format: {resp_json}")
            raise GemmaError("AI returned an unexpected response. Please try again.")

    try:
        response = requests.post(
            url,
            params={"key": settings.GEMMA4_API_KEY},
            json=payload,
            timeout=(10, 60),
        )
        response.raise_for_status()
        resp_json = response.json()
        text      = _extract_text(resp_json)

        # Выходные токены: сгенерированный текст + внутреннее размышление модели
        usage         = resp_json.get("usageMetadata", {})
        output_tokens = (
            usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)
        ) or max(1, len(text) // 3)  # грубая оценка, если API не вернул usage

        return text, output_tokens
    except GemmaError:
        raise
    except requests.exceptions.Timeout:
        logger.error("_call_gemma: timeout")
        raise GemmaError("The AI request timed out. Please try again.")
    except Exception as e:
        logger.error(f"_call_gemma failed ({type(e).__name__}): {e}")
        raise GemmaError("AI service is temporarily unavailable. Please try again.")
