from django.urls import path
from . import views

urlpatterns = [
    # Create a new chat session
    path("chat/sessions/create/", views.create_session, name="chat_create_session"),

    # List all sessions for a user
    path("chat/users/<str:user_uid>/sessions/", views.list_sessions, name="chat_list_sessions"),

    # Get all messages in a session
    path("chat/sessions/<str:session_id>/messages/", views.get_messages, name="chat_get_messages"),

    # Send a message and get AI reply
    path("chat/sessions/<str:session_id>/message/", views.send_message, name="chat_send_message"),

    # Delete a session and its messages
    path("chat/sessions/<str:session_id>/delete/", views.delete_session, name="chat_delete_session"),

    # Rename a session
    path("chat/sessions/<str:session_id>/title/", views.rename_session, name="chat_rename_session"),
]
