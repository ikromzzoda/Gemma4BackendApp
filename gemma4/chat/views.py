import json
import requests
import logging
from django.http import JsonResponse
from django.conf import settings
from django.utils import timezone
from .models import ChatSession, Message

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are Airi, a helpful AI assistant for an air quality monitoring app. "
    "You help users understand air quality data, health impacts of pollution, "
    "weather patterns, and provide personalized health recommendations. "
    "Be concise, friendly, and always prioritize user health and safety."
)


def _session_to_dict(session):
    return {
        "id": session.id,
        "user_uid": session.user_uid,
        "title": session.title,
        "created_at": str(session.created_at) if session.created_at else None,
        "updated_at": str(session.updated_at) if session.updated_at else None,
    }


def _message_to_dict(msg):
    return {
        "id": msg.id,
        "chat_id": msg.chat_id,
        "role": msg.role,
        "content": msg.content,
        "created_at": str(msg.created_at) if msg.created_at else None,
    }


def create_session(request):
    """POST /api/chat/sessions/create/ — Create a new chat session for a user."""
    if request.method != "POST":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"status": "error", "error": "Invalid JSON body"}, status=400)

    user_uid = body.get("user_uid", "").strip()
    title = body.get("title", "New Chat").strip() or "New Chat"

    if not user_uid:
        return JsonResponse({"status": "error", "error": "user_uid is required"}, status=400)

    try:
        session = ChatSession(user_uid=user_uid, title=title)
        session.save()
        return JsonResponse({"status": "success", "data": _session_to_dict(session)}, status=201)
    except Exception as e:
        logger.error(f"create_session: {e}")
        return JsonResponse({"status": "error", "error": str(e)}, status=500)


def list_sessions(request, user_uid):
    """GET /api/chat/users/<user_uid>/sessions/ — List all chat sessions for a user."""
    if request.method != "GET":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)

    try:
        raw = ChatSession.collection.filter("user_uid", "==", user_uid).fetch()
        sessions = [_session_to_dict(s) for s in raw]
        sessions.sort(key=lambda x: x["created_at"] or "", reverse=True)
        return JsonResponse({"status": "success", "data": sessions}, status=200)
    except Exception as e:
        logger.error(f"list_sessions: {e}")
        return JsonResponse({"status": "error", "error": str(e)}, status=500)


def get_messages(request, session_id):
    """GET /api/chat/sessions/<session_id>/messages/ — Get all messages in a session."""
    if request.method != "GET":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)

    try:
        raw = Message.collection.filter("chat_id", "==", session_id).fetch()
        messages = [_message_to_dict(m) for m in raw]
        messages.sort(key=lambda x: x["created_at"] or "")
        return JsonResponse({"status": "success", "data": messages}, status=200)
    except Exception as e:
        logger.error(f"get_messages: {e}")
        return JsonResponse({"status": "error", "error": str(e)}, status=500)


def send_message(request, session_id):
    """POST /api/chat/sessions/<session_id>/message/ — Send a message and get AI reply."""
    if request.method != "POST":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"status": "error", "error": "Invalid JSON body"}, status=400)

    user_text = body.get("message", "").strip()
    if not user_text:
        return JsonResponse({"status": "error", "error": "message is required"}, status=400)

    # Verify session exists
    try:
        session = ChatSession.collection.get(session_id)
    except Exception:
        session = None
    if session is None:
        return JsonResponse({"status": "error", "error": "Session not found"}, status=404)

    # Load existing chat history for context
    try:
        history_raw = Message.collection.filter("chat_id", "==", session_id).fetch()
        history = sorted(list(history_raw), key=lambda m: m.created_at or "")
    except Exception:
        history = []

    # Save user message immediately
    user_msg = Message(
        chat_id=session_id,
        user_uid=session.user_uid,
        role="user",
        content=user_text,
    )
    user_msg.save()

    # Build multi-turn conversation payload for Gemma4 API
    contents = []
    for msg in history:
        api_role = "model" if msg.role == "assistant" else "user"
        contents.append({"role": api_role, "parts": [{"text": msg.content}]})
    contents.append({"role": "user", "parts": [{"text": user_text}]})

    ai_text = _call_gemma(contents)

    # Save AI response
    ai_msg = Message(
        chat_id=session_id,
        user_uid=session.user_uid,
        role="assistant",
        content=ai_text,
    )
    ai_msg.save()

    # Auto-generate title from first user message
    if session.title == "New Chat" and not history:
        session.title = user_text[:60] + ("..." if len(user_text) > 60 else "")

    session.updated_at = timezone.now()
    try:
        session.update()
    except Exception as e:
        logger.warning(f"send_message — session update failed: {e}")

    return JsonResponse({
        "status": "success",
        "data": {
            "user_message": _message_to_dict(user_msg),
            "ai_message": _message_to_dict(ai_msg),
            "session_title": session.title,
        },
    }, status=200)


def delete_session(request, session_id):
    """DELETE /api/chat/sessions/<session_id>/delete/ — Delete a session and all its messages."""
    if request.method != "DELETE":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)

    try:
        session = ChatSession.collection.get(session_id)
    except Exception:
        session = None
    if session is None:
        return JsonResponse({"status": "error", "error": "Session not found"}, status=404)

    try:
        msgs = Message.collection.filter("chat_id", "==", session_id).fetch()
        for msg in msgs:
            msg.delete()
        session.delete()
        return JsonResponse({"status": "success", "message": "Session deleted"}, status=200)
    except Exception as e:
        logger.error(f"delete_session: {e}")
        return JsonResponse({"status": "error", "error": str(e)}, status=500)


def rename_session(request, session_id):
    """PATCH /api/chat/sessions/<session_id>/title/ — Rename a chat session."""
    if request.method != "PATCH":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"status": "error", "error": "Invalid JSON body"}, status=400)

    title = body.get("title", "").strip()
    if not title:
        return JsonResponse({"status": "error", "error": "title is required"}, status=400)

    try:
        session = ChatSession.collection.get(session_id)
    except Exception:
        session = None
    if session is None:
        return JsonResponse({"status": "error", "error": "Session not found"}, status=404)

    try:
        session.title = title
        session.updated_at = timezone.now()
        session.update()
        return JsonResponse({"status": "success", "data": _session_to_dict(session)}, status=200)
    except Exception as e:
        logger.error(f"rename_session: {e}")
        return JsonResponse({"status": "error", "error": str(e)}, status=500)


def _call_gemma(contents: list) -> str:
    """Call Gemma4 API with full multi-turn conversation history."""
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": 500,
            "temperature": 0.7,
        },
    }
    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMMA4_MODEL}:generateContent",
            params={"key": settings.GEMMA4_API_KEY},
            json=payload,
            timeout=(10, 60),
        )
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except requests.exceptions.ReadTimeout:
        logger.error("_call_gemma: TIMEOUT")
        return "Sorry, I'm taking too long to respond. Please try again."
    except Exception as e:
        logger.error(f"_call_gemma: {type(e).__name__}: {e}")
        # Retry without systemInstruction in case the model doesn't support it
        payload.pop("systemInstruction", None)
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMMA4_MODEL}:generateContent",
                params={"key": settings.GEMMA4_API_KEY},
                json=payload,
                timeout=(10, 60),
            )
            response.raise_for_status()
            return response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e2:
            logger.error(f"_call_gemma retry failed: {type(e2).__name__}: {e2}")
            return "Sorry, I couldn't process your request right now. Please try again."
