"""跨 API、业务服务和 Agent 共用的受控枚举。

把意图、订单状态等值集中在这里，可以避免不同文件各自手写字符串，
也能让 Pydantic 在请求入口尽早拒绝非法值。
"""

from enum import StrEnum


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Intent(StrEnum):
    """首版固定的 10 类售后意图。

    枚举值同时用于 API、LangGraph 路由和离线评估，修改时必须同步升级数据集版本。
    """

    ORDER_QUERY = "order_query"
    LOGISTICS_QUERY = "logistics_query"
    LOGISTICS_ABNORMAL = "logistics_abnormal"
    REFUND_REQUEST = "refund_request"
    RETURN_REQUEST = "return_request"
    EXCHANGE_REQUEST = "exchange_request"
    DAMAGED_PRODUCT = "damaged_product"
    MISSING_PRODUCT = "missing_product"
    WRONG_PRODUCT = "wrong_product"
    HUMAN_HANDOFF = "human_handoff"


class Urgency(StrEnum):
    NORMAL = "normal"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class CaseType(StrEnum):
    REFUND = "refund"
    RETURN = "return"
    EXCHANGE = "exchange"


class CaseStatus(StrEnum):
    PENDING_EVIDENCE = "pending_evidence"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    WAITING_RETURN = "waiting_return"
    REFUND_PROCESSING = "refund_processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OrderStatus(StrEnum):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDING = "refunding"
    REFUNDED = "refunded"


class ShipmentStatus(StrEnum):
    NOT_SHIPPED = "not_shipped"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"

