from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AccountStatus, UserRole
from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Customer(Base):
    """客户业务资料。

    ``user_account_id`` 只负责把登录账号和客户资料连接起来。它允许为空，方便导入
    还没有开通登录账号的历史客户；唯一约束保证一个登录账号最多对应一个客户。
    """
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_accounts.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    demo_handle: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    phone_masked: Mapped[str] = mapped_column(String(30), default="")
    member_level: Mapped[str] = mapped_column(String(30), default="normal")
    user_account: Mapped["UserAccount | None"] = relationship(back_populates="customer")


class UserAccount(Base):
    """用于登录和授权的账号，和订单等业务资料保持分离。

    角色与状态暂时使用字符串存储，便于接口序列化；数据库 CHECK 约束会拦截未知值，
    应用层则统一使用 ``UserRole`` 和 ``AccountStatus`` 枚举。
    """

    __tablename__ = "user_accounts"
    __table_args__ = (
        CheckConstraint(
            "role IN ('customer', 'support', 'admin')",
            name="ck_user_accounts_role",
        ),
        CheckConstraint(
            "status IN ('active', 'locked', 'disabled')",
            name="ck_user_accounts_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username_normalized: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=UserRole.CUSTOMER.value, index=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default=AccountStatus.ACTIVE.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )

    customer: Mapped[Customer | None] = relationship(back_populates="user_account", uselist=False)
    sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user_account",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AuthSession(Base):
    """可撤销的刷新会话。

    浏览器持有刷新令牌原文，数据库只保存 SHA-256 等单向摘要。退出登录、令牌轮换
    或账号停用时设置 ``revoked_at``，无需保存访问 JWT 的明文或黑名单。
    """

    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_account_id: Mapped[int] = mapped_column(
        ForeignKey("user_accounts.id", ondelete="CASCADE"),
        index=True,
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    user_account: Mapped[UserAccount] = relationship(back_populates="sessions")


class Product(Base):
    """最小商品目录。首版只保留售后流程必需的信息。"""
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(80), default="general")
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    returnable: Mapped[bool] = mapped_column(Boolean, default=True)
    return_exclusion_reason: Mapped[str] = mapped_column(Text, default="")


class Order(Base):
    """订单事实。customer_id 是所有订单授权检查的依据。"""
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    status: Mapped[str] = mapped_column(String(40))
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(10), default="CNY")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    customer: Mapped[Customer] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(lazy="selectin")


class OrderItem(Base):
    """订单和商品的关联记录，并保存购买数量。"""
    __tablename__ = "order_items"
    __table_args__ = (
        # 同一订单中的同一商品只保留一行，数量由 quantity 表达。数据库约束可以
        # 阻止并发种子任务或后续导入脚本写出重复明细。
        UniqueConstraint(
            "order_id",
            "product_id",
            name="uq_order_items_order_id_product_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    product: Mapped[Product] = relationship(lazy="joined")


class Shipment(Base):
    """首版物流状态；按当前范围，一笔订单对应一条物流记录。"""
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    status: Mapped[str] = mapped_column(String(40))
    carrier: Mapped[str] = mapped_column(String(80), default="")
    tracking_number: Mapped[str] = mapped_column(String(100), default="")
    latest_event: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeDocument(Base):
    """知识文档原文；文档级元数据和原文由 PostgreSQL 作为权威存储。"""
    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(80), default="general", index=True)
    version: Mapped[str] = mapped_column(String(40))
    source_uri: Mapped[str] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="active")


class KnowledgeChunk(Base):
    """离线生成的父子片段；向量本身保存在 ChromaDB。"""

    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.document_id", ondelete="CASCADE"), index=True
    )
    parent_chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_chunks.chunk_id", ondelete="CASCADE"), nullable=True, index=True
    )
    level: Mapped[str] = mapped_column(String(20), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    title_path: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_uri: Mapped[str] = mapped_column(String(500))
    source_anchor: Mapped[str] = mapped_column(String(500), default="")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    chunker_version: Mapped[str] = mapped_column(String(80))
    content: Mapped[str] = mapped_column(Text)
    # embedding_text 含标题路径，向量模型能看到小节上下文；父片段不生成向量。
    embedding_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    vector_indexed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class AfterSalesCase(Base):
    """售后申请；用户与幂等键的唯一约束防止重复创建。"""
    __tablename__ = "after_sales_cases"
    __table_args__ = (UniqueConstraint("customer_id", "idempotency_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    case_type: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    request_hash: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), default="pending_review")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Conversation(Base):
    """会话主记录，用 customer_id 控制会话归属。"""
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Message(Base):
    """会话消息。当前保存文本，后续可扩展附件和引用。"""
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

