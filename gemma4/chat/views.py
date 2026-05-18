import json
import logging
import requests

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone

from .models import ChatSession, Message
from django.views.decorators.csrf import csrf_exempt
from firebase_admin import firestore

logger = logging.getLogger(__name__)

# ── System prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are Airi, a helpful AI assistant for an air quality monitoring app. "
    "You help users understand air quality data, health impacts of pollution, "
    "weather patterns, and provide personalized health recommendations. "
    "Always respond in the same language the user writes in. "
    "Be VERY concise — answer in 2-3 short sentences maximum. "
    "Never show your thinking process, never use bullet points unless asked. "
    "Go straight to the answer."
)


def _get_user_profile(user_uid: str) -> dict | None:
    """Fetch user profile from Firestore by uid."""
    try:
        db  = firestore.client()
        doc = db.collection("users").document(user_uid).get()
        
        logger.info(f"_get_user_profile: querying user_uid='{user_uid}'")
        
        if doc.exists:
            data = doc.to_dict()
            logger.info(f"_get_user_profile: found user with {len(data)} fields")
            return data
        
        logger.warning(f"_get_user_profile: document not found for user_uid='{user_uid}'")
        return None
        
    except Exception as e:
        logger.error(f"_get_user_profile: ERROR - {type(e).__name__}: {e}", exc_info=True)
        return None


