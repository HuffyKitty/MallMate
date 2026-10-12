"""不依赖第三方机器学习库的评估指标。"""

import math
from collections import Counter


def classification_metrics(expected: list[str], actual: list[str]) -> dict:
    labels = sorted(set(expected) | set(actual))
    per_label: dict[str, dict[str, float | int]] = {}
    for label in labels:
        true_positive = sum(e == label and a == label for e, a in zip(expected, actual, strict=True))
        false_positive = sum(e != label and a == label for e, a in zip(expected, actual, strict=True))
        false_negative = sum(e == label and a != label for e, a in zip(expected, actual, strict=True))
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = {
            "support": Counter(expected)[label],
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
    accuracy = sum(e == a for e, a in zip(expected, actual, strict=True)) / max(len(expected), 1)
    macro_f1 = sum(float(values["f1"]) for values in per_label.values()) / max(len(labels), 1)
    return {"accuracy": round(accuracy, 4), "macro_f1": round(macro_f1, 4), "per_label": per_label}


def recall_at_k(relevant: set[str], ranked: list[str], k: int) -> float:
    return len(relevant & set(ranked[:k])) / max(len(relevant), 1)


def reciprocal_rank(relevant: set[str], ranked: list[str]) -> float:
    for position, document_id in enumerate(ranked, start=1):
        if document_id in relevant:
            return 1 / position
    return 0.0


def ndcg_at_k(relevant: set[str], ranked: list[str], k: int) -> float:
    dcg = sum(
        1 / math.log2(position + 1)
        for position, document_id in enumerate(ranked[:k], start=1)
        if document_id in relevant
    )
    ideal_hits = min(len(relevant), k)
    ideal = sum(1 / math.log2(position + 1) for position in range(1, ideal_hits + 1))
    return dcg / ideal if ideal else 0.0
