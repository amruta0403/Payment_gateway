from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class MerchantBankAccount(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "merchant_bank_accounts"
    __table_args__ = (Index("ix_mba_merchant_id", "merchant_id"),)

    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("merchants.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_holder_name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Encrypted at rest
    account_number: Mapped[str] = mapped_column(Text, nullable=False)
    account_number_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    ifsc_code: Mapped[str] = mapped_column(String(11), nullable=False)
    account_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="CURRENT", server_default="CURRENT"
    )

    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Penny drop state
    penny_drop_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    penny_drop_amount: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    penny_drop_initiated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