def _build_system_prompt(user_uid: str) -> str:
    profile = _get_user_profile(user_uid)

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
        """.strip()

    return SYSTEM_PROMPT + "\n\n" + user_context


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _parse_body(request):
    """Return parsed JSON body or raise ValueError."""
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("Invalid JSON body")


def _get_session(chat_id: str) -> ChatSession:
    """Fetch a ChatSession by id or raise LookupError."""
    try:
        session = ChatSession.collection.get(chat_id)
    except Exception:
        session = None
    if session is None:
        raise LookupError("Session not found")
    return session


def _load_history(chat_id: str) -> list[Message]:
    """Return all messages of a session sorted by created_at (oldest first)."""
    raw = Message.collection.filter("chat_id", "==", chat_id).fetch()
    return sorted(raw, key=lambda m: m.created_at or "")


# ══════════════════════════════════════════════════════════════════════════════
#  SESSION VIEWS
# ══════════════════════════════════════════════════════════════════════════════

@csrf_exempt
def create_session(request):
    """
    POST /api/chat/sessions/
    Body: { "user_uid": "abc123", "title": "Optional title" }

    Creates a new chat session and returns its chat_id.
    """
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
        logger.info(f"create_session: new session {session.id} for user {user_uid}")
        return JsonResponse({"status": "success", "data": session.to_dict()}, status=201)
    except Exception as e:
        logger.error(f"create_session: {e}")
        return JsonResponse({"status": "error", "error": str(e)}, status=500)


@csrf_exempt
def list_sessions(request, user_uid: str):
    """
    GET /api/chat/users/<user_uid>/sessions/

    Returns all chat sessions for the given user, newest first.
    Each session includes its chat_id which is used to access messages.
    """
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
    """
    DELETE /api/chat/sessions/<chat_id>/

    Deletes the session and ALL messages belonging to it.
    """
    if request.method != "DELETE":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)

    try:
        session = _get_session(chat_id)
    except LookupError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=404)

    try:
        # Delete all messages first
        msgs = Message.collection.filter("chat_id", "==", chat_id).fetch()
        deleted_msgs = 0
        for msg in msgs:
            msg.delete()
            deleted_msgs += 1

        session.delete()
        logger.info(f"delete_session: removed session {chat_id} + {deleted_msgs} messages")
        return JsonResponse(
            {"status": "success", "message": f"Session and {deleted_msgs} message(s) deleted"},
            status=200,
        )
    except Exception as e:
        logger.error(f"delete_session: {e}")
        return JsonResponse({"status": "error", "error": str(e)}, status=500)


@csrf_exempt
def rename_session(request, chat_id: str):
    """
    PATCH /api/chat/sessions/<chat_id>/title/
    Body: { "title": "New title" }
    """
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
    """
    GET /api/chat/sessions/<chat_id>/messages/

    Returns the full message history for a chat session.
    Messages are sorted oldest → newest (chronological order).
    Each message has role='user' or role='assistant'.
    """
    if request.method != "GET":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)

    # Verify session exists
    try:
        _get_session(chat_id)
    except LookupError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=404)

    try:
        history  = _load_history(chat_id)
        messages = [m.to_dict() for m in history]
        return JsonResponse({"status": "success", "chat_id": chat_id, "data": messages}, status=200)
    except Exception as e:
        logger.error(f"get_messages: {e}")
        return JsonResponse({"status": "error", "error": str(e)}, status=500)


@csrf_exempt
def send_message(request, chat_id: str):
    """
    POST /api/chat/sessions/<chat_id>/send/
    Body: { "message": "What is the AQI today?" }

    Flow:
      1. Validate session exists.
      2. Load existing message history (for multi-turn context).
      3. Save the user's message to DB.
      4. Call the Gemma AI with full history + new message.
      5. Save the AI reply to DB.
      6. Auto-title the session on first message.
      7. Return both messages.
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

    # ── 1. Verify session ──────────────────────────────────────────────────
    try:
        session = _get_session(chat_id)
    except LookupError as e:
        return JsonResponse({"status": "error", "error": str(e)}, status=404)

    # ── 2. Load history ────────────────────────────────────────────────────
    history = _load_history(chat_id)

    # ── 3. Build personalized prompt ──────────────────────────────────────
    system_prompt = _build_system_prompt(session.user_uid)  # ← добавь эту строку

    # ── 3. Save user message ───────────────────────────────────────────────
    user_msg = Message(
        chat_id=chat_id,
        user_uid=session.user_uid,
        role="user",
        content=user_text,
    )
    user_msg.save()
    logger.info(f"send_message: saved user msg {user_msg.id} in chat {chat_id}")

    # ── 4. Build Gemma payload (full multi-turn history) ───────────────────
    contents = []
    for msg in history:
        api_role = "model" if msg.role == "assistant" else "user"
        contents.append({"role": api_role, "parts": [{"text": msg.content}]})
    # Append current user message
    contents.append({"role": "user", "parts": [{"text": user_text}]})

    ai_text = _call_gemma(contents, system_prompt)

    # ── 5. Save AI reply ───────────────────────────────────────────────────
    ai_msg = Message(
        chat_id=chat_id,
        user_uid=session.user_uid,
        role="assistant",
        content=ai_text,
    )
    ai_msg.save()
    logger.info(f"send_message: saved AI msg {ai_msg.id} in chat {chat_id}")

    # ── 6. Auto-title on first message, update timestamp ──────────────────
    if session.title == "New Chat" and not history:
        session.title = user_text[:60] + ("…" if len(user_text) > 60 else "")

    session.updated_at = timezone.now()
    try:
        session.update()
    except Exception as e:
        logger.warning(f"send_message — session.update() failed: {e}")

    # ── 7. Return both saved messages ──────────────────────────────────────
    return JsonResponse(
        {
            "status": "success",
            "chat_id": chat_id,
            "data": {
                "user_message":  user_msg.to_dict(),
                "ai_message":    ai_msg.to_dict(),
                "session_title": session.title,
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
    
    logger.info(f"_call_gemma: using system_prompt with {len(system_prompt)} chars")
    
    # Prepend system prompt as first user message to ensure context is always included
    enriched_contents = [
        {"role": "user", "parts": [{"text": system_prompt}]},
        {"role": "model", "parts": [{"text": "Understood. I will personalize my responses based on the profile information provided."}]},
    ] + contents
    
    payload = {
        "contents": enriched_contents,
        "generationConfig": {
            "maxOutputTokens": 500,  
            "temperature": 0.7,
        },
    }

    def _extract_text(resp_json: dict) -> str:
        try:
            parts = resp_json["candidates"][0]["content"]["parts"]

            # Собираем весь текст из всех частей
            full_text = ""
            for part in parts:
                if not part.get("thought", False) and part.get("text", "").strip():
                    full_text += part["text"].strip()

            if not full_text:
                return "Извините, не удалось получить ответ."

            # Модель пишет финальный ответ в самом конце после всех размышлений
            # Берём последний непустой абзац
            paragraphs = [p.strip() for p in full_text.split("\n") if p.strip()]
            
            # Пропускаем строки с маркерами размышлений (* - •)
            clean_lines = [
                line for line in paragraphs
                if not line.startswith(("*", "-", "•", "#"))
            ]

            if clean_lines:
                return clean_lines[-1]  # последний чистый абзац = финальный ответ

            return paragraphs[-1]  # fallback — просто последняя строка

        except (KeyError, IndexError) as e:
            logger.error(f"_call_gemma: unexpected response format: {resp_json}")
            return "Извините, не удалось получить ответ."

    try:
        logger.info(f"_call_gemma: sending request with enriched context")
        response = requests.post(
            url,
            params={"key": settings.GEMMA4_API_KEY},
            json=payload,
            timeout=(10, 60),
        )
        response.raise_for_status()
        logger.info(f"_call_gemma: got response, extracting text")
        result = _extract_text(response.json())
        logger.info(f"_call_gemma: success, returning response")
        return result

    except requests.exceptions.Timeout:
        logger.error("_call_gemma: request timed out")
        return "Извините, запрос занял слишком много времени. Попробуйте ещё раз."

    except Exception as e:
        logger.error(f"_call_gemma failed ({type(e).__name__}): {e}")
        return "Извините, не удалось обработать запрос. Попробуйте ещё раз."