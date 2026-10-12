"""MallMate 离线评估入口。

本脚本不启动 FastAPI、不连接数据库、不调用通义千问。它验证三项确定性基线：
10 类意图与紧急度、Markdown 知识检索、售后规则决策。
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evals"))

from app.agent.intent import classify_intent  # noqa: E402
from app.core.enums import CaseType, OrderStatus  # noqa: E402
from app.domain.after_sales_policy import PolicyInput, evaluate_after_sales  # noqa: E402
from app.retrieval.lexical import SearchDocument, rank_bm25  # noqa: E402
from metrics import classification_metrics, ndcg_at_k, recall_at_k, reciprocal_rank  # noqa: E402


DATASETS = ROOT / "evals" / "datasets"
REPORTS = ROOT / "evals" / "reports"
KNOWLEDGE = ROOT / "knowledge" / "policies"


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def parse_knowledge() -> list[SearchDocument]:
    documents: list[SearchDocument] = []
    for path in sorted(KNOWLEDGE.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        metadata: dict[str, str] = {}
        body = text
        if text.startswith("---\n"):
            header, body = text[4:].split("\n---\n", maxsplit=1)
            for line in header.splitlines():
                key, separator, value = line.partition(":")
                if separator:
                    metadata[key.strip()] = value.strip()
        documents.append(
            SearchDocument(
                document_id=metadata.get("id", path.stem),
                title=metadata.get("title", path.stem),
                content=body,
                source_uri=str(path.relative_to(ROOT)).replace("\\", "/"),
                version=metadata.get("version", "unknown"),
            )
        )
    return documents


def evaluate_intent(split: str) -> dict:
    rows = load_jsonl(DATASETS / f"intent_{split}.jsonl")
    expected, actual, failures = [], [], []
    urgency_correct = 0
    for row in rows:
        prediction = classify_intent(row["query"])
        expected.append(row["expected_intent"])
        actual.append(prediction.intent.value)
        urgency_correct += prediction.urgency.value == row["expected_urgency"]
        if prediction.intent.value != row["expected_intent"]:
            failures.append({"case_id": row["case_id"], "expected": row["expected_intent"], "actual": prediction.intent.value})
    result = classification_metrics(expected, actual)
    result.update({"cases": len(rows), "urgency_accuracy": round(urgency_correct / max(len(rows), 1), 4), "failures": failures})
    return result


def evaluate_retrieval(split: str) -> dict:
    rows = load_jsonl(DATASETS / f"retrieval_{split}.jsonl")
    documents = parse_knowledge()
    recalls, reciprocal_ranks, ndcgs, failures = [], [], [], []
    for row in rows:
        ranked = [item.document.document_id for item in rank_bm25(row["query"], documents, limit=5)]
        relevant = set(row["relevant_document_ids"])
        recall = recall_at_k(relevant, ranked, 5)
        recalls.append(recall)
        reciprocal_ranks.append(reciprocal_rank(relevant, ranked))
        ndcgs.append(ndcg_at_k(relevant, ranked, 5))
        if recall < 1:
            failures.append({"case_id": row["case_id"], "relevant": sorted(relevant), "top5": ranked})
    count = max(len(rows), 1)
    return {
        "cases": len(rows),
        "recall_at_5": round(sum(recalls) / count, 4),
        "mrr": round(sum(reciprocal_ranks) / count, 4),
        "ndcg_at_5": round(sum(ndcgs) / count, 4),
        "failures": failures,
    }


def evaluate_policy(split: str) -> dict:
    rows = load_jsonl(DATASETS / f"policy_{split}.jsonl")
    failures: list[dict] = []
    for row in rows:
        input_data = row["input"]
        decision = evaluate_after_sales(
            PolicyInput(
                order_status=OrderStatus(input_data["order_status"]),
                case_type=CaseType(input_data["case_type"]),
                reason=input_data["reason"],
                amount_cents=input_data["amount_cents"],
                delivered_at=datetime.fromisoformat(input_data["delivered_at"]) if input_data["delivered_at"] else None,
                all_items_returnable=input_data["all_items_returnable"],
            ),
            now=datetime.fromisoformat(row["evaluation_time"]),
        )
        expected = row["expected"]
        actual = {
            "eligible": decision.eligible,
            "code": decision.code,
            "requires_evidence": decision.requires_evidence,
            "requires_human": decision.requires_human,
        }
        if actual != expected:
            failures.append({"case_id": row["case_id"], "expected": expected, "actual": actual})
    return {"cases": len(rows), "exact_match": round((len(rows) - len(failures)) / max(len(rows), 1), 4), "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser(description="运行不调用大模型的 MallMate 离线评估")
    parser.add_argument("--split", choices=("dev", "holdout"), default="dev")
    args = parser.parse_args()

    report = {
        "dataset_version": "mallmate-eval-2026.10-v1",
        "split": args.split,
        "generated_at": datetime.now().astimezone().isoformat(),
        "model_mode": "deterministic_offline_baseline",
        "intent": evaluate_intent(args.split),
        "retrieval": evaluate_retrieval(args.split),
        "policy": evaluate_policy(args.split),
    }
    thresholds = {
        "intent_macro_f1": 0.80,
        "retrieval_recall_at_5": 0.85,
        "policy_exact_match": 0.95,
    }
    report["thresholds"] = thresholds
    report["passed"] = (
        report["intent"]["macro_f1"] >= thresholds["intent_macro_f1"]
        and report["retrieval"]["recall_at_5"] >= thresholds["retrieval_recall_at_5"]
        and report["policy"]["exact_match"] >= thresholds["policy_exact_match"]
    )

    REPORTS.mkdir(parents=True, exist_ok=True)
    output = REPORTS / f"offline-{args.split}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n报告已写入: {output}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
