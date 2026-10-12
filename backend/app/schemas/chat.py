"""聊天接口的请求和响应模型。"""

from pydantic import Field

from app.core.enums import Intent, Urgency
from app.schemas.common import APIModel, SourceResponse


class ChatRequest(APIModel):
    message: str = Field(min_length=1, max_length=2000, description="用户本轮消息")
    conversation_id: str | None = Field(default=None, description="继续已有会话时传入")


class ChatResponse(APIModel):
    conversation_id: str
    intent: Intent
    urgency: Urgency
    confidence: float = Field(ge=0, le=1)
    answer: str
    sources: list[SourceResponse] = Field(default_factory=list)

