"""会话和消息数据访问。"""

from sqlalchemy.orm import Session

from app.models import Conversation, Message


class ConversationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, conversation_id: str) -> Conversation | None:
        return self.db.get(Conversation, conversation_id)

    def add(self, conversation: Conversation) -> None:
        self.db.add(conversation)

    def add_exchange(self, conversation_id: str, user_text: str, assistant_text: str) -> None:
        self.db.add_all(
            [
                Message(conversation_id=conversation_id, role="user", content=user_text),
                Message(conversation_id=conversation_id, role="assistant", content=assistant_text),
            ]
        )

