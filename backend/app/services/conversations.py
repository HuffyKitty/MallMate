"""会话归属和消息持久化服务。"""

from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError
from app.models import Conversation
from app.repositories.conversations import ConversationRepository


class ConversationService:
    def __init__(self, db: Session, conversations: ConversationRepository):
        self.db = db
        self.conversations = conversations

    def get_or_create(self, customer_id: int, requested_id: str | None) -> Conversation:
        """创建新会话，或确认已有会话确实属于当前用户。"""

        if requested_id is None:
            conversation = Conversation(id=str(uuid4()), customer_id=customer_id)
            self.conversations.add(conversation)
            return conversation

        conversation = self.conversations.get(requested_id)
        if conversation is None or conversation.customer_id != customer_id:
            # 不区分“不存在”和“属于他人”，避免泄露其他用户的会话信息。
            raise ResourceNotFoundError("会话不存在")
        return conversation

    def save_exchange(self, conversation_id: str, user_text: str, assistant_text: str) -> None:
        self.conversations.add_exchange(conversation_id, user_text, assistant_text)
        self.db.commit()

