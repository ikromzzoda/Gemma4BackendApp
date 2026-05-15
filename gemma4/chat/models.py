from fireo import models


class ChatSession(models.Model):
    user_uid = models.TextField(required=True)
    title = models.TextField(required=False, default="New Chat")
    created_at = models.DateTime(auto=True)
    updated_at = models.DateTime(required=False)

    class Meta:
        collection_name = "chat_sessions"


class Message(models.Model):
    chat_id = models.TextField(required=True)
    user_uid = models.TextField(required=True)
    role = models.TextField(required=True)     # 'user' or 'assistant'
    content = models.TextField(required=True)
    created_at = models.DateTime(auto=True)

    class Meta:
        collection_name = "chat_messages"
