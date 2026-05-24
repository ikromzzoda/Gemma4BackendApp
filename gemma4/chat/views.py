import json
import logging
import requests
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone

from .models import ChatSession
from django.views.decorators.csrf import csrf_exempt
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


def _load_history(chat_id: str) -> list[dict]:
    """Oldest → newest из субколлекции, один запрос."""
    docs = _msg_col(chat_id).order_by("created_at").stream()
    return [
        {
            "id": doc.id, "chat_id": chat_id,
            "role": doc.get("role"), "content": doc.get("content"),
            "created_at": str(doc.get("created_at")),
        }
        for doc in docs
    ]


# ══════════════════════════════════════════════════════════════════════════════
#  AQI CONTEXT  ← новый блок
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
        records = list(
            AirPollution.collection
            .filter("lat", "==", lat)
            .filter("lon", "==", lon)
            .fetch()
        )
        if records:
            records.sort(key=lambda r: r.created_at or "", reverse=True)
            fresh = records[0]
            if fresh.created_at and fresh.created_at >= one_hour_ago:
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
            f"http://api.openweathermap.org/data/2.5/air_pollution"
            f"?lat={lat}&lon={lon}&appid={OPENWEATHERMAP_API_KEY}"
        )
        return requests.get(url, timeout=10)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            aqi_future = executor.submit(get_aqi_by_coords, lat, lon)
            owm_future = executor.submit(fetch_owm)

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
        return f"{v:.1f}" if isinstance(v, float) else str(v) if v is not None else "—"

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


def _build_system_prompt(profile: dict | None) -> str:
    if not profile:
        return SYSTEM_PROMPT

    user_context = f"""
        Current user profile:
        - Name: {profile.get("firstName", "")} {profile.get("surname", "")}
        - Age group: {profile.get("ageGroup", "Unknown")}
        - Location: {profile.get("location", "Unknown")}
        - Activity level: {profile.get("activityLevel", "Unknown")}
        - Health conditions: {profile.get("healthCondition", "") or "None"}

        Personalization rules:
        - Address the user by first name when natural.
        - Use their location as default city for AQI/weather queries.
        - Consider health conditions in every health-related answer.
        - Tailor activity recommendations to their activity level.
        - ALWAYS reply in the exact language used by the user in their prompt.
        - When real-time AQI data is provided in the message, use those exact numbers.
          Never invent or approximate AQI values.
    """.strip()

    return SYSTEM_PROMPT + "\n\n" + user_context


# ══════════════════════════════════════════════════════════════════════════════
#  REQUEST HELPERS
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
#  SESSION VIEWS
# ══════════════════════════════════════════════════════════════════════════════

@csrf_exempt
def create_session(request):
    """POST /api/chat/sessions/"""
    if request.method != "POST":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)
    try:
        body = _parse_body(request)
    except ValueError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=400)

    user_uid = body.get("user_uid", "").strip()
    title    = body.get("title", "New Chat").strip() or "New Chat"

    if not user_uid:
        return JsonResponse({"status": "error", "error": "user_uid is required"}, status=400)

    try:
        session = ChatSession(user_uid=user_uid, title=title)
        session.save()
        return JsonResponse({"status": "success", "data": session.to_dict()}, status=201)
    except Exception as e:
        logger.error(f"create_session: {e}")
        return JsonResponse({"status": "error", "error": str(e)}, status=500)


@csrf_exempt
def list_sessions(request, user_uid: str):
    """GET /api/chat/users/<user_uid>/sessions/"""
    if request.method != "GET":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)
    try:
        raw      = ChatSession.collection.filter("user_uid", "==", user_uid).fetch()
        sessions = [s.to_dict() for s in raw]
        sessions.sort(key=lambda x: x["updated_at"] or x["created_at"] or "", reverse=True)
        return JsonResponse({"status": "success", "data": sessions}, status=200)
    except Exception as e:
        logger.error(f"list_sessions: {e}")
        return JsonResponse({"status": "error", "error": str(e)}, status=500)


@csrf_exempt
def delete_session(request, chat_id: str):
    """DELETE /api/chat/sessions/<chat_id>/delete"""
    if request.method != "DELETE":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)
    try:
        session = _get_session(chat_id)
    except LookupError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=404)

    try:
        db    = firestore.client()
        batch = db.batch()
        deleted_msgs = 0
        for doc in _msg_col(chat_id).stream():
            batch.delete(doc.reference)
            deleted_msgs += 1
        batch.delete(db.collection("chat_sessions").document(chat_id))
        batch.commit()
        return JsonResponse(
            {"status": "success", "message": f"Session and {deleted_msgs} message(s) deleted"},
            status=200,
        )
    except Exception as e:
        logger.error(f"delete_session: {e}")
        return JsonResponse({"status": "error", "error": str(e)}, status=500)


