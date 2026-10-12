"""可离线复现的 BM25 中文检索基线。

当前实现不需要分词服务：连续中文会生成单字和双字 token，英文与数字按词提取。
它用于无模型开发、种子知识查询与离线评估。ChromaDB 向量召回接入后，会与本结果
通过 RRF 融合，而不是删除这个稳定基线。
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SearchDocument:
    document_id: str
    title: str
    content: str
    source_uri: str
    version: str = "unknown"


@dataclass(frozen=True)
class RankedDocument:
    document: SearchDocument
    score: float


def tokenize(text: str) -> list[str]:
    normalized = text.lower()
    ascii_tokens = re.findall(r"[a-z0-9]+", normalized)
    chinese_runs = re.findall(r"[\u4e00-\u9fff]+", normalized)
    chinese_tokens: list[str] = []
    for run in chinese_runs:
        chinese_tokens.extend(run)
        chinese_tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
    return ascii_tokens + chinese_tokens


def rank_bm25(
    query: str,
    documents: Iterable[SearchDocument],
    *,
    limit: int = 5,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[RankedDocument]:
    docs = list(documents)
    if not docs or limit <= 0:
        return []

    tokenized = [tokenize(f"{doc.title} {doc.content}") for doc in docs]
    query_tokens = set(tokenize(query))
    average_length = sum(map(len, tokenized)) / len(tokenized)
    document_frequency = Counter(
        token for tokens in tokenized for token in set(tokens)
    )

    ranked: list[RankedDocument] = []
    for doc, tokens in zip(docs, tokenized, strict=True):
        frequencies = Counter(tokens)
        score = 0.0
        for token in query_tokens:
            frequency = frequencies[token]
            if frequency == 0:
                continue
            containing = document_frequency[token]
            idf = math.log(1 + (len(docs) - containing + 0.5) / (containing + 0.5))
            denominator = frequency + k1 * (
                1 - b + b * len(tokens) / max(average_length, 1)
            )
            score += idf * frequency * (k1 + 1) / denominator
        if score > 0:
            ranked.append(RankedDocument(doc, score))

    return sorted(ranked, key=lambda item: (-item.score, item.document.document_id))[:limit]
