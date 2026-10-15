"""知识查询服务：BM25 与 Chroma 稠密召回通过 RRF 融合，再按父片段补充上下文。"""

from dataclasses import dataclass
import logging

from app.core.config import settings
from app.integrations.qwen import QwenGateway
from app.repositories.knowledge import KnowledgeRepository
from app.retrieval.hybrid import reciprocal_rank_fusion
from app.retrieval.lexical import SearchDocument, rank_bm25
from app.retrieval.vector import ChromaVectorSearch


logger = logging.getLogger(__name__)

BM25_CANDIDATE_LIMIT = 20
VECTOR_CANDIDATE_LIMIT = 20
FUSED_CHILD_LIMIT = 10
PARENT_CONTEXT_LIMIT = 4
RRF_CONSTANT = 60


@dataclass(frozen=True)
class KnowledgeEvidence:
    title: str
    version: str
    uri: str
    content: str
    parent_chunk_id: str
    matched_child_ids: tuple[str, ...]
    rrf_score: float


class KnowledgeService:
    def __init__(self, knowledge: KnowledgeRepository):
        self.knowledge = knowledge
        self.embedding = QwenGateway(settings)
        self.vector_search = ChromaVectorSearch(settings)

    def search(self, query: str) -> list[KnowledgeEvidence]:
        """先按子片段做混合检索，再取父片段构造去重后的上下文。"""

        query = query.strip()
        if not query:
            return []

        # BM25 直接检索 PostgreSQL 中有效子片段，标题路径也拼入文本以保留章节语义。
        child_rows = self.knowledge.list_active_child_chunks()
        lexical_documents = [
            SearchDocument(
                document_id=chunk.chunk_id,
                title=" / ".join(chunk.title_path) or document.title,
                content=chunk.embedding_text or chunk.content,
                source_uri=chunk.source_uri,
                version=document.version,
            )
            for chunk, document in child_rows
        ]
        bm25_results = rank_bm25(
            query,
            lexical_documents,
            limit=BM25_CANDIDATE_LIMIT,
        )

        # 向量服务或 Embedding API 暂时不可用时保留 BM25 结果，保证 FAQ 仍能降级工作。
        vector_ids: list[str] = []
        if settings.llm_enabled and child_rows:
            try:
                query_vector = self.embedding.embed_query(query)
                vector_ids = self.vector_search.search(
                    query_vector,
                    limit=VECTOR_CANDIDATE_LIMIT,
                )
            except Exception:
                logger.exception("RAG 稠密向量召回失败，本次请求降级为 BM25 关键词召回")

        fused = reciprocal_rank_fusion(
            bm25_results,
            vector_ids,
            limit=FUSED_CHILD_LIMIT,
            constant=RRF_CONSTANT,
        )
        if not fused:
            return []

        # 融合列表里的 ID 是子片段 ID；以 PostgreSQL 为准找回片段与父片段。
        active_children = self.knowledge.active_child_chunks_by_ids(
            [item.chunk_id for item in fused]
        )
        selected = [
            (fused_item, active_children[fused_item.chunk_id][0], active_children[fused_item.chunk_id][1])
            for fused_item in fused
            if fused_item.chunk_id in active_children
        ]
        parent_ids = list(
            dict.fromkeys(
                child.parent_chunk_id
                for _, child, _ in selected
                if child.parent_chunk_id is not None
            )
        )
        parents = self.knowledge.active_parent_chunks_by_ids(parent_ids)

        # 多个高分 child 可能来自同一父片段；上下文中只放一次，按最高融合排名排序。
        evidence_by_parent: dict[str, KnowledgeEvidence] = {}
        child_ids_by_parent: dict[str, list[str]] = {}
        for fused_item, child, document in selected:
            parent_id = child.parent_chunk_id or child.chunk_id
            if parent_id not in parents:
                # 对历史异常数据做安全回退：没有父片段时只把命中的子片段送入上下文。
                parent = child
                source_document = document
                parent_id = child.chunk_id
            else:
                parent, source_document = parents[parent_id]

            child_ids_by_parent.setdefault(parent_id, []).append(child.chunk_id)
            if parent_id in evidence_by_parent:
                previous = evidence_by_parent[parent_id]
                evidence_by_parent[parent_id] = KnowledgeEvidence(
                    title=previous.title,
                    version=previous.version,
                    uri=previous.uri,
                    content=previous.content,
                    parent_chunk_id=previous.parent_chunk_id,
                    matched_child_ids=tuple(child_ids_by_parent[parent_id]),
                    rrf_score=previous.rrf_score + fused_item.score,
                )
                continue

            title = " / ".join(parent.title_path) or source_document.title
            uri = parent.source_uri + (parent.source_anchor or "")
            evidence_by_parent[parent_id] = KnowledgeEvidence(
                title=title,
                version=source_document.version,
                uri=uri,
                content=parent.content,
                parent_chunk_id=parent_id,
                matched_child_ids=(child.chunk_id,),
                rrf_score=fused_item.score,
            )

        return list(evidence_by_parent.values())[:PARENT_CONTEXT_LIMIT]

