from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class TransactionResponse(BaseModel):
    id: uuid.UUID
    merchant_id: uuid.UUID
    amount: int
    currency: str
    captured_amount: int | None = None
    refunded_amount: int
    status: str
    payment_method: str
    card_last4: str | None = None
    card_network: str | None = None
    upi_vpa: str | None = None
    bank_code: str | None = None
    gateway_txn_id: str | None = None
    order_id: str | None = None
    rrn: str | None = None
    description: str | None = None
    fraud_score: float | None = None
    error_code: str | None = None
    error_message: str | None = None
    authorized_at: datetime | None = None
    captured_at: datetime | None = None
    settled_at: datetime | None = None
    failed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class TransactionStats(BaseModel):
    merchant_id: uuid.UUID
    period: str                     # "today" | "7d" | "30d"
    total_count: int
    success_count: int
    failed_count: int
    total_amount_paise: int
    captured_amount_paise: int
    refunded_amount_paise: int
    success_rate_pct: float
    avg_ticket_paise: int
    by_method: dict[str, int]       # method → count
    by_status: dict[str, int]       # status → count


class DailyVolume(BaseModel):
    date: str
    count: int
    amount_paise: int
    success_count: int
