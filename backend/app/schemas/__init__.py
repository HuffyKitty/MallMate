"""对外 API 数据契约。

路由只能使用这里的模型接收和返回数据，避免直接暴露 ORM 对象。
"""

from app.schemas.after_sales import (
    AfterSalesCaseResponse,
    CasePreviewResponse,
    CaseRequest,
    ConfirmRequest,
)
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.order import LogisticsResponse, OrderItemResponse, OrderResponse

__all__ = [
    "AfterSalesCaseResponse",
    "CasePreviewResponse",
    "CaseRequest",
    "ChatRequest",
    "ChatResponse",
    "ConfirmRequest",
    "LogisticsResponse",
    "OrderItemResponse",
    "OrderResponse",
]

