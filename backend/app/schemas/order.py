"""订单和物流接口的响应模型。"""

from datetime import datetime

from app.core.enums import OrderStatus, ShipmentStatus
from app.schemas.common import APIModel


class OrderItemResponse(APIModel):
    sku: str
    name: str
    quantity: int


class OrderResponse(APIModel):
    id: int
    status: OrderStatus
    items: list[OrderItemResponse]


class LogisticsResponse(APIModel):
    order_id: int
    status: ShipmentStatus
    updated_at: datetime | None

