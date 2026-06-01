from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from shared.models.enums import CardCategory, CardNetwork


def _luhn_ok(number: str) -> bool:
    total = 0
    for i, ch in enumerate(number[::-1]):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


class TokenizeRequest(BaseModel):
    """
    PCI-sensitive request body.
    pan and cvv are validated then immediately discarded after use —
    they must NEVER be logged, stored, or returned.
    """
    pan: str = Field(..., description="16-digit PAN — Luhn validated, never stored raw")
    expiry_month: int = Field(..., ge=1, le=12)
    expiry_year: int = Field(..., ge=2024, le=2099)
    cvv: str = Field(..., pattern=r"^\d{3,4}$", description="Used once, never stored")
    cardholder_name: str | None = Field(None, max_length=200)
    merchant_id: uuid.UUID
    customer_id: uuid.UUID | None = None

    @field_validator("pan")
    @classmethod
    def validate_pan(cls, v: str) -> str:
        digits = re.sub(r"[\s\-]", "", v)
        if not digits.isdigit():
            raise ValueError("PAN must contain only digits")
        if len(digits) != 16:
            raise ValueError("PAN must be 16 digits")
        if not _luhn_ok(digits):
            raise ValueError("Invalid PAN (Luhn check failed)")
        return digits


class TokenizeResponse(BaseModel):
    """Safe response — NEVER contains PAN, CVV, or full card number."""
    token: uuid.UUID
    last4: str
    first6: str
    card_network: CardNetwork
    card_category: CardCategory
    issuer_bank: str | None = None
    is_domestic: bool
    expires_at: date | None = None


class CardMetadataResponse(BaseModel):
    """Safe card metadata for display. NEVER contains PAN."""
    token: uuid.UUID
    last4: str
    first6: str
    card_network: CardNetwork
    card_category: CardCategory
    issuer_bank: str | None = None
    expiry_month: int | None = None
    expiry_year: int | None = None
    is_domestic: bool
    is_active: bool
    usage_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ChargeDataRequest(BaseModel):
    """
    Internal-only: request decrypted PAN for acquirer charge.
    No CVV field — CVV is never stored and cannot be returned.
    """
    token: uuid.UUID


class ChargeDataResponse(BaseModel):
    """
    Decrypted PAN + expiry for acquirer.
    NO CVV — cardholder must re-enter for card-on-file charges.
    This response must never be cached or logged.
    """
    pan: str = Field(..., description="Decrypted PAN — never log or cache this")
    expiry_month: int
    expiry_year: int


class RotateKeyRequest(BaseModel):
    new_key_version: int = Field(..., ge=1, le=99)


class RotationStatusResponse(BaseModel):
    job_id: str
    status: str            # started | in_progress | completed | failed
    old_version: int | None = None
    new_version: int | None = None
    total_tokens: int = 0
    processed: int = 0
    failed_count: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


class DeleteCardResponse(BaseModel):
    token: uuid.UUID
    status: str = "deleted"
