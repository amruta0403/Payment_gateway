from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin
from shared.models.enums import KycDocumentStatus, KycDocumentType


class KycDocument(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "kyc_documents"
    __table_args__ = (
        Index("ix_kyc_docs_merchant_id", "merchant_id"),
        Index("ix_kyc_docs_status", "status"),
        Index("ix_kyc_docs_document_type", "document_type"),
    )

    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("merchants.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_type: Mapped[KycDocumentType] = mapped_column(
        SAEnum(KycDocumentType, name="kyc_document_type_enum", create_type=False),
        nullable=False,
    )
    status: Mapped[KycDocumentStatus] = mapped_column(
        SAEnum(KycDocumentStatus, name="kyc_document_status_enum", create_type=False),
        nullable=False,
        default=KycDocumentStatus.PENDING,
    )

    # S3/R2 storage — path encrypted so bucket structure is opaque
    s3_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Review
    verified_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
