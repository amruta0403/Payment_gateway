from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum as SAEnum, Index,
    JSON, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base import Base, UUIDMixin


class RefundStatus(str, Enum):
    INITIATED        = "INITIATED"
    PROCESSING       = "PROCESSING"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    SUCCESS          = "SUCCESS"
    FAILED           = "FAILED"
    REVERSED         = "REVERSED"


class RefundType(str, Enum):
    FULL               = "FULL"
    PARTIAL            = "PARTIAL"
    MERCHANT_INIT      = "MERCHANT_INIT"
    CUSTOMER_INIT      = "CUSTOMER_INIT"
    CHARGEBACK_REVERSAL = "CHARGEBACK_REVERSAL"


class Refund(UUIDMixin, Base):
    __tablename__ = "refunds"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_refunds_idempotency_key"),
        Index("ix_refunds_transaction_id",   "transaction_id"),
        Index("ix_refunds_merchant_id",      "merchant_id"),
        Index("ix_refunds_status",           "status"),
        Index("ix_refunds_created_at",       "created_at"),
        Index("ix_refunds_merchant_status",  "merchant_id", "status"),
        Index("ix_refunds_gateway_id",       "gateway_refund_id"),
    )

    # Cross-service refs — no FK (payment-service owns transactions)
    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR", server_default="INR")

    refund_type: Mapped[RefundType] = mapped_column(
        SAEnum(RefundType, name="refund_type_enum", create_type=False),
        nullable=False, default=RefundType.FULL,
    )
    status: Mapped[RefundStatus] = mapped_column(
        SAEnum(RefundStatus, name="refund_status_enum", create_type=False),
        nullable=False, default=RefundStatus.INITIATED,
    )

    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Acquirer / gateway
    gateway_refund_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utr_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    acquirer_rrn: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Who initiated
    initiated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Error
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Idempotency
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)

    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    metadata_: Mapped[dict] = mapped_column("metadata", JSON, nullable=False,
                                             default=dict, server_default="{}")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False,
                                              default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
