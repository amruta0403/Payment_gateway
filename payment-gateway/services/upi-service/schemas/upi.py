from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from models.upi_transaction import UpiMandateFrequency, UpiMandateStatus, UpiStatus

_VPA_RE = re.compile(r"^[a-zA-Z0-9._-]+@[a-zA-Z]+$")


# ── Collect ───────────────────────────────────────────────────────────────────

class CollectRequest(BaseModel):
    payment_id: uuid.UUID
    payer_vpa: str = Field(..., description="Payer's UPI VPA, e.g. user@hdfc")
    amount: int = Field(..., gt=0, description="Amount in paise")
    description: str = Field(..., max_length=50)
    expiry_seconds: int = Field(default=300, ge=30, le=1800)
    merchant_vpa: str

    @field_validator("payer_vpa")
    @classmethod
    def validate_vpa(cls, v: str) -> str:
        if not _VPA_RE.match(v):
            raise ValueError("Invalid VPA format — expected handle@provider")
        return v.lower()

    @field_validator("merchant_vpa")
    @classmethod
    def validate_merchant_vpa(cls, v: str) -> str:
        if not _VPA_RE.match(v):
            raise ValueError("Invalid merchant VPA format")
        return v.lower()


class CollectResponse(BaseModel):
    our_ref_id: str
    npci_txn_id: str | None = None
    status: UpiStatus
    expires_at: datetime | None = None
    qr_code_base64: str | None = None


# ── Intent ────────────────────────────────────────────────────────────────────

class IntentRequest(BaseModel):
    payment_id: uuid.UUID
    amount: int = Field(..., gt=0, description="Amount in paise")
    merchant_vpa: str
    description: str = Field(..., max_length=50)

    @field_validator("merchant_vpa")
    @classmethod
    def validate_vpa(cls, v: str) -> str:
        if not _VPA_RE.match(v):
            raise ValueError("Invalid merchant VPA format")
        return v.lower()


class IntentResponse(BaseModel):
    our_ref_id: str
    upi_deep_link: str
    qr_code_base64: str | None = None
    expires_at: datetime


# ── VPA validate ──────────────────────────────────────────────────────────────

class VpaValidateResponse(BaseModel):
    vpa: str
    is_valid: bool
    account_name: str | None = None
    bank_name: str | None = None


# ── Status ────────────────────────────────────────────────────────────────────

class UpiStatusResponse(BaseModel):
    our_ref_id: str
    npci_txn_id: str | None = None
    status: UpiStatus
    completed_at: datetime | None = None
    decline_code: str | None = None
    decline_reason: str | None = None

    model_config = {"from_attributes": True}


# ── NPCI callback payload (camelCase from NPCI) ───────────────────────────────

class UpiCallbackPayload(BaseModel):
    txnId: str
    refId: str
    txnRef: str
    amount: str                  # NPCI sends as string "100.00"
    status: str                  # "SUCCESS" / "FAILURE"
    respCode: str
    respMsg: str
    payerVPA: str | None = None
    payeeVPA: str | None = None
    txnAuthDate: str | None = None

    model_config = {"populate_by_name": True}


# ── Mandate ───────────────────────────────────────────────────────────────────

class MandateCreateRequest(BaseModel):
    customer_vpa: str
    amount: int = Field(..., gt=0, description="Amount per debit in paise")
    frequency: UpiMandateFrequency
    start_date: date
    end_date: date
    description: str = Field(default="", max_length=50)

    @field_validator("customer_vpa")
    @classmethod
    def validate_vpa(cls, v: str) -> str:
        if not _VPA_RE.match(v):
            raise ValueError("Invalid VPA format")
        return v.lower()


class MandateResponse(BaseModel):
    id: uuid.UUID
    merchant_id: uuid.UUID
    customer_vpa: str           # returned unencrypted
    amount: int
    frequency: UpiMandateFrequency
    start_date: date
    end_date: date
    status: UpiMandateStatus
    mandate_ref_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MandateExecuteRequest(BaseModel):
    amount: int = Field(..., gt=0, description="Amount to debit in paise")
    description: str = Field(default="", max_length=50)
