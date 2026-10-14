"""客户数据访问。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer


class CustomerRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_demo_handle(self, handle: str) -> Customer | None:
        return self.db.scalar(select(Customer).where(Customer.demo_handle == handle))

    def get_by_id(self, customer_id: int) -> Customer | None:
        """按认证结果中的顾客 ID 读取资料，不接受客户端声明的归属。"""

        return self.db.get(Customer, customer_id)

