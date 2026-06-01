from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator, model_validator

from shared.models.enums import CardNetwork, FraudDecision, PaymentMethod, TransactionStatus


def _luhn_check(number: str) -> bool:
    digits = [int(d) for d in number]
    digits.reverse()
    total = 0
    for i, digit in enumerate(digits):
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


class CardDetails(BaseModel):
    number: str = Field(..., description="16-digit PAN")
    expiry_month: int = Field(..., ge=1, le=12)
    expiry_year: int = Field(..., ge=2024)
    cvv: str = Field(..., pattern=r"^\d{3,4}$")
    cardholder_name: str | None = None

    @field_validator("number")
    @classmethod
    def validate_card_number(cls, v: str) -> str:
        digits = re.sub(r"[\s\-]", "", v)
        if not digits.isdigit():
            raise ValueError("Card number must contain only digits")
        if len(digits) != 16:
            raise ValueError("Card number must be 16 digits")
        if not _luhn_check(digits):
            raise ValueError("Invalid card number (Luhn check failed)")
        return digits


class CustomerDetails(BaseModel):
    email: EmailStr
    phone: str = Field(..., pattern=r"^\+91[6-9]\d{9}$", description="E.164 Indian mobile")
    name: str | None = None


class PaymentCreateRequest(BaseModel):
    amount: int = Field(..., gt=0, le=10_000_000, description="Amount in paise (max ₹1 lakh)")
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    payment_method: PaymentMethod
    card: CardDetails | None = None
    upi_vpa: str | None = Field(
        None, pattern=r"^[a-zA-Z0-9._\-]+@[a-zA-Z]+$", description="UPI VPA"
    )
    bank_code: str | None = Field(None, max_length=20)
    customer: CustomerDetails
    order_id: str | None = Field(None, max_length=100)
    description: str | None = Field(None, max_length=500)
    callback_url: HttpUrl | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_method_fields(self) -> PaymentCreateRequest:
        if self.payment_method == PaymentMethod.CARD and not self.card:
            raise ValueError("card details required for CARD payment method")
        if self.payment_method == PaymentMethod.NETBANKING and not self.bank_code:
            raise ValueError("bank_code required for NETBANKING payment method")
        return self


class PaymentResponse(BaseModel):
    id: uuid.UUID
    merchant_id: uuid.UUID
    amount: int
    currency: str
    status: TransactionStatus
    payment_method: PaymentMethod
    card_last4: str | None = None
    card_network: str | None = None
    order_id: str | None = None
    gateway_txn_id: str | None = None
    fraud_score: Decimal | None = None
    created_at: datetime
    updated_at: datetime | None = None
    action_required: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class PaymentListResponse(BaseModel):
    items: list[PaymentResponse]
    total: int
    cursor: str | None = None


class CaptureRequest(BaseModel):
    amount: int | None = Field(
        None, gt=0, description="Partial capture in paise. Omit to capture full amount."
    )


class TransactionEventResponse(BaseModel):
    id: int
    transaction_id: uuid.UUID
    from_status: TransactionStatus | None = None
    to_status: TransactionStatus
    triggered_by: str
    actor_id: uuid.UUID | None = None
    message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}
