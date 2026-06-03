from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, Index, JSON, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base import Base, TimestampMixin, UUIDMixin


class KycSessionStatus(str, Enum):
    INITIATED  = "INITIATED"
    PENDING    = "PENDING"
    VERIFIED   = "VERIFIED"
    REJECTED   = "REJECTED"
    EXPIRED    = "EXPIRED"


class KycProviderEnum(str, Enum):
    MOCK       = "MOCK"
    MANUAL     = "MANUAL"
    DIGILOCKER = "DIGILOCKER"


class KycSession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "kyc_sessions"
    __table_args__ = (
        Index("ix_kycs_merchant_id", "merchant_id"),
        Index("ix_kycs_status", "status"),
    )

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    session_type: Mapped[str] = mapped_column(String(30), nullable=False)   # PAN, GSTIN, BANK_ACCOUNT
    status: Mapped[KycSessionStatus] = mapped_column(
        SAEnum(KycSessionStatus, name="kycs_status_enum", create_type=False),
        nullable=False, default=KycSessionStatus.INITIATED,
    )
    provider: Mapped[KycProviderEnum] = mapped_column(
        SAEnum(KycProviderEnum, name="kyc_provider_enum", create_type=False),
        nullable=False, default=KycProviderEnum.MOCK,
    )
    provider_session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    submitted_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
