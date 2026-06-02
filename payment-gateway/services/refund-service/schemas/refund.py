from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from models.refund import RefundStatus, RefundType


class RefundCreateRequest(BaseModel):
    transaction_id: uuid.UUID
    amount: int = Field(..., gt=0, description="Amount to refund in paise")
    reason: str | None = Field(None, max_length=500)
    notes: str | None = Field(None, max_length=1000)
    refund_type: RefundType = RefundType.FULL
    idempotency_key: str = Field(..., min_length=8, max_length=255)


class RefundResponse(BaseModel):
    id: uuid.UUID
    transaction_id: uuid.UUID
    merchant_id: uuid.UUID
    amount: int
    currency: str
    refund_type: RefundType
    status: RefundStatus
    reason: str | None = None
    gateway_refund_id: str | None = None
    utr_number: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    processed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RefundListResponse(BaseModel):
    items: list[RefundResponse]
    total: int
    page: int
    page_size: int
