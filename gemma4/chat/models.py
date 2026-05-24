from fireo import models


class ChatSession(models.Model):
    """
    Represents a single chat conversation.

    Firestore structure:
        chat_sessions/
            {sessionId}/
                ├── user_uid
                ├── title
                ├── created_at
                ├── updated_at
                └── messages/          ← subcollection
                      {messageId}/
                          ├── role       ('user' | 'assistant')
                          ├── content
                          └── created_at
    """
    user_uid   = models.TextField(required=True)
    title      = models.TextField(required=False, default="New Chat")
    created_at = models.DateTime(auto=True)
    updated_at = models.DateTime(required=False)

    class Meta:
        collection_name = "chat_sessions"

    def to_dict(self):
        return {
            "chat_id":    self.id,
            "user_uid":   self.user_uid,
            "title":      self.title,
            "created_at": str(self.created_at) if self.created_at else None,
            "updated_at": str(self.updated_at) if self.updated_at else None,
        }


# NOTE: Message is no longer a top-level Firestore collection.
# Messages live as a subcollection inside each ChatSession document:
#   chat_sessions/{chat_id}/messages/{message_id}
#
# All message read/write operations are handled via the Firestore client
# directly in views.py using _msg_col(chat_id) helper, which returns the
# subcollection reference. This avoids cross-collection queries and makes
# every session self-contained — one document tree per conversation.
