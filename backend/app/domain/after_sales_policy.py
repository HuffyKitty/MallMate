"""售后资格的确定性规则。

本文件是演示平台规则 v2026.10，不替代法律意见。规则输入来自数据库事实，输出供
Service、Agent 和离线评估共同使用，防止三处各写一套判断。
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.enums import CaseType, OrderStatus


POLICY_VERSION = "mallmate-demo-2026.10-v1"
NO_REASON_RETURN_DAYS = 7
EXCHANGE_DAYS = 15
HIGH_VALUE_CENTS = 100_000


@dataclass(frozen=True)
class PolicyInput:
    order_status: OrderStatus
    case_type: CaseType
    reason: str
    amount_cents: int
    delivered_at: datetime | None
    all_items_returnable: bool


@dataclass(frozen=True)
class PolicyDecision:
    eligible: bool
    code: str
    explanation: str
    requires_evidence: bool
    requires_human: bool
    policy_version: str = POLICY_VERSION


QUALITY_TERMS = ("破损", "坏", "裂", "漏液", "故障", "少件", "漏发", "发错", "质量")


def evaluate_after_sales(data: PolicyInput, *, now: datetime | None = None) -> PolicyDecision:
    """按订单状态、时效、商品属性和问题类型给出可审计结论。"""

    current_time = now or datetime.now(timezone.utc)
    reason = data.reason.strip()
    quality_issue = any(term in reason for term in QUALITY_TERMS)

    if len(reason) < 4:
        return _decision(False, "reason_too_short", "请补充至少 4 个字的问题说明")

    if data.order_status in {OrderStatus.CANCELLED, OrderStatus.REFUNDED}:
        return _decision(False, "order_closed", "订单已取消或已退款，不能重复申请")

    if data.case_type == CaseType.REFUND and data.order_status in {
        OrderStatus.PAID,
        OrderStatus.PROCESSING,
    }:
        return _decision(True, "refund_before_shipment", "订单尚未发货，可以申请退款")

    if data.order_status == OrderStatus.SHIPPED:
        return _decision(
            False,
            "in_transit_requires_human",
            "订单运输中，需要先尝试拦截或拒收，由人工确认后续处理",
            requires_human=True,
        )

    if data.order_status not in {OrderStatus.DELIVERED, OrderStatus.COMPLETED}:
        return _decision(False, "status_not_supported", "当前订单状态暂不支持该售后类型")

    if data.delivered_at is None:
        return _decision(
            False,
            "missing_delivery_time",
            "订单缺少签收时间，无法自动判断售后时效",
            requires_human=True,
        )

    delivered_at = data.delivered_at
    if delivered_at.tzinfo is None:
        delivered_at = delivered_at.replace(tzinfo=timezone.utc)
    days_since_delivery = max(0, (current_time - delivered_at).days)

    if quality_issue:
        return _decision(
            True,
            "quality_issue_review",
            "疑似质量、少件或错发问题，需要上传凭证并进入人工审核",
            requires_evidence=True,
            requires_human=data.amount_cents >= HIGH_VALUE_CENTS,
        )

    if not data.all_items_returnable:
        return _decision(
            False,
            "item_not_returnable",
            "订单包含已明确确认不适用无理由退货的商品，需要人工核验",
            requires_human=True,
        )

    limit = EXCHANGE_DAYS if data.case_type == CaseType.EXCHANGE else NO_REASON_RETURN_DAYS
    if days_since_delivery > limit:
        return _decision(
            False,
            "window_expired",
            f"已超过演示规则规定的 {limit} 天申请期限，需要人工判断是否存在法定或承诺例外",
            requires_human=True,
        )

    return _decision(
        True,
        "within_service_window",
        f"订单在签收后 {limit} 天服务期限内，可以提交审核",
        requires_human=data.amount_cents >= HIGH_VALUE_CENTS,
    )


def _decision(
    eligible: bool,
    code: str,
    explanation: str,
    *,
    requires_evidence: bool = False,
    requires_human: bool = False,
) -> PolicyDecision:
    return PolicyDecision(
        eligible=eligible,
        code=code,
        explanation=explanation,
        requires_evidence=requires_evidence,
        requires_human=requires_human,
    )
