from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db.base import Base, TimestampMixin, UUIDMixin, SoftDeleteMixin
from shared.models.enums import CardNetwork, FraudDecision, PaymentMethod, TransactionStatus


class Transaction(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_transactions_idempotency_key"),
        Index("ix_transactions_merchant_id", "merchant_id"),
        Index("ix_transactions_status", "status"),
        Index("ix_transactions_order_id", "order_id"),
        Index("ix_transactions_gateway_txn_id", "gateway_txn_id"),
        Index("ix_transactions_merchant_status", "merchant_id", "status"),
        Index("ix_transactions_created_at", "created_at"),
    )

    # Core
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="INR", server_default="INR"
    )
    captured_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    refunded_amount: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )

    # Status
    status: Mapped[TransactionStatus] = mapped_column(
        SAEnum(TransactionStatus, name="transaction_status_enum", create_type=False),
        nullable=False,
        default=TransactionStatus.CREATED,
        index=True,
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        SAEnum(PaymentMethod, name="payment_method_enum", create_type=False),
        nullable=False,
    )

    # Card
    card_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    card_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    card_network: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # UPI
    upi_vpa: Mapped[str | None] = mapped_column(Text, nullable=True)  # AES-256-GCM encrypted
    upi_txn_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Netbanking / wallet
    bank_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    wallet_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    wallet_txn_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Gateway / acquirer
    gateway_txn_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    acquirer_ref_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rrn: Mapped[str | None] = mapped_column(String(50), nullable=True)
    auth_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bank_txn_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Idempotency
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    # Customer (AES-256-GCM encrypted at rest)
    customer_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Request context
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_fingerprint: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Fraud
    fraud_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    fraud_decision: Mapped[FraudDecision | None] = mapped_column(
        SAEnum(FraudDecision, name="fraud_decision_enum", create_type=False), nullable=True
    )
    rule_hits: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )

    # 3DS
    three_ds_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    three_ds_eci: Mapped[str | None] = mapped_column(String(5), nullable=True)
    three_ds_cavv: Mapped[str | None] = mapped_column(Text, nullable=True)  # encrypted
    three_ds_xid: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Metadata
    order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    merchant_metadata: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    callback_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    redirect_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Error
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Lifecycle timestamps
    authorized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    events: Mapped[list[TransactionEvent]] = relationship(
        "TransactionEvent",
        back_populates="transaction",
        lazy="select",
        cascade="all, delete-orphan",
    )


class TransactionEvent(Base):
    __tablename__ = "transaction_events"
    __table_args__ = (
        Index("ix_txn_events_transaction_id", "transaction_id"),
        Index("ix_txn_events_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_status: Mapped[TransactionStatus | None] = mapped_column(
        SAEnum(TransactionStatus, name="transaction_status_enum", create_type=False),
        nullable=True,
    )
    to_status: Mapped[TransactionStatus] = mapped_column(
        SAEnum(TransactionStatus, name="transaction_status_enum", create_type=False),
        nullable=False,
    )
    triggered_by: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

    transaction: Mapped[Transaction] = relationship("Transaction", back_populates="events")
