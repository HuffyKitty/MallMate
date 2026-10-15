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

    def get_recent_history(
        self,
        customer_id: int,
        conversation_id: str,
        rounds: int = 5,
    ) -> list[dict[str, str]]:
        """读取最近若干轮干净对话，过滤掉旧版 FAQ 原文转储。

        读取范围多于最终上下文轮数，以便跳过旧版 FAQ 直接返回的整段知识文档。
        只保留完整的 user/assistant 对话轮次，避免给模型传入角色错位的历史。
        """

        messages = self.conversations.list_recent_messages(
            customer_id=customer_id,
            conversation_id=conversation_id,
            # 最多回看 25 轮，通常足以在过滤旧版文档回复后仍凑齐 5 轮上下文。
            limit=max(rounds * 10, 50),
        )

        clean_turns: list[list[dict[str, str]]] = []
        pending_user_message: dict[str, str] | None = None
        for message in messages:
            if message.role == "user":
                pending_user_message = {
                    "role": "user",
                    "content": message.content,
                }
            elif message.role == "assistant" and pending_user_message is not None:
                assistant_message = {
                    "role": "assistant",
                    "content": message.content,
                }
                # 旧版 FAQ 会把知识父片段以“【标题｜版本】”开头原样保存。
                # 这类长文不是自然对话，不能再作为模型的历史回答引用。
                is_raw_knowledge_dump = (
                    assistant_message["content"].lstrip().startswith("【")
                    and "｜版本 " in assistant_message["content"][:300]
                )
                if is_raw_knowledge_dump:
                    # 保留本轮用户问题以帮助理解后续指代，但不把旧版检索原文交给模型。
                    assistant_message["content"] = (
                        "上一轮已检索过售后资料；本轮回答必须重新依据当前检索到的资料。"
                    )
                clean_turns.append([pending_user_message, assistant_message])
                pending_user_message = None
            else:
                # 遇到不认识的角色时丢弃未配对用户消息，避免生成残缺对话轮次。
                pending_user_message = None

        return [message for turn in clean_turns[-rounds:] for message in turn]

    def save_exchange(self, conversation_id: str, user_text: str, assistant_text: str) -> None:
        self.conversations.add_exchange(conversation_id, user_text, assistant_text)
        self.db.commit()

