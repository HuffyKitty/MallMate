"""保证一笔订单中的同一商品只有一条明细。

Revision ID: 20261014_0002
Revises: 20261013_0001
Create Date: 2026-10-14

迁移先核对 0001 应提供的最低表结构，并检查历史重复数据。这样已经执行过早期
0001 文件的数据库也不会在结构残缺或数据冲突时被错误标记为最新版本。
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261014_0002"
down_revision: str | None = "20261013_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_REQUIRED_HEAD_COLUMNS: dict[str, set[str]] = {
    "user_accounts": {
        "id",
        "username_normalized",
        "password_hash",
        "role",
        "status",
        "created_at",
        "updated_at",
        "password_changed_at",
    },
    "auth_sessions": {
        "id",
        "user_account_id",
        "refresh_token_hash",
        "created_at",
        "expires_at",
        "revoked_at",
    },
    "customers": {
        "id",
        "user_account_id",
        "demo_handle",
        "display_name",
        "phone_masked",
        "member_level",
    },
    "products": {
        "id",
        "sku",
        "name",
        "description",
        "category",
        "price_cents",
        "returnable",
        "return_exclusion_reason",
    },
    "orders": {
        "id",
        "customer_id",
        "status",
        "amount_cents",
        "currency",
        "created_at",
        "paid_at",
        "shipped_at",
        "delivered_at",
    },
    "order_items": {"id", "order_id", "product_id", "quantity"},
    "shipments": {
        "id",
        "order_id",
        "status",
        "carrier",
        "tracking_number",
        "latest_event",
        "updated_at",
    },
    "knowledge_documents": {
        "id",
        "document_id",
        "title",
        "category",
        "version",
        "source_uri",
        "content",
        "status",
    },
    "after_sales_cases": {
        "id",
        "order_id",
        "customer_id",
        "case_type",
        "reason",
        "request_hash",
        "idempotency_key",
        "status",
        "created_at",
    },
    "conversations": {"id", "customer_id", "created_at"},
    "messages": {"id", "conversation_id", "role", "content", "created_at"},
}


def _validate_previous_revision_schema() -> None:
    """保护曾使用早期 0001 文件接管的数据库。"""

    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    problems: list[str] = []

    for table_name, required_columns in _REQUIRED_HEAD_COLUMNS.items():
        if table_name not in existing_tables:
            problems.append(f"缺少表: {table_name}")
            continue
        actual_columns = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        missing_columns = sorted(required_columns - actual_columns)
        if missing_columns:
            problems.append(f"{table_name} 缺少列: {', '.join(missing_columns)}")

    if problems:
        details = "; ".join(problems)
        raise RuntimeError(
            "无法升级到 20261014_0002：数据库不满足 0001 基线（"
            f"{details}）。请从备份恢复并编写专用迁移，不能直接标记 Alembic head。"
        )


def _has_equivalent_unique_rule() -> bool:
    """识别已有的组合唯一约束或唯一索引，避免重复创建。"""

    inspector = sa.inspect(op.get_bind())
    expected_columns = {"order_id", "product_id"}

    for constraint in inspector.get_unique_constraints("order_items"):
        if set(constraint.get("column_names") or []) == expected_columns:
            return True

    for index in inspector.get_indexes("order_items"):
        if index.get("unique") and set(index.get("column_names") or []) == expected_columns:
            return True

    return False


def _reject_duplicate_order_items() -> None:
    """已有重复行需要人工确定数量，迁移不擅自合并业务数据。"""

    duplicate = op.get_bind().execute(
        sa.text(
            """
            SELECT order_id, product_id, COUNT(*) AS row_count
            FROM order_items
            GROUP BY order_id, product_id
            HAVING COUNT(*) > 1
            ORDER BY order_id, product_id
            LIMIT 1
            """
        )
    ).mappings().first()

    if duplicate is not None:
        raise RuntimeError(
            "无法创建订单明细唯一约束：发现重复数据 "
            f"order_id={duplicate['order_id']}, product_id={duplicate['product_id']}, "
            f"共 {duplicate['row_count']} 行。请先核对并合并数量，再重新执行迁移。"
        )


def upgrade() -> None:
    _validate_previous_revision_schema()
    if _has_equivalent_unique_rule():
        return

    _reject_duplicate_order_items()
    # batch 模式会为 SQLite 安全重建表；PostgreSQL 会执行普通 ALTER TABLE。
    with op.batch_alter_table("order_items") as batch_op:
        batch_op.create_unique_constraint(
            "uq_order_items_order_id_product_id",
            ["order_id", "product_id"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    owned_constraint_exists = any(
        constraint.get("name") == "uq_order_items_order_id_product_id"
        for constraint in inspector.get_unique_constraints("order_items")
    )
    if not owned_constraint_exists:
        return

    with op.batch_alter_table("order_items") as batch_op:
        batch_op.drop_constraint(
            "uq_order_items_order_id_product_id",
            type_="unique",
        )
