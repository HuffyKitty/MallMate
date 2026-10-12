"""售后预览、确认和创建结果的数据契约。"""

from typing import Literal

from pydantic import Field

from app.core.enums import CaseStatus, CaseType
from app.schemas.common import APIModel


class CaseRequest(APIModel):
    order_id: int = Field(gt=0, description="正整数订单号")
    case_type: CaseType
    reason: str = Field(min_length=1, max_length=1000)


class CasePreviewResponse(APIModel):
    eligible: bool
    reason: str
    order_id: int
    case_type: CaseType
    application_reason: str
    decision_code: str
    requires_evidence: bool
    requires_human: bool
    policy_version: str


class ConfirmRequest(CaseRequest):
    # Literal[True] 保证只有明确确认后，请求才会进入写操作。
    confirmed: Literal[True]


class AfterSalesCaseResponse(APIModel):
    case_id: int
    order_id: int
    status: CaseStatus

