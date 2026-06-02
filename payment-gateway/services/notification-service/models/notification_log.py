from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    DateTime, Enum as SAEnum, Index, JSON, SmallInteger, String, Text, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base import Base, UUIDMixin


class NotificationType(str, Enum):
    PAYMENT_SUCCESS   = "PAYMENT_SUCCESS"
    PAYMENT_FAILED    = "PAYMENT_FAILED"
    REFUND_INITIATED  = "REFUND_INITIATED"
    REFUND_COMPLETED  = "REFUND_COMPLETED"
    SETTLEMENT_ADVICE = "SETTLEMENT_ADVICE"
    KYC_APPROVED      = "KYC_APPROVED"
    KYC_REJECTED      = "KYC_REJECTED"


class NotificationChannel(str, Enum):
    EMAIL    = "EMAIL"
    SMS      = "SMS"
    PUSH     = "PUSH"
    WEBHOOK  = "WEBHOOK"


class NotificationStatus(str, Enum):
    PENDING    = "PENDING"
    QUEUED     = "QUEUED"
    SENT       = "SENT"
    DELIVERED  = "DELIVERED"
    FAILED     = "FAILED"
    SUPPRESSED = "SUPPRESSED"


class NotificationLog(UUIDMixin, Base):
    __tablename__ = "notification_logs"
    __table_args__ = (
        Index("ix_notif_event_id",    "event_id"),
        Index("ix_notif_merchant_id", "merchant_id"),
        Index("ix_notif_status",      "status"),
        Index("ix_notif_created_at",  "created_at"),
    )

    # Source event that triggered this notification
    event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    merchant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    notification_type: Mapped[NotificationType] = mapped_column(
        SAEnum(NotificationType, name="notification_type_enum", create_type=False),
        nullable=False,
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        SAEnum(NotificationChannel, name="notification_channel_enum", create_type=False),
        nullable=False,
    )

    recipient: Mapped[str] = mapped_column(Text, nullable=False)  # encrypted
    template_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)

    status: Mapped[NotificationStatus] = mapped_column(
        SAEnum(NotificationStatus, name="notification_status_enum", create_type=False),
        nullable=False,
        default=NotificationStatus.PENDING,
    )

    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
