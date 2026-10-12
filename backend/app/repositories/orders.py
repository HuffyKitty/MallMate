"""订单、商品项和物流数据访问。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, Shipment


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_owned(self, customer_id: int, order_id: int) -> Order | None:
        # 把用户条件放进同一条 SQL，避免先查订单再在应用层判断归属。
        return self.db.scalar(
            select(Order).where(Order.id == order_id, Order.customer_id == customer_id)
        )

    def get_shipment(self, order_id: int) -> Shipment | None:
        return self.db.scalar(select(Shipment).where(Shipment.order_id == order_id))

