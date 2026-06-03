"""Initial netbanking-service schema

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
            CREATE TYPE nbs_status_enum AS ENUM
                ('INITIATED','REDIRECTED','SUCCESS','FAILED','EXPIRED','CANCELLED');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    op.create_table(
        "netbanking_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bank_code", sa.String(20), nullable=False),
        sa.Column("amount", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("status", sa.Enum(name="nbs_status_enum", create_type=False), nullable=False, server_default="INITIATED"),
        sa.Column("redirect_url", sa.Text, nullable=True),
        sa.Column("return_url", sa.Text, nullable=True),
        sa.Column("bank_txn_id", sa.String(100), nullable=True),
        sa.Column("bank_ref", sa.String(100), nullable=True),
        sa.Column("callback_payload", postgresql.JSON, nullable=True),
        sa.Column("initiated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_nbs_merchant_id", "netbanking_sessions", ["merchant_id"])
    op.create_index("ix_nbs_transaction_id", "netbanking_sessions", ["transaction_id"])
    op.create_index("ix_nbs_status", "netbanking_sessions", ["status"])


def downgrade() -> None:
    op.drop_table("netbanking_sessions")
    op.execute("DROP TYPE IF EXISTS nbs_status_enum")
