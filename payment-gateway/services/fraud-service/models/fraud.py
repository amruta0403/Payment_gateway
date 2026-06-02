from __future__ import annotations

from sqlalchemy import Boolean, Float, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base import Base, TimestampMixin, UUIDMixin


class FraudBlacklist(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "fraud_blacklist"
    __table_args__ = (
        Index("ix_fraud_bl_list_type_value", "list_type", "value"),
    )

    list_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class FraudRule(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "fraud_rules"
    __table_args__ = (
        UniqueConstraint("rule_name", name="uq_fraud_rules_rule_name"),
    )

    rule_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, server_default="1.0")
