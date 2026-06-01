from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator

from shared.models.enums import (
    BusinessType,
    KycDocumentStatus,
    KycDocumentType,
    MerchantStatus,
)

_PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


# ── Merchant ──────────────────────────────────────────────────────────────────

class MerchantRegisterRequest(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=200)
    business_type: BusinessType
    pan: str = Field(..., description="10-char PAN (e.g. ABCDE1234F)")
    gstin: str | None = Field(None, description="15-char GSTIN (optional)")
    website_url: str | None = Field(None, max_length=500)
    support_email: EmailStr
    support_phone: str = Field(..., pattern=r"^\+91[6-9]\d{9}$")
    business_category: str | None = Field(None, max_length=10, description="MCC code")

    @field_validator("pan")
    @classmethod
    def validate_pan(cls, v: str) -> str:
        v = v.upper().strip()
        if not _PAN_RE.match(v):
            raise ValueError("Invalid PAN format (expected: ABCDE1234F)")
        return v

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.upper().strip()
        if not _GSTIN_RE.match(v):
            raise ValueError("Invalid GSTIN format")
        return v


class MerchantUpdateRequest(BaseModel):
    website_url: str | None = None
    support_email: EmailStr | None = None
    support_phone: str | None = Field(None, pattern=r"^\+91[6-9]\d{9}$")
    display_name: str | None = Field(None, max_length=200)
    logo_url: str | None = Field(None, max_length=500)
    business_category: str | None = Field(None, max_length=10)


class OnboardingChecklist(BaseModel):
    pan_verified: bool = False
    gstin_verified: bool = False
    bank_account_added: bool = False
    bank_verified: bool = False
    kyc_docs_uploaded: bool = False
    kyc_approved: bool = False

    @property
    def is_complete(self) -> bool:
        return all([
            self.pan_verified,
            self.bank_account_added,
            self.bank_verified,
            self.kyc_docs_uploaded,
            self.kyc_approved,
        ])


class MerchantResponse(BaseModel):
    id: uuid.UUID
    business_name: str          # decrypted
    business_type: BusinessType
    status: MerchantStatus
    website_url: str | None = None
    support_email: str | None = None   # decrypted, masked
    support_phone: str | None = None   # decrypted, masked
    business_category: str | None = None
    fee_config: dict[str, Any]
    keycloak_group_id: str | None = None
    display_name: str | None = None
    logo_url: str | None = None
    onboarding_checklist: OnboardingChecklist
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Bank account ──────────────────────────────────────────────────────────────

class BankAccountRequest(BaseModel):
    account_holder_name: str = Field(..., min_length=2, max_length=200)
    account_number: str = Field(..., min_length=9, max_length=18, pattern=r"^\d+$")
    ifsc_code: str = Field(..., pattern=r"^[A-Z]{4}0[A-Z0-9]{6}$")
    account_type: str = Field(default="CURRENT", pattern=r"^(CURRENT|SAVINGS)$")

    @field_validator("ifsc_code")
    @classmethod
    def upper_ifsc(cls, v: str) -> str:
        return v.upper()


class BankAccountResponse(BaseModel):
    id: uuid.UUID
    merchant_id: uuid.UUID
    account_holder_name: str
    account_number_last4: str      # only last 4 digits
    ifsc_code: str
    account_type: str
    is_primary: bool
    is_verified: bool
    verified_at: datetime | None = None
    penny_drop_initiated_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PennyDropResponse(BaseModel):
    status: str
    expected_amount_paise: int | None = None
    message: str


class PennyDropVerifyRequest(BaseModel):
    stated_amount_paise: int = Field(..., ge=1, le=2)


class PennyDropVerifyResponse(BaseModel):
    verified: bool
    message: str


# ── KYC ───────────────────────────────────────────────────────────────────────

class KycDocumentResponse(BaseModel):
    id: uuid.UUID
    merchant_id: uuid.UUID
    document_type: KycDocumentType
    status: KycDocumentStatus
    file_size_bytes: int | None = None
    mime_type: str | None = None
    original_filename: str | None = None
    verified_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class KycRejectRequest(BaseModel):
    rejection_reason: str = Field(..., min_length=10, max_length=500)


# ── API keys ──────────────────────────────────────────────────────────────────

class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    environment: str = Field(default="SANDBOX", pattern=r"^(LIVE|SANDBOX)$")
    permissions: list[str] = Field(default_factory=list)


class ApiKeyCreateResponse(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    full_key: str = Field(..., description="Shown ONCE — store securely, cannot be retrieved again")
    warning: str = "This key will not be shown again. Store it securely."
    environment: str
    permissions: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyListItem(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    environment: str
    permissions: list[str]
    is_active: bool
    last_used_at: datetime | None = None
    usage_count: int
    expires_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Webhooks ──────────────────────────────────────────────────────────────────

class WebhookCreateRequest(BaseModel):
    url: HttpUrl
    events: list[str] = Field(..., min_length=1)

    @field_validator("url")
    @classmethod
    def must_be_https(cls, v: HttpUrl) -> HttpUrl:
        if str(v).startswith("http://"):
            raise ValueError("Webhook URL must use HTTPS")
        return v


class WebhookCreateResponse(BaseModel):
    id: uuid.UUID
    url: str
    events: list[str]
    webhook_secret: str = Field(..., description="Shown ONCE — use to verify HMAC signatures")
    warning: str = "This secret will not be shown again. Store it securely."
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookListItem(BaseModel):
    id: uuid.UUID
    url: str
    events: list[str]
    is_active: bool
    last_triggered_at: datetime | None = None
    failure_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Dashboard ─────────────────────────────────────────────────────────────────

class DailyVolume(BaseModel):
    date: str
    volume_paise: int
    count: int


class DashboardResponse(BaseModel):
    merchant_id: uuid.UUID
    today_volume_paise: int
    today_count: int
    today_success_rate_pct: float
    last_7_days: list[DailyVolume]
    pending_settlements_paise: int
    last_5_transactions: list[dict[str, Any]]
