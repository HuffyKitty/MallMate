"""BM25 与向量召回的轻量 RRF 融合。"""

from dataclasses import dataclass

from app.retrieval.lexical import RankedDocument


@dataclass(frozen=True)
class FusedChunk:
    """RRF 排名后的子片段；保留两路名次便于日志和后续评估。"""

    chunk_id: str
    score: float
    bm25_rank: int | None
    vector_rank: int | None


def reciprocal_rank_fusion(
    bm25_results: list[RankedDocument],
    vector_chunk_ids: list[str],
    *,
    limit: int = 8,
    constant: int = 60,
) -> list[FusedChunk]:
    """使用 RRF 合并两个排序列表，不直接比较 BM25 分数和向量距离。

    两类检索的分值含义和范围不同，RRF 只看各自名次；同时命中两路的片段自然会
    得到更高的融合分数。名次从 1 开始，符合 RRF 的标准定义。
    """

    if limit <= 0:
        return []

    scores: dict[str, float] = {}
    bm25_ranks: dict[str, int] = {}
    vector_ranks: dict[str, int] = {}

    for rank, result in enumerate(bm25_results, start=1):
        chunk_id = result.document.document_id
        bm25_ranks[chunk_id] = rank
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (constant + rank)

    # Chroma 通常不会重复返回 ID；seen 仍可防御异常/替代向量后端的重复结果。
    for rank, chunk_id in enumerate(dict.fromkeys(vector_chunk_ids), start=1):
        vector_ranks[chunk_id] = rank
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (constant + rank)

    ranked = sorted(scores, key=lambda item: (-scores[item], item))[:limit]
    return [
        FusedChunk(
            chunk_id=chunk_id,
            score=scores[chunk_id],
            bm25_rank=bm25_ranks.get(chunk_id),
            vector_rank=vector_ranks.get(chunk_id),
        )
        for chunk_id in ranked
    ]
