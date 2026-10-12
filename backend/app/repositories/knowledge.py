"""知识文档数据访问。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeDocument


class KnowledgeRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_active(self) -> list[KnowledgeDocument]:
        return list(
            self.db.scalars(
                select(KnowledgeDocument).where(KnowledgeDocument.status == "active")
            ).all()
        )

