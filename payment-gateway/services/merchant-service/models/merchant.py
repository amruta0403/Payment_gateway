from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    Index,
    JSON,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin
from shared.models.enums import BusinessType, MerchantStatus

DEFAULT_FEE_CONFIG: dict = {
    "card_mdr_percent": "2.0",
    "upi_flat_fee_paise": 0,
    "netbanking_flat_fee_paise": 1000,
    "gst_percent": "18",
}


class Merchant(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "merchants"
    __table_args__ = (
        Index("ix_merchants_status", "status"),
        Index("ix_merchants_pan_hash", "pan_hash"),
        Index("ix_merchants_gstin_hash", "gstin_hash"),
        Index("ix_merchants_business_name_hash", "business_name_hash"),
    )

    # Encrypted at rest (AES-256-GCM via FieldEncryptor)
    business_name: Mapped[str] = mapped_column(Text, nullable=False)
    pan: Mapped[str | None] = mapped_column(Text, nullable=True)
    gstin: Mapped[str | None] = mapped_column(Text, nullable=True)
    support_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    support_phone: Mapped[str | None] = mapped_column(Text, nullable=True)

    # SHA-256 hashes for searchable lookup (no decryption needed for search)
    business_name_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pan_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gstin_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Plain fields
    business_type: Mapped[BusinessType] = mapped_column(
        SAEnum(BusinessType, name="business_type_enum", create_type=False),
        nullable=False,
    )
    status: Mapped[MerchantStatus] = mapped_column(
        SAEnum(MerchantStatus, name="merchant_status_enum", create_type=False),
        nullable=False,
        default=MerchantStatus.DRAFT,
        index=True,
    )
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    business_category: Mapped[str | None] = mapped_column(String(10), nullable=True)  # MCC

    # Fee configuration (JSONB)
    fee_config: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: dict(DEFAULT_FEE_CONFIG),
        server_default=text("'{}'::json"),
    )

    # Keycloak group for RBAC
    keycloak_group_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Display metadata
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
