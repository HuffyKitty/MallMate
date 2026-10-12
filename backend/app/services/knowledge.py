"""知识查询服务：当前使用 BM25 基线，后续与 ChromaDB 向量召回做 RRF 融合。"""

from dataclasses import dataclass

from app.repositories.knowledge import KnowledgeRepository
from app.retrieval.lexical import SearchDocument, rank_bm25


@dataclass(frozen=True)
class KnowledgeEvidence:
    title: str
    version: str
    uri: str
    content: str


class KnowledgeService:
    def __init__(self, knowledge: KnowledgeRepository):
        self.knowledge = knowledge

    def search(self, query: str) -> KnowledgeEvidence | None:
        documents = self.knowledge.list_active()
        ranked = rank_bm25(
            query,
            [
                SearchDocument(
                    document_id=document.document_id,
                    title=document.title,
                    content=document.content,
                    source_uri=document.source_uri,
                    version=document.version,
                )
                for document in documents
            ],
            limit=1,
        )
        if not ranked:
            return None

        best = ranked[0].document
        return KnowledgeEvidence(
            title=best.title,
            version=best.version,
            uri=best.source_uri,
            content=best.content,
        )

