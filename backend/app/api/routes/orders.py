"""订单与物流只读接口。"""

from fastapi import APIRouter, Depends, Path

from app.api.dependencies import current_customer, get_order_service
from app.models import Customer
from app.schemas.order import LogisticsResponse, OrderResponse
from app.services.orders import OrderService


router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int = Path(gt=0),
    customer: Customer = Depends(current_customer),
    orders: OrderService = Depends(get_order_service),
) -> dict:
    return orders.get_order_data(customer.id, order_id)


@router.get("/{order_id}/logistics", response_model=LogisticsResponse)
def get_logistics(
    order_id: int = Path(gt=0),
    customer: Customer = Depends(current_customer),
    orders: OrderService = Depends(get_order_service),
) -> dict:
    return orders.get_logistics_data(customer.id, order_id)

