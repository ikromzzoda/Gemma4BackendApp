from django.urls import path
from . import views

urlpatterns = [
    # ── Session management ────────────────────────────────────────────────────
    # POST   /api/chat/sessions/                      → create new chat session
    path("chat/sessions/", views.create_session, name="chat_create_session"),

    # GET    /api/chat/users/<user_uid>/sessions/     → list all user's sessions
    path("chat/users/<str:user_uid>/sessions/", views.list_sessions, name="chat_list_sessions"),

    # DELETE /api/chat/sessions/<chat_id>/            → delete session + messages
    path("chat/sessions/<str:chat_id>/delete", views.delete_session, name="chat_delete_session"),

    # PATCH  /api/chat/sessions/<chat_id>/title/      → rename session title
    path("chat/sessions/<str:chat_id>/title/", views.rename_session, name="chat_rename_session"),

    # ── Message management ────────────────────────────────────────────────────
    # GET    /api/chat/sessions/<chat_id>/messages/   → fetch full chat history
    path("chat/sessions/<str:chat_id>/messages/", views.get_messages, name="chat_get_messages"),

    # POST   /api/chat/sessions/<chat_id>/messages/   → send message, get AI reply
    path("chat/sessions/<str:chat_id>/send/", views.send_message, name="chat_send_message"),
]
