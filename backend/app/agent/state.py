"""LangGraph 的可持久状态与单次运行依赖。

State 只保存能够描述任务进展的数据；数据库服务放在 Context 中，避免把不可序列化的
Session 写进状态。未来接入 checkpointer 时，这个边界非常重要。
"""

from dataclasses import dataclass
from typing import TypedDict

from app.core.enums import Intent, Urgency
from app.core.security import Principal
from app.services.knowledge import KnowledgeService
from app.services.orders import OrderService


class AgentState(TypedDict, total=False):
    message: str
    intent: Intent
    urgency: Urgency
    confidence: float
    matched_keywords: list[str]
    answer: str
    sources: list[dict[str, str]]


@dataclass(frozen=True)
class AgentContext:
    """只在本次 invoke 中使用的可信身份和服务，不会被保存成会话状态。"""

    principal: Principal
    orders: OrderService
    knowledge: KnowledgeService

