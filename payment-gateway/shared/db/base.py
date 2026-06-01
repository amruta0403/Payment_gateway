from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=True,
    )


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )


class BaseModel(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __abstract__ = True

    __table_args__ = (
        Index(None, "is_deleted"),
    )


async def set_rls_context(
    conn,
    merchant_id: str | None = None,
    is_admin: bool = False,
) -> None:
    if is_admin:
        await conn.execute(
            text("SET LOCAL app.current_user_is_admin = 'true'")
        )
    else:
        await conn.execute(
            text("SET LOCAL app.current_user_is_admin = 'false'")
        )
    if merchant_id:
        await conn.execute(
            text(f"SET LOCAL app.current_merchant_id = '{merchant_id}'")
        )
