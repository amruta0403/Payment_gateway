from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from models.settlement_batch import SettlementStatus
from models.settlement_payout import PayoutMethod, PayoutStatus


class SettlementBatchResponse(BaseModel):
    id: uuid.UUID
    merchant_id: uuid.UUID
    settlement_date: date
    gross_amount: int
    fee_amount: int
    gst_on_fee: int
    net_amount: int
    transaction_count: int
    status: SettlementStatus
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class SettlementTransactionResponse(BaseModel):
    id: uuid.UUID
    batch_id: uuid.UUID
    transaction_id: uuid.UUID
    amount: int
    fee: int
    gst: int
    net: int

    model_config = {"from_attributes": True}


class SettlementPayoutResponse(BaseModel):
    id: uuid.UUID
    batch_id: uuid.UUID
    amount: int
    payout_method: PayoutMethod
    status: PayoutStatus
    utr_number: str | None = None
    failure_reason: str | None = None
    initiated_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class SettlementBatchDetail(SettlementBatchResponse):
    transactions: list[SettlementTransactionResponse] = []
    payouts: list[SettlementPayoutResponse] = []


class TriggerSettlementRequest(BaseModel):
    settlement_date: date = Field(default_factory=lambda: datetime.utcnow().date())


class RetryPayoutRequest(BaseModel):
    batch_id: uuid.UUID


class MonthlySummaryItem(BaseModel):
    month: str                 # "2025-01"
    batch_count: int
    total_gross: int
    total_fee: int
    total_gst: int
    total_net: int
    transaction_count: int


class RbiReportRow(BaseModel):
    batch_id: str
    merchant_id: str
    settlement_date: str
    gross_amount_paise: int
    fee_paise: int
    gst_paise: int
    net_paise: int
    transaction_count: int
    utr_number: str
    status: str
