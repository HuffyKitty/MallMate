"""订单和物流查询服务。"""

from app.core.enums import ShipmentStatus
from app.core.exceptions import ResourceNotFoundError
from app.models import Order
from app.repositories.orders import OrderRepository


class OrderService:
    def __init__(self, orders: OrderRepository):
        self.orders = orders

    def get_owned_order(self, customer_id: int, order_id: int) -> Order:
        """只返回属于当前用户的订单，越权与不存在统一表现为未找到。"""

        order = self.orders.get_owned(customer_id, order_id)
        if order is None:
            raise ResourceNotFoundError("订单不存在")
        return order

    def get_order_data(self, customer_id: int, order_id: int) -> dict:
        order = self.get_owned_order(customer_id, order_id)
        return {
            "id": order.id,
            "status": order.status,
            "items": [
                {
                    "sku": item.product.sku,
                    "name": item.product.name,
                    "quantity": item.quantity,
                }
                for item in order.items
            ],
        }

    def get_logistics_data(self, customer_id: int, order_id: int) -> dict:
        # 即使只查物流也必须先校验订单归属，不能直接按 order_id 查 Shipment。
        self.get_owned_order(customer_id, order_id)
        shipment = self.orders.get_shipment(order_id)
        if shipment is None:
            return {
                "order_id": order_id,
                "status": ShipmentStatus.NOT_SHIPPED,
                "updated_at": None,
            }
        return {
            "order_id": order_id,
            "status": shipment.status,
            "updated_at": shipment.updated_at,
        }

