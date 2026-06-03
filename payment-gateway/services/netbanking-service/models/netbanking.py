from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Index, Integer, JSON, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base import Base, UUIDMixin


class NetbankingSessionStatus(str, Enum):
    INITIATED = "INITIATED"
    REDIRECTED = "REDIRECTED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class NetbankingSession(UUIDMixin, Base):
    __tablename__ = "netbanking_sessions"
    __table_args__ = (
        Index("ix_nbs_merchant_id", "merchant_id"),
        Index("ix_nbs_transaction_id", "transaction_id"),
        Index("ix_nbs_status", "status"),
    )

    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    bank_code: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")
    status: Mapped[NetbankingSessionStatus] = mapped_column(
        SAEnum(NetbankingSessionStatus, name="nbs_status_enum", create_type=False),
        nullable=False, default=NetbankingSessionStatus.INITIATED,
    )
    redirect_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    return_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    bank_txn_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bank_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    callback_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
