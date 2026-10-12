"""售后资格检查、幂等创建和创建后回查。"""

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import CaseType
from app.core.exceptions import BusinessRuleError, ConflictError
from app.domain.after_sales_policy import PolicyInput, evaluate_after_sales
from app.models import AfterSalesCase
from app.repositories.after_sales import AfterSalesRepository
from app.services.orders import OrderService


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    reason: str
    order_id: int
    case_type: CaseType
    application_reason: str
    decision_code: str
    requires_evidence: bool
    requires_human: bool
    policy_version: str


class AfterSalesService:
    def __init__(
        self,
        db: Session,
        cases: AfterSalesRepository,
        orders: OrderService,
    ):
        self.db = db
        self.cases = cases
        self.orders = orders

    def preview(
        self,
        customer_id: int,
        order_id: int,
        case_type: CaseType,
        reason: str,
    ) -> EligibilityResult:
        """执行确定性资格规则，不进行任何写操作。"""

        order = self.orders.get_owned_order(customer_id, order_id)
        clean_reason = reason.strip()
        decision = evaluate_after_sales(
            PolicyInput(
                order_status=order.status,
                case_type=case_type,
                reason=clean_reason,
                amount_cents=order.amount_cents,
                delivered_at=order.delivered_at,
                all_items_returnable=all(item.product.returnable for item in order.items),
            )
        )
        return EligibilityResult(
            eligible=decision.eligible,
            reason=decision.explanation,
            order_id=order.id,
            case_type=case_type,
            application_reason=clean_reason,
            decision_code=decision.code,
            requires_evidence=decision.requires_evidence,
            requires_human=decision.requires_human,
            policy_version=decision.policy_version,
        )

    def create(
        self,
        customer_id: int,
        order_id: int,
        case_type: CaseType,
        reason: str,
        idempotency_key: str,
    ) -> AfterSalesCase:
        """重新校验资格后创建申请，相同幂等请求返回首次创建的结果。"""

        clean_reason = reason.strip()
        request_hash = self._request_hash(order_id, case_type, clean_reason)
        existing = self.cases.get_by_idempotency_key(customer_id, idempotency_key)
        if existing is not None:
            # 重试请求优先返回首次成功结果，避免订单状态变化后破坏幂等语义。
            return self._validate_existing(existing, request_hash)

        preview = self.preview(customer_id, order_id, case_type, clean_reason)
        if not preview.eligible:
            raise BusinessRuleError(preview.reason)

        case = AfterSalesCase(
            order_id=order_id,
            customer_id=customer_id,
            case_type=case_type,
            reason=clean_reason,
            request_hash=request_hash,
            idempotency_key=idempotency_key,
        )
        self.cases.add(case)
        try:
            self.db.commit()
        except IntegrityError:
            # 并发请求可能同时通过上面的预查询，数据库唯一约束负责最后兜底。
            self.db.rollback()
            existing = self.cases.get_by_idempotency_key(customer_id, idempotency_key)
            if existing is not None:
                return self._validate_existing(existing, request_hash)
            raise ConflictError("申请重复或幂等键冲突") from None

        self.db.refresh(case)
        verified = self.cases.get_owned(customer_id, case.id)
        if verified is None:
            raise RuntimeError("申请创建后回查失败")
        return verified

    @staticmethod
    def _request_hash(order_id: int, case_type: CaseType, reason: str) -> str:
        payload = [order_id, case_type, reason]
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _validate_existing(case: AfterSalesCase, request_hash: str) -> AfterSalesCase:
        if case.request_hash != request_hash:
            raise ConflictError("幂等键已用于其他申请")
        return case

