"""知识文档数据访问。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeChunk, KnowledgeDocument


class KnowledgeRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_active(self) -> list[KnowledgeDocument]:
        return list(
            self.db.scalars(
                select(KnowledgeDocument).where(KnowledgeDocument.status == "active")
            ).all()
        )

    def list_active_child_chunks(self) -> list[tuple[KnowledgeChunk, KnowledgeDocument]]:
        """取出 BM25 所需的有效子片段，并同时载入它所属文档的标题和版本。"""

        rows = self.db.execute(
            select(KnowledgeChunk, KnowledgeDocument)
            .join(
                KnowledgeDocument,
                KnowledgeDocument.document_id == KnowledgeChunk.document_id,
            )
            .where(
                KnowledgeDocument.status == "active",
                KnowledgeChunk.level == "child",
            )
        )
        return list(rows.all())

    def active_child_chunks_by_ids(
        self, chunk_ids: list[str]
    ) -> dict[str, tuple[KnowledgeChunk, KnowledgeDocument]]:
        """按 Chroma/BM25 返回的稳定 chunk_id 取回数据库中的可信片段记录。"""

        if not chunk_ids:
            return {}
        rows = self.db.execute(
            select(KnowledgeChunk, KnowledgeDocument)
            .join(
                KnowledgeDocument,
                KnowledgeDocument.document_id == KnowledgeChunk.document_id,
            )
            .where(
                KnowledgeDocument.status == "active",
                KnowledgeChunk.level == "child",
                KnowledgeChunk.chunk_id.in_(chunk_ids),
            )
        )
        return {chunk.chunk_id: (chunk, document) for chunk, document in rows.all()}

    def active_parent_chunks_by_ids(
        self, chunk_ids: list[str]
    ) -> dict[str, tuple[KnowledgeChunk, KnowledgeDocument]]:
        """按子片段的 parent_chunk_id 批量加载父片段，避免逐条查询数据库。"""

        if not chunk_ids:
            return {}
        rows = self.db.execute(
            select(KnowledgeChunk, KnowledgeDocument)
            .join(
                KnowledgeDocument,
                KnowledgeDocument.document_id == KnowledgeChunk.document_id,
            )
            .where(
                KnowledgeDocument.status == "active",
                KnowledgeChunk.level == "parent",
                KnowledgeChunk.chunk_id.in_(chunk_ids),
            )
        )
        return {chunk.chunk_id: (chunk, document) for chunk, document in rows.all()}

