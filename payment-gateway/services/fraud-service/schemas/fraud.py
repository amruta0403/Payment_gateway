from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FraudDecision(str, Enum):
    ALLOW = "ALLOW"
    CHALLENGE = "CHALLENGE"
    BLOCK = "BLOCK"


class ScoringRequest(BaseModel):
    payment_id: uuid.UUID
    merchant_id: uuid.UUID
    merchant_created_at: datetime | None = None
    merchant_mcc: str | None = None
    amount: int = Field(..., gt=0, description="Amount in paise")
    card_token: uuid.UUID | None = None
    card_fingerprint: str | None = None
    pan_first6: str | None = Field(None, min_length=6, max_length=6)
    upi_vpa: str | None = None
    payment_method: str
    ip_address: str
    user_agent: str | None = None
    device_fingerprint: str | None = None
    customer_email_hash: str | None = None
    customer_phone_hash: str | None = None
    billing_country: str | None = None


class ScoringContext(ScoringRequest):
    """Internal context object passed through rules engine and ML scorer."""
    pass


class ScoringResult(BaseModel):
    fraud_score: float = Field(..., ge=0.0, le=1.0)
    decision: FraudDecision
    reasons: list[str]
    rule_hits: list[str]
    evaluated_at: datetime


class BlacklistAddRequest(BaseModel):
    value: str = Field(..., min_length=1, max_length=255)


class RuleResponse(BaseModel):
    id: uuid.UUID
    rule_name: str
    is_active: bool
    description: str | None = None
    weight: float
    hit_count: int
    created_at: datetime

    model_config = {"from_attributes": True}