@csrf_exempt
def rename_session(request, chat_id: str):
    """PATCH /api/chat/sessions/<chat_id>/title/"""
    if request.method != "PATCH":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)
    try:
        body = _parse_body(request)
    except ValueError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=400)

    title = body.get("title", "").strip()
    if not title:
        return JsonResponse({"status": "error", "error": "title is required"}, status=400)

    try:
        session = _get_session(chat_id)
    except LookupError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=404)

    try:
        session.title      = title
        session.updated_at = timezone.now()
        session.update()
        return JsonResponse({"status": "success", "data": session.to_dict()}, status=200)
    except Exception as e:
        logger.error(f"rename_session: {e}")
        return JsonResponse({"status": "error", "error": str(e)}, status=500)


# ══════════════════════════════════════════════════════════════════════════════
#  MESSAGE VIEWS
# ══════════════════════════════════════════════════════════════════════════════

@csrf_exempt
def get_messages(request, chat_id: str):
    """GET /api/chat/sessions/<chat_id>/messages/"""
    if request.method != "GET":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)
    try:
        _get_session(chat_id)
    except LookupError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=404)

    try:
        messages = _load_history(chat_id)
        return JsonResponse({"status": "success", "chat_id": chat_id, "data": messages}, status=200)
    except Exception as e:
        logger.error(f"get_messages: {e}")
        return JsonResponse({"status": "error", "error": str(e)}, status=500)


@csrf_exempt
def send_message(request, chat_id: str):
    """
    POST /api/chat/sessions/<chat_id>/send/
    Body: { "message": "Какой сегодня AQI?" }

    Flow:
      1. Validate session.
      2. Load user profile (location, health, activity).
      3. Fetch REAL AQI data for user's city (cache → live API).
      4. Build personalized system prompt.
      5. Load message history.
      6. Save user message.
      7. Inject AQI context into Gemma call.
      8. Save AI reply.
      9. Update session.
    """
    if request.method != "POST":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)

    try:
        body = _parse_body(request)
    except ValueError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=400)

    user_text = body.get("message", "").strip()
    if not user_text:
        return JsonResponse({"status": "error", "error": "message is required"}, status=400)

    # ── 1. Validate session ────────────────────────────────────────────────
    try:
        session = _get_session(chat_id)
    except LookupError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=404)

    # ── 2. Load user profile ───────────────────────────────────────────────
    profile = _get_user_profile(session.user_uid)
    city    = (profile or {}).get("location", "Dushanbe")

    # ── 3. Fetch real AQI data for user's city ─────────────────────────────
    # Runs in background while we do other work
    with ThreadPoolExecutor(max_workers=1) as executor:
        aqi_future = executor.submit(_fetch_aqi_data, city)

        # ── 4. Build system prompt ─────────────────────────────────────────
        system_prompt = _build_system_prompt(profile)

        # ── 5. Load history ────────────────────────────────────────────────
        history = _load_history(chat_id)

        aqi_data = aqi_future.result()  # wait for AQI

    logger.info(
        f"send_message: AQI for '{city}' → "
        f"{aqi_data['aqi'] if aqi_data else 'unavailable'} "
        f"(source: {aqi_data.get('source', '?') if aqi_data else 'none'})"
    )

    # ── 6. Save user message ───────────────────────────────────────────────
    user_msg_dict = _save_message(chat_id, session.user_uid, "user", user_text)

    # ── 7. Build Gemma payload ─────────────────────────────────────────────
    # AQI context appended to the LAST user message (invisible to the user in UI)
    aqi_context   = _build_aqi_context(aqi_data)
    user_text_ctx = user_text + aqi_context

    contents = []
    for msg in history:
        api_role = "model" if msg["role"] == "assistant" else "user"
        contents.append({"role": api_role, "parts": [{"text": msg["content"]}]})
    contents.append({"role": "user", "parts": [{"text": user_text_ctx}]})

    ai_text = _call_gemma(contents, system_prompt)

    # ── 8. Save AI reply ───────────────────────────────────────────────────
    ai_msg_dict = _save_message(chat_id, session.user_uid, "assistant", ai_text)

    # ── 9. Auto-title + update session timestamp ───────────────────────────
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

def _call_gemma(contents: list, system_prompt: str) -> str:
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
        "generationConfig": {"maxOutputTokens": 500, "temperature": 0.7},
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
                return "Sorry, could not get a response."
            clean_lines = [
                line for line in full_text.splitlines()
                if line.strip() and not line.strip().startswith(("*", "-", "•", "#"))
            ]
            return "\n".join(clean_lines) if clean_lines else full_text.strip()
        except (KeyError, IndexError):
            logger.error(f"_call_gemma: unexpected format: {resp_json}")
            return "Sorry, could not get a response."

    try:
        response = requests.post(
            url,
            params={"key": settings.GEMMA4_API_KEY},
            json=payload,
            timeout=(10, 60),
        )
        response.raise_for_status()
        return _extract_text(response.json())
    except requests.exceptions.Timeout:
        logger.error("_call_gemma: timeout")
        return "Sorry, the request timed out. Please try again."
    except Exception as e:
        logger.error(f"_call_gemma failed ({type(e).__name__}): {e}")
        return "Sorry, could not process the request. Please try again."
