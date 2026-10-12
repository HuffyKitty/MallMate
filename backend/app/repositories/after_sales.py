"""售后申请数据访问。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AfterSalesCase


class AfterSalesRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_idempotency_key(
        self, customer_id: int, idempotency_key: str
    ) -> AfterSalesCase | None:
        return self.db.scalar(
            select(AfterSalesCase).where(
                AfterSalesCase.customer_id == customer_id,
                AfterSalesCase.idempotency_key == idempotency_key,
            )
        )

    def get_owned(self, customer_id: int, case_id: int) -> AfterSalesCase | None:
        return self.db.scalar(
            select(AfterSalesCase).where(
                AfterSalesCase.id == case_id,
                AfterSalesCase.customer_id == customer_id,
            )
        )

    def add(self, case: AfterSalesCase) -> None:
        self.db.add(case)

