from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db.base import Base, TimestampMixin, UUIDMixin


class PayoutMethod(str, Enum):
    IMPS = "IMPS"
    NEFT = "NEFT"
    RTGS = "RTGS"


class PayoutStatus(str, Enum):
    INITIATED = "INITIATED"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class SettlementPayout(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "settlement_payouts"
    __table_args__ = (
        Index("ix_sp_batch_id", "batch_id"),
        Index("ix_sp_status", "status"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("settlement_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Cross-service ref — no FK (merchant-service owns this table)
    merchant_bank_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payout_method: Mapped[PayoutMethod] = mapped_column(
        SAEnum(PayoutMethod, name="payout_method_enum", create_type=False),
        nullable=False,
        default=PayoutMethod.IMPS,
    )
    status: Mapped[PayoutStatus] = mapped_column(
        SAEnum(PayoutStatus, name="payout_status_enum", create_type=False),
        nullable=False,
        default=PayoutStatus.INITIATED,
    )
    utr_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    initiated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=text("NOW()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    batch: Mapped["SettlementBatch"] = relationship(  # type: ignore[name-defined]
        "SettlementBatch", back_populates="payouts"
    )
