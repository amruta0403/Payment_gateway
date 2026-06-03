"""Initial kyc-service schema

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE kycs_status_enum AS ENUM ('INITIATED','PENDING','VERIFIED','REJECTED','EXPIRED');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE kyc_provider_enum AS ENUM ('MOCK','MANUAL','DIGILOCKER');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    op.create_table(
        "kyc_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_type", sa.String(30), nullable=False),
        sa.Column("status", sa.Enum(name="kycs_status_enum", create_type=False), nullable=False, server_default="INITIATED"),
        sa.Column("provider", sa.Enum(name="kyc_provider_enum", create_type=False), nullable=False, server_default="MOCK"),
        sa.Column("provider_session_id", sa.String(100), nullable=True),
        sa.Column("provider_response", postgresql.JSON, nullable=True),
        sa.Column("submitted_data", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_kycs_merchant_id", "kyc_sessions", ["merchant_id"])
    op.create_index("ix_kycs_status", "kyc_sessions", ["status"])


def downgrade() -> None:
    op.drop_table("kyc_sessions")
    op.execute("DROP TYPE IF EXISTS kyc_provider_enum")
    op.execute("DROP TYPE IF EXISTS kycs_status_enum")
