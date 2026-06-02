from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base import Base, TimestampMixin, UUIDMixin


class UpiStatus(str, Enum):
    INITIATED = "INITIATED"
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class UpiMandateStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class UpiMandateFrequency(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


# ── upi_transactions ──────────────────────────────────────────────────────────

class UpiTransaction(UUIDMixin, Base):
    __tablename__ = "upi_transactions"
    __table_args__ = (
        UniqueConstraint("our_ref_id", name="uq_upi_txn_ref_id"),
        Index("ix_upi_txn_transaction_id", "transaction_id"),
        Index("ix_upi_txn_merchant_id", "merchant_id"),
        Index("ix_upi_txn_status", "status"),
    )

    # Cross-service reference (no FK — payment-service owns the payment)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    our_ref_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    npci_txn_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Encrypted PII
    vpa_payer: Mapped[str | None] = mapped_column(Text, nullable=True)
    payer_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    vpa_payee: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)

    status: Mapped[UpiStatus] = mapped_column(
        SAEnum(UpiStatus, name="upi_status_enum", create_type=False),
        nullable=False,
        default=UpiStatus.INITIATED,
    )

    collect_expiry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    upi_deep_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    qr_code_base64: Mapped[str | None] = mapped_column(Text, nullable=True)

    decline_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    decline_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    initiated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default="NOW()",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    callback_received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    raw_callback: Mapped[dict | None] = mapped_column(JSON, nullable=True)


# ── merchant_vpas ─────────────────────────────────────────────────────────────

class MerchantVpa(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "merchant_vpas"
    __table_args__ = (
        UniqueConstraint("vpa", name="uq_merchant_vpas_vpa"),
        Index("ix_merchant_vpas_merchant_id", "merchant_id"),
    )

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vpa: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


# ── upi_mandates ──────────────────────────────────────────────────────────────

class UpiMandate(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "upi_mandates"
    __table_args__ = (
        Index("ix_upi_mandates_merchant_id", "merchant_id"),
        Index("ix_upi_mandates_status", "status"),
    )

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # Encrypted at rest
    customer_vpa: Mapped[str] = mapped_column(Text, nullable=False)

    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    frequency: Mapped[UpiMandateFrequency] = mapped_column(
        SAEnum(UpiMandateFrequency, name="upi_mandate_frequency_enum", create_type=False),
        nullable=False,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[UpiMandateStatus] = mapped_column(
        SAEnum(UpiMandateStatus, name="upi_mandate_status_enum", create_type=False),
        nullable=False,
        default=UpiMandateStatus.PENDING,
    )
    mandate_ref_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
