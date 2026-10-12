"""售后资格预览和确认写入接口。"""

from fastapi import APIRouter, Depends, Header

from app.api.dependencies import current_customer, get_after_sales_service
from app.models import Customer
from app.schemas.after_sales import (
    AfterSalesCaseResponse,
    CasePreviewResponse,
    CaseRequest,
    ConfirmRequest,
)
from app.services.after_sales import AfterSalesService


router = APIRouter(prefix="/after-sales", tags=["after-sales"])


@router.post("/preview", response_model=CasePreviewResponse)
def preview_after_sales(
    request: CaseRequest,
    customer: Customer = Depends(current_customer),
    after_sales: AfterSalesService = Depends(get_after_sales_service),
):
    # 预览只读，便于前端展示资格结果并请求用户明确确认。
    return after_sales.preview(
        customer.id, request.order_id, request.case_type, request.reason
    )


@router.post("/confirm", response_model=AfterSalesCaseResponse)
def confirm_after_sales(
    request: ConfirmRequest,
    idempotency_key: str = Header(min_length=8, max_length=120, alias="Idempotency-Key"),
    customer: Customer = Depends(current_customer),
    after_sales: AfterSalesService = Depends(get_after_sales_service),
) -> dict:
    case = after_sales.create(
        customer.id,
        request.order_id,
        request.case_type,
        request.reason,
        idempotency_key,
    )
    return {"case_id": case.id, "order_id": case.order_id, "status": case.status}

