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
    Integer,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db.base import Base, TimestampMixin, UUIDMixin


class SettlementStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RECONCILED = "RECONCILED"


class SettlementBatch(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "settlement_batches"
    __table_args__ = (
        Index("ix_sb_merchant_id", "merchant_id"),
        Index("ix_sb_settlement_date", "settlement_date"),
        Index("ix_sb_status", "status"),
    )

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    settlement_date: Mapped[date] = mapped_column(Date, nullable=False)
    gross_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fee_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    gst_on_fee: Mapped[int] = mapped_column(BigInteger, nullable=False)
    net_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    transaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[SettlementStatus] = mapped_column(
        SAEnum(SettlementStatus, name="settlement_status_enum", create_type=False),
        nullable=False,
        default=SettlementStatus.PENDING,
    )

    settlement_transactions: Mapped[list] = relationship(
        "SettlementTransaction", back_populates="batch", lazy="select"
    )
    payouts: Mapped[list] = relationship(
        "SettlementPayout", back_populates="batch", lazy="select"
    )
