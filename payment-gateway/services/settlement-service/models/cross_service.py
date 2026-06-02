"""
Read-only SQLAlchemy models for tables owned by other services.
Used by Celery tasks that query the shared main DB.
No FK constraints — other services own the lifecycle.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    JSON,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base import Base, UUIDMixin


class Transaction(UUIDMixin, Base):
    """Mirror of payment-service.transactions (read-only from settlement)."""
    __tablename__ = "transactions"
    __table_args__ = {"extend_existing": True}

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    captured_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)
    captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Merchant(UUIDMixin, Base):
    """Mirror of merchant-service.merchants (read-only from settlement)."""
    __tablename__ = "merchants"
    __table_args__ = {"extend_existing": True}

    fee_config: Mapped[dict] = mapped_column(JSON, nullable=False, server_default="{}")


class MerchantBankAccount(UUIDMixin, Base):
    """Mirror of merchant-service.merchant_bank_accounts (read-only from settlement)."""
    __tablename__ = "merchant_bank_accounts"
    __table_args__ = {"extend_existing": True}

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    account_number: Mapped[str] = mapped_column(Text, nullable=False)
    ifsc_code: Mapped[str] = mapped_column(String(11), nullable=False)
    account_holder_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
