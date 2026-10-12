"""从版本化 fixture 与 Markdown 知识库初始化演示数据。

初始化可重复执行：每类数据都按稳定业务键检查，只补缺失记录。Fixture 中全部人物、
电话、订单和运单均为虚构数据，不应与真实业务混用。
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AfterSalesCase,
    Customer,
    KnowledgeDocument,
    Order,
    OrderItem,
    Product,
    Shipment,
)


BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent
FIXTURE_PATH = BACKEND_DIR / "fixtures" / "demo_data.json"
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge" / "policies"


def _datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    header, body = text[4:].split("\n---\n", maxsplit=1)
    metadata: dict[str, str] = {}
    for line in header.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip().strip('"')
    return metadata, body.strip()


def _request_hash(order_id: int, case_type: str, reason: str) -> str:
    payload = [order_id, case_type, reason]
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def seed_demo(db: Session) -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    customers: dict[str, Customer] = {}
    products: dict[str, Product] = {}

    for row in payload["customers"]:
        item = db.scalar(select(Customer).where(Customer.demo_handle == row["handle"]))
        if item is None:
            item = Customer(
                demo_handle=row["handle"],
                display_name=row["display_name"],
                phone_masked=row["phone_masked"],
                member_level=row["member_level"],
            )
            db.add(item)
            db.flush()
        customers[row["handle"]] = item

    for row in payload["products"]:
        item = db.scalar(select(Product).where(Product.sku == row["sku"]))
        if item is None:
            item = Product(**row)
            db.add(item)
            db.flush()
        products[row["sku"]] = item

    for row in payload["orders"]:
        if db.get(Order, row["id"]) is None:
            db.add(
                Order(
                    id=row["id"],
                    customer_id=customers[row["customer"]].id,
                    status=row["status"],
                    amount_cents=row["amount_cents"],
                    created_at=_datetime(row["created_at"]),
                    paid_at=_datetime(row["paid_at"]),
                    shipped_at=_datetime(row["shipped_at"]),
                    delivered_at=_datetime(row["delivered_at"]),
                )
            )
    db.flush()

    for row in payload["order_items"]:
        product = products[row["sku"]]
        exists = db.scalar(
            select(OrderItem).where(
                OrderItem.order_id == row["order_id"],
                OrderItem.product_id == product.id,
            )
        )
        if exists is None:
            db.add(OrderItem(order_id=row["order_id"], product_id=product.id, quantity=row["quantity"]))

    for row in payload["shipments"]:
        if db.scalar(select(Shipment).where(Shipment.order_id == row["order_id"])) is None:
            db.add(
                Shipment(
                    order_id=row["order_id"],
                    status=row["status"],
                    carrier=row["carrier"],
                    tracking_number=row["tracking_number"],
                    latest_event=row["latest_event"],
                    updated_at=_datetime(row["updated_at"]),
                )
            )

    for row in payload["after_sales_cases"]:
        if db.get(AfterSalesCase, row["id"]) is None:
            reason = row["reason"].strip()
            db.add(
                AfterSalesCase(
                    id=row["id"],
                    order_id=row["order_id"],
                    customer_id=customers[row["customer"]].id,
                    case_type=row["case_type"],
                    reason=reason,
                    request_hash=_request_hash(row["order_id"], row["case_type"], reason),
                    idempotency_key=row["idempotency_key"],
                    status=row["status"],
                    created_at=_datetime(row["created_at"]),
                )
            )

    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        metadata, content = _frontmatter(path)
        document_id = metadata.get("id", path.stem)
        exists = db.scalar(
            select(KnowledgeDocument).where(KnowledgeDocument.document_id == document_id)
        )
        if exists is None:
            db.add(
                KnowledgeDocument(
                    document_id=document_id,
                    title=metadata.get("title", path.stem),
                    category=metadata.get("category", "general"),
                    version=metadata.get("version", "unversioned"),
                    source_uri=f"knowledge/policies/{path.name}",
                    content=content,
                    status=metadata.get("status", "active"),
                )
            )

    db.commit()
