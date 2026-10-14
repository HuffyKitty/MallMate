"""聊天接口：校验会话归属、执行 Agent、保存本轮消息。"""

from fastapi import APIRouter, Depends

from app.agent.graph import agent_graph
from app.agent.state import AgentContext
from app.api.dependencies import (
    get_conversation_service,
    get_current_customer,
    get_current_principal,
    get_knowledge_service,
    get_order_service,
)
from app.core.security import Principal
from app.models import Customer
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.conversations import ConversationService
from app.services.knowledge import KnowledgeService
from app.services.orders import OrderService


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    customer: Customer = Depends(get_current_customer),
    principal: Principal = Depends(get_current_principal),
    conversations: ConversationService = Depends(get_conversation_service),
    orders: OrderService = Depends(get_order_service),
    knowledge: KnowledgeService = Depends(get_knowledge_service),
) -> dict:
    conversation = conversations.get_or_create(customer.id, request.conversation_id)

    # State 保存任务数据；Context 注入本次请求可用的业务服务。
    result = agent_graph.invoke(
        {"message": request.message},
        context=AgentContext(principal=principal, orders=orders, knowledge=knowledge),
    )
    conversations.save_exchange(conversation.id, request.message, result["answer"])
    return {
        "conversation_id": conversation.id,
        "intent": result["intent"],
        "urgency": result["urgency"],
        "confidence": result["confidence"],
        "answer": result["answer"],
        "sources": result.get("sources", []),
    }

