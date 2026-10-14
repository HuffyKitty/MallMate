"""建立完整基线，并为旧演示库补充认证结构。

Revision ID: 20261013_0001
Revises: None
Create Date: 2026-10-13

旧版本曾通过 ``Base.metadata.create_all()`` 直接创建业务表。这个迁移先检查目标数据库：
空数据库会创建完整基线；已有表只有在包含当前基线要求的全部旧字段时才会被接管。
任一已有业务表缺少必需列都会明确失败，避免把未知旧结构错误标记为最新版本。
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261013_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 这些是认证改造前业务基线已有的列。customers.user_account_id 由本迁移新增，
# 因此不属于接管旧表前必须存在的列。
_REQUIRED_EXISTING_BUSINESS_COLUMNS: dict[str, set[str]] = {
    "customers": {"id", "demo_handle", "display_name", "phone_masked", "member_level"},
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


def _table_names() -> set[str]:
    """每次重新检查，避免 Inspector 缓存看不到刚创建的表。"""

    return set(sa.inspect(op.get_bind()).get_table_names())


def _validate_existing_business_schema() -> None:
    """接管旧业务表前检查最低列结构，未知旧版本交给专用迁移处理。"""

    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    problems: list[str] = []

    for table_name, required_columns in _REQUIRED_EXISTING_BUSINESS_COLUMNS.items():
        # 缺失整张表属于空库或部分初始化场景，后续创建函数会补齐；只有已经存在
        # 却字段不足的表才危险，因为 create_table 无法升级它。
        if table_name not in existing_tables:
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
            "拒绝接管现有 MallMate 数据库：业务表结构早于受支持基线（"
            f"{details}）。请保留备份并编写显式数据迁移，不能直接标记 Alembic head。"
        )


def _create_user_accounts() -> None:
    if "user_accounts" in _table_names():
        return

    op.create_table(
        "user_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username_normalized", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('customer', 'support', 'admin')",
            name="ck_user_accounts_role",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'locked', 'disabled')",
            name="ck_user_accounts_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_accounts"),
    )
    op.create_index("ix_user_accounts_username_normalized", "user_accounts", ["username_normalized"], unique=True)
    op.create_index("ix_user_accounts_role", "user_accounts", ["role"], unique=False)
    op.create_index("ix_user_accounts_status", "user_accounts", ["status"], unique=False)


def _create_or_upgrade_customers() -> None:
    if "customers" not in _table_names():
        op.create_table(
            "customers",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_account_id", sa.Integer(), nullable=True),
            sa.Column("demo_handle", sa.String(length=80), nullable=False),
            sa.Column("display_name", sa.String(length=80), nullable=False),
            sa.Column("phone_masked", sa.String(length=30), nullable=False),
            sa.Column("member_level", sa.String(length=30), nullable=False),
            sa.ForeignKeyConstraint(
                ["user_account_id"],
                ["user_accounts.id"],
                name="fk_customers_user_account_id_user_accounts",
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id", name="pk_customers"),
            sa.UniqueConstraint("user_account_id", name="uq_customers_user_account_id"),
        )
        op.create_index("ix_customers_demo_handle", "customers", ["demo_handle"], unique=True)
        return

    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("customers")}
    if "user_account_id" in columns:
        return

    # batch_alter_table 会在 SQLite 上安全重建表，在 PostgreSQL 上生成普通 ALTER TABLE。
    with op.batch_alter_table("customers") as batch_op:
        batch_op.add_column(sa.Column("user_account_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_customers_user_account_id_user_accounts",
            "user_accounts",
            ["user_account_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            "uq_customers_user_account_id",
            ["user_account_id"],
        )


def _create_auth_sessions() -> None:
    if "auth_sessions" in _table_names():
        return

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_account_id", sa.Integer(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_account_id"],
            ["user_accounts.id"],
            name="fk_auth_sessions_user_account_id_user_accounts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auth_sessions"),
    )
    op.create_index("ix_auth_sessions_user_account_id", "auth_sessions", ["user_account_id"], unique=False)
    op.create_index("ix_auth_sessions_refresh_token_hash", "auth_sessions", ["refresh_token_hash"], unique=True)
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"], unique=False)
    op.create_index("ix_auth_sessions_revoked_at", "auth_sessions", ["revoked_at"], unique=False)


def _create_products() -> None:
    if "products" in _table_names():
        return
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("returnable", sa.Boolean(), nullable=False),
        sa.Column("return_exclusion_reason", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
        sa.UniqueConstraint("sku", name="uq_products_sku"),
    )


def _create_orders() -> None:
    if "orders" in _table_names():
        return
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_orders_customer_id_customers"),
        sa.PrimaryKeyConstraint("id", name="pk_orders"),
    )
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"], unique=False)


def _create_order_items() -> None:
    if "order_items" in _table_names():
        return
    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_order_items_order_id_orders"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_order_items_product_id_products"),
        sa.PrimaryKeyConstraint("id", name="pk_order_items"),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"], unique=False)


def _create_shipments() -> None:
    if "shipments" in _table_names():
        return
    op.create_table(
        "shipments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("carrier", sa.String(length=80), nullable=False),
        sa.Column("tracking_number", sa.String(length=100), nullable=False),
        sa.Column("latest_event", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_shipments_order_id_orders"),
        sa.PrimaryKeyConstraint("id", name="pk_shipments"),
        sa.UniqueConstraint("order_id", name="uq_shipments_order_id"),
    )


def _create_knowledge_documents() -> None:
    if "knowledge_documents" in _table_names():
        return
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("source_uri", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_documents"),
    )
    op.create_index("ix_knowledge_documents_document_id", "knowledge_documents", ["document_id"], unique=True)
    op.create_index("ix_knowledge_documents_category", "knowledge_documents", ["category"], unique=False)


def _create_after_sales_cases() -> None:
    if "after_sales_cases" in _table_names():
        return
    op.create_table(
        "after_sales_cases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("case_type", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_after_sales_cases_order_id_orders"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_after_sales_cases_customer_id_customers"),
        sa.PrimaryKeyConstraint("id", name="pk_after_sales_cases"),
        sa.UniqueConstraint("customer_id", "idempotency_key", name="uq_after_sales_cases_customer_id_idempotency_key"),
    )
    op.create_index("ix_after_sales_cases_order_id", "after_sales_cases", ["order_id"], unique=False)
    op.create_index("ix_after_sales_cases_customer_id", "after_sales_cases", ["customer_id"], unique=False)


def _create_conversations() -> None:
    if "conversations" in _table_names():
        return
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_conversations_customer_id_customers"),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
    )
    op.create_index("ix_conversations_customer_id", "conversations", ["customer_id"], unique=False)


def _create_messages() -> None:
    if "messages" in _table_names():
        return
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], name="fk_messages_conversation_id_conversations"),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"], unique=False)


def upgrade() -> None:
    # 必须在创建认证表或改动 customers 之前完成检查，避免失败时留下半套接管结构。
    _validate_existing_business_schema()

    # 认证账号必须先于 customers 创建，才能建立可空外键。
    _create_user_accounts()
    _create_or_upgrade_customers()
    _create_auth_sessions()

    # 对空库创建完整业务基线；接管旧库时这些函数因表已存在而不会改动数据。
    _create_products()
    _create_orders()
    _create_order_items()
    _create_shipments()
    _create_knowledge_documents()
    _create_after_sales_cases()
    _create_conversations()
    _create_messages()


def downgrade() -> None:
    """只撤销认证增量，保留可能在 Alembic 接管前就存在的业务表。"""

    tables = _table_names()
    if "auth_sessions" in tables:
        op.drop_table("auth_sessions")

    if "customers" in _table_names():
        columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("customers")}
        if "user_account_id" in columns:
            with op.batch_alter_table("customers") as batch_op:
                batch_op.drop_constraint("uq_customers_user_account_id", type_="unique")
                batch_op.drop_constraint(
                    "fk_customers_user_account_id_user_accounts",
                    type_="foreignkey",
                )
                batch_op.drop_column("user_account_id")

    if "user_accounts" in _table_names():
        op.drop_table("user_accounts")
