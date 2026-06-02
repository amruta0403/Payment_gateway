from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db.base import Base, TimestampMixin, UUIDMixin


class SettlementTransaction(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "settlement_transactions"
    __table_args__ = (
        Index("ix_st_batch_id", "batch_id"),
        Index("ix_st_transaction_id", "transaction_id"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("settlement_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Cross-service ref — no FK (payment-service owns this table)
    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fee: Mapped[int] = mapped_column(BigInteger, nullable=False)
    gst: Mapped[int] = mapped_column(BigInteger, nullable=False)
    net: Mapped[int] = mapped_column(BigInteger, nullable=False)

    batch: Mapped["SettlementBatch"] = relationship(  # type: ignore[name-defined]
        "SettlementBatch", back_populates="settlement_transactions"
    )
