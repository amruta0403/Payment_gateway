from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class VaultBase(DeclarativeBase):
    pass


class CardToken(VaultBase):
    __tablename__ = "card_tokens"
    __table_args__ = (
        Index("ix_card_tokens_fingerprint_merchant", "pan_fingerprint", "merchant_id"),
        Index("ix_card_tokens_merchant_id", "merchant_id"),
        Index("ix_card_tokens_customer_id", "customer_id"),
        Index("ix_card_tokens_is_active", "is_active"),
        UniqueConstraint("token", name="uq_card_tokens_token"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4
    )

    # Encrypted storage — AES-256-GCM, format "v{version}:{base64(nonce+ct)}"
    pan_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1"
    )

    # Safe searchable fields (never raw PAN)
    pan_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    pan_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    pan_first6: Mapped[str | None] = mapped_column(String(6), nullable=True)
    pan_length: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=16, server_default="16"
    )

    # Card details
    expiry_month: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    expiry_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    cardholder_name: Mapped[str | None] = mapped_column(Text, nullable=True)  # encrypted

    # Network / category
    card_network: Mapped[str | None] = mapped_column(String(20), nullable=True)
    card_category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    issuer_bank: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issuer_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    is_domestic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Ownership
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    usage_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )


class VaultAccessLog(VaultBase):
    """Append-only audit log. NEVER UPDATE OR DELETE rows here."""
    __tablename__ = "vault_access_log"
    __table_args__ = (
        Index("ix_val_card_token", "card_token"),
        Index("ix_val_created_at", "created_at"),
        Index("ix_val_operation", "operation"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    card_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    requesting_service: Mapped[str | None] = mapped_column(String(50), nullable=True)
    requesting_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )


class BinDatabase(VaultBase):
    """BIN (Bank Identification Number) lookup table, seeded from BIN list."""
    __tablename__ = "bin_database"

    bin: Mapped[str] = mapped_column(String(6), primary_key=True)
    card_network: Mapped[str | None] = mapped_column(String(20), nullable=True)
    card_category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    issuer_bank: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issuer_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    is_domestic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
