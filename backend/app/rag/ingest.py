"""把离线父子切片向量化，并分别写入 PostgreSQL 与 ChromaDB。

PostgreSQL 保存原文、父子片段和来源信息；ChromaDB 保存子片段向量及检索所需元数据。
脚本可以重复运行：相同 chunk_id 会更新而不是不断新增重复记录。
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import chromadb
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.integrations.qwen import QwenGateway
from app.models import KnowledgeChunk, KnowledgeDocument
from app.rag.offline_slicer import DEFAULT_OUTPUT, PROJECT_ROOT, _split_frontmatter


EMBEDDING_BATCH_SIZE = 10


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """逐行读取切片文件，并在任何外部写入前验证基本字段。"""

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL 第 {line_number} 行格式错误: {exc}") from exc
            required = {"chunk_id", "document_id", "level", "content", "source_uri"}
            missing = required - row.keys()
            if missing:
                raise ValueError(f"JSONL 第 {line_number} 行缺少字段: {sorted(missing)}")
            rows.append(row)
    if not rows:
        raise ValueError(f"切片文件为空: {path}")
    return rows


def _embed_children(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """仅向量化 child；按小批次调用 API，减少单次请求失败影响范围。"""

    children = [row for row in rows if row["level"] == "child"]
    if not children:
        raise ValueError("切片中没有 child 子片段，无法建立检索向量")

    gateway = QwenGateway(settings)
    vectors: list[list[float]] = []
    for offset in range(0, len(children), EMBEDDING_BATCH_SIZE):
        batch = children[offset : offset + EMBEDDING_BATCH_SIZE]
        texts = [row.get("embedding_text") or row["content"] for row in batch]
        batch_vectors = gateway.embed_documents(texts)
        if len(batch_vectors) != len(batch):
            raise RuntimeError("Embedding API 返回向量数量与输入片段数量不一致")
        vectors.extend(batch_vectors)

    dimensions = len(vectors[0])
    if not dimensions or any(len(vector) != dimensions for vector in vectors):
        raise RuntimeError("Embedding API 返回的向量维度为空或不一致")
    for row, vector in zip(children, vectors, strict=True):
        row["_embedding"] = vector
    return children, dimensions


def _load_document_content(row: dict[str, Any]) -> str:
    """从仓库里的 Markdown 原文读取全文，数据库不会只存被切碎的片段。"""

    source = (PROJECT_ROOT / row["source_uri"]).resolve()
    if not source.is_relative_to(PROJECT_ROOT.resolve()) or not source.is_file():
        raise FileNotFoundError(f"找不到知识原文: {row['source_uri']}")
    return source.read_text(encoding="utf-8")


def _upsert_postgres(rows: list[dict[str, Any]], indexed_ids: set[str]) -> None:
    """将文档原文和父子片段写进 PostgreSQL；chunk_id 作为稳定幂等键。"""

    by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_document[row["document_id"]].append(row)

    with SessionLocal() as session:
        for document_id, document_rows in by_document.items():
            representative = document_rows[0]
            incoming_ids = {row["chunk_id"] for row in document_rows}
            existing_ids = set(
                session.scalars(
                    select(KnowledgeChunk.chunk_id).where(
                        KnowledgeChunk.document_id == document_id
                    )
                )
            )
            stale_ids = existing_ids - incoming_ids
            if stale_ids:
                # 删除切片策略更新后已废弃的旧片段；自外键级联会一并清理其旧子片段。
                session.execute(
                    delete(KnowledgeChunk).where(KnowledgeChunk.chunk_id.in_(stale_ids))
                )

            existing_document = session.scalar(
                select(KnowledgeDocument).where(KnowledgeDocument.document_id == document_id)
            )
            raw_content = _load_document_content(representative)
            frontmatter, body = _split_frontmatter(raw_content)
            document_values = {
                "title": frontmatter.get("title") or representative["document_title"],
                "category": frontmatter.get("category") or representative["category"],
                "version": frontmatter.get("version") or representative["version"],
                "source_uri": representative["source_uri"],
                "content": body,
                "status": frontmatter.get("status") or representative["status"],
            }
            if existing_document is None:
                session.add(KnowledgeDocument(document_id=document_id, **document_values))
            else:
                for field, value in document_values.items():
                    setattr(existing_document, field, value)

            for row in document_rows:
                chunk = session.scalar(
                    select(KnowledgeChunk).where(KnowledgeChunk.chunk_id == row["chunk_id"])
                )
                values = {
                    "document_id": document_id,
                    "parent_chunk_id": row.get("parent_chunk_id"),
                    "level": row["level"],
                    "ordinal": row["ordinal"],
                    "title_path": row["title_path"],
                    "source_uri": row["source_uri"],
                    "source_anchor": row["source_anchor"],
                    "content_hash": row["content_hash"],
                    "chunker_version": row["chunker_version"],
                    "content": row["content"],
                    "embedding_text": row.get("embedding_text"),
                    "embedding_model": settings.llm_embedding_model
                    if row["level"] == "child"
                    else None,
                    # 先保存向量还未确认完成的状态，写 Chroma 成功后再置为 true。
                    "vector_indexed": row["chunk_id"] in indexed_ids,
                }
                if chunk is None:
                    session.add(KnowledgeChunk(chunk_id=row["chunk_id"], **values))
                else:
                    for field, value in values.items():
                        setattr(chunk, field, value)
        session.commit()


def _upsert_chroma(children: list[dict[str, Any]], dimensions: int) -> None:
    """把 child 向量及父片段引用等过滤元数据写进 ChromaDB。"""

    client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    collection = client.get_or_create_collection(
        name=settings.chroma_collection,
        metadata={
            "hnsw:space": "cosine",
            "mallmate:embedding_model": settings.llm_embedding_model,
            "mallmate:embedding_dimension": dimensions,
        },
    )
    metadata = collection.metadata or {}
    existing_count = collection.count()
    old_model = metadata.get("mallmate:embedding_model")
    old_dimensions = metadata.get("mallmate:embedding_dimension")
    if existing_count and (old_model != settings.llm_embedding_model or old_dimensions != dimensions):
        raise RuntimeError(
            "Chroma 集合已经有其他模型或维度的向量；请换一个空集合名，避免混合不同向量空间。"
        )
    if not existing_count and (old_model != settings.llm_embedding_model or old_dimensions != dimensions):
        collection.modify(
            metadata={
                **metadata,
                "hnsw:space": "cosine",
                "mallmate:embedding_model": settings.llm_embedding_model,
                "mallmate:embedding_dimension": dimensions,
            }
        )

    # 替换旧的同文档切片向量，清除切片内容变化后不再存在的旧 chunk_id。
    for document_id in sorted({row["document_id"] for row in children}):
        old = collection.get(where={"document_id": document_id}, include=[])
        current_ids = {row["chunk_id"] for row in children if row["document_id"] == document_id}
        stale_ids = [chunk_id for chunk_id in old.get("ids", []) if chunk_id not in current_ids]
        if stale_ids:
            collection.delete(ids=stale_ids)

    collection.upsert(
        ids=[row["chunk_id"] for row in children],
        embeddings=[row["_embedding"] for row in children],
        documents=[row.get("embedding_text") or row["content"] for row in children],
        metadatas=[
            {
                "document_id": row["document_id"],
                "parent_chunk_id": row["parent_chunk_id"],
                "document_title": row["document_title"],
                "category": row["category"],
                "version": row["version"],
                "status": row["status"],
                "source_uri": row["source_uri"],
                "source_anchor": row["source_anchor"],
                "ordinal": row["ordinal"],
                "chunker_version": row["chunker_version"],
            }
            for row in children
        ],
    )


def _mark_indexed(chunk_ids: list[str]) -> None:
    """记录已成功写入 Chroma 的 child；失败时保留 PostgreSQL 中的待索引状态。"""

    with SessionLocal() as session:
        chunks = session.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.chunk_id.in_(chunk_ids))
        )
        for chunk in chunks:
            chunk.vector_indexed = True
        session.commit()


def run_ingestion(input_path: Path = DEFAULT_OUTPUT) -> dict[str, int | str]:
    """执行：读切片 → 向量化 → 保存 Postgres → 更新 Chroma → 标记完成。"""

    if not settings.llm_enabled:
        raise RuntimeError("MALLMATE_LLM_ENABLED 未开启")
    rows = _read_jsonl(input_path)
    children, dimensions = _embed_children(rows)
    child_ids = [row["chunk_id"] for row in children]

    # 先把原文和片段安全写到关系数据库；随后 Chroma 即使临时失败也可重跑脚本修复。
    _upsert_postgres(rows, indexed_ids=set())
    _upsert_chroma(children, dimensions)
    _mark_indexed(child_ids)
    return {
        "documents": len({row["document_id"] for row in rows}),
        "parent_chunks": sum(row["level"] == "parent" for row in rows),
        "child_chunks": len(children),
        "embedding_dimensions": dimensions,
        "embedding_model": settings.llm_embedding_model,
        "chroma_collection": settings.chroma_collection,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="把 MallMate 父子切片向量化并写入 PostgreSQL/ChromaDB")
    parser.add_argument("--input", type=Path, default=DEFAULT_OUTPUT, help="offline_slicer 生成的 JSONL")
    args = parser.parse_args()
    summary = run_ingestion(args.input)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
