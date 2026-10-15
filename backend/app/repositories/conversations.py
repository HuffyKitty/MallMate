"""会话和消息数据访问。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation, Message


class ConversationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, conversation_id: str) -> Conversation | None:
        return self.db.get(Conversation, conversation_id)

    def add(self, conversation: Conversation) -> None:
        self.db.add(conversation)

    def list_recent_messages(
        self,
        customer_id: int,
        conversation_id: str,
        limit: int = 10,
    ) -> list[Message]:
        """读取指定用户在指定会话中的最近消息，并按时间正序返回。

        同时过滤 customer_id 和 conversation_id：即使调用方误传了他人的会话 ID，
        查询本身也不会返回对方的聊天内容。
        """

        statement = (
            select(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Message.conversation_id == conversation_id,
                Conversation.customer_id == customer_id,
            )
            .order_by(Message.id.desc())
            .limit(limit)
        )
        # 先倒序取最近记录，再反转为模型阅读时自然的时间顺序。
        recent_messages = list(self.db.scalars(statement).all())
        return list(reversed(recent_messages))

    def add_exchange(self, conversation_id: str, user_text: str, assistant_text: str) -> None:
        self.db.add_all(
            [
                Message(conversation_id=conversation_id, role="user", content=user_text),
                Message(conversation_id=conversation_id, role="assistant", content=assistant_text),
            ]
        )

