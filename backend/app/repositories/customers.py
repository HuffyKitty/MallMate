"""客户数据访问。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer


class CustomerRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_demo_handle(self, handle: str) -> Customer | None:
        return self.db.scalar(select(Customer).where(Customer.demo_handle == handle))

