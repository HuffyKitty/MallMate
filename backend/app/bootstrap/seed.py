"""从版本化 fixture 与 Markdown 知识库初始化演示数据。

初始化可重复执行：每类数据都按稳定业务键检查，只补缺失记录。Fixture 中全部人物、
电话、订单和运单均为虚构数据，不应与真实业务混用。
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.enums import AccountStatus, UserRole
from app.core.security import hash_password
from app.models import (
    AfterSalesCase,
    Customer,
    KnowledgeDocument,
    Order,
    OrderItem,
    Product,
    Shipment,
    UserAccount,
)


BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent
FIXTURE_PATH = BACKEND_DIR / "fixtures" / "demo_data.json"
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge" / "policies"
DEMO_PASSWORD = "MallMate123!"


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


def _sync_postgresql_id_sequences(db: Session) -> None:
    """让 PostgreSQL 自增序列跟上 fixture 中显式指定的业务 ID。

    SQLite 会自动根据最大 ROWID 继续分配，而 PostgreSQL 的序列不会因为插入
    ``orders.id=1001`` 自动前进。如果不处理，后续真实写入最终会撞上 fixture ID。
    """

    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table_name in ("orders", "after_sales_cases"):
        # 表名来自代码中的固定白名单，不接收用户输入。第三个参数决定空表时下一次
        # nextval 返回 1，非空表时返回 MAX(id)+1。
        db.execute(
            text(
                f"""
                SELECT setval(
                    pg_get_serial_sequence('{table_name}', 'id'),
                    GREATEST(COALESCE(MAX(id), 1), 1),
                    COUNT(*) > 0
                )
                FROM {table_name}
                """
            )
        )


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

    # 演示账号只在首次缺失时创建，重复启动不会重置密码或覆盖用户后续修改。
    # 登录名使用和 demo_handle 相同的稳定值，三位演示顾客的开发密码均为
    # MallMate123!；数据库中只保存 Argon2 哈希，不保存该明文。
    for handle, customer in customers.items():
        username_normalized = handle.strip().casefold()
        account = db.scalar(
            select(UserAccount).where(
                UserAccount.username_normalized == username_normalized,
            )
        )
        if account is None:
            account = UserAccount(
                username_normalized=username_normalized,
                password_hash=hash_password(DEMO_PASSWORD),
                role=UserRole.CUSTOMER.value,
                status=AccountStatus.ACTIVE.value,
            )
            db.add(account)
            db.flush()

        # 仅补齐空关联，不改写已经存在的账号归属，避免种子过程破坏业务数据。
        if customer.user_account_id is None:
            linked_customer_id = db.scalar(
                select(Customer.id).where(Customer.user_account_id == account.id)
            )
            if linked_customer_id is None:
                customer.user_account_id = account.id

    # 这两个账号只服务于 seed_demo_data=true 的本地角色联调，不关联 Customer，
    # 不能作为正式客服或管理员账号发布到生产环境。
    for username, role in (
        ("support-demo", UserRole.SUPPORT),
        ("admin-demo", UserRole.ADMIN),
    ):
        account = db.scalar(
            select(UserAccount).where(UserAccount.username_normalized == username)
        )
        if account is None:
            db.add(
                UserAccount(
                    username_normalized=username,
                    password_hash=hash_password(DEMO_PASSWORD),
                    role=role.value,
                    status=AccountStatus.ACTIVE.value,
                )
            )

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

    # 文本 SQL 不应依赖 ORM 是否自动 flush；先明确写出所有待处理对象，再读取
    # MAX(id) 同步序列。两步仍处于同一个事务中。
    db.flush()
    _sync_postgresql_id_sequences(db)
    db.commit()
