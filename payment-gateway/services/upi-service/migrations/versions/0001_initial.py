"""Initial UPI service schema

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000
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
    # ── Enum types ────────────────────────────────────────────────────────────
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE upi_status_enum AS ENUM
                ('INITIATED','PENDING','SUCCESS','FAILED','EXPIRED');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE upi_mandate_status_enum AS ENUM
                ('PENDING','ACTIVE','PAUSED','REVOKED','EXPIRED');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE upi_mandate_frequency_enum AS ENUM
                ('DAILY','WEEKLY','MONTHLY');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # ── upi_transactions ──────────────────────────────────────────────────────
    op.create_table(
        "upi_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("merchant_id",    postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("our_ref_id",  sa.String(50),  nullable=False),
        sa.Column("npci_txn_id", sa.String(100), nullable=True),
        sa.Column("vpa_payer",   sa.Text,         nullable=True),
        sa.Column("payer_name",  sa.Text,         nullable=True),
        sa.Column("vpa_payee",   sa.String(100),  nullable=False),
        sa.Column("amount",      sa.BigInteger,   nullable=False),
        sa.Column("status",
                  sa.Enum(name="upi_status_enum", create_type=False),
                  nullable=False, server_default="INITIATED"),
        sa.Column("collect_expiry_at",    sa.DateTime(timezone=True), nullable=True),
        sa.Column("upi_deep_link",        sa.Text,                    nullable=True),
        sa.Column("qr_code_base64",       sa.Text,                    nullable=True),
        sa.Column("decline_code",         sa.String(10),              nullable=True),
        sa.Column("decline_reason",       sa.Text,                    nullable=True),
        sa.Column("initiated_at",         sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
        sa.Column("completed_at",         sa.DateTime(timezone=True), nullable=True),
        sa.Column("callback_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_callback",         postgresql.JSON,            nullable=True),
    )
    op.create_unique_constraint("uq_upi_txn_ref_id", "upi_transactions", ["our_ref_id"])
    op.create_index("ix_upi_txn_transaction_id", "upi_transactions", ["transaction_id"])
    op.create_index("ix_upi_txn_merchant_id",    "upi_transactions", ["merchant_id"])
    op.create_index("ix_upi_txn_status",         "upi_transactions", ["status"])

    # ── merchant_vpas ─────────────────────────────────────────────────────────
    op.create_table(
        "merchant_vpas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vpa",         sa.String(100), nullable=False),
        sa.Column("is_active",   sa.Boolean,     nullable=False, server_default="true"),
        sa.Column("created_at",  sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at",  sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_merchant_vpas_vpa", "merchant_vpas", ["vpa"])
    op.create_index("ix_merchant_vpas_merchant_id", "merchant_vpas", ["merchant_id"])

    # ── upi_mandates ──────────────────────────────────────────────────────────
    op.create_table(
        "upi_mandates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("merchant_id",    postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_vpa",   sa.Text,        nullable=False),
        sa.Column("amount",         sa.BigInteger,  nullable=False),
        sa.Column("frequency",
                  sa.Enum(name="upi_mandate_frequency_enum", create_type=False),
                  nullable=False),
        sa.Column("start_date",     sa.Date,        nullable=False),
        sa.Column("end_date",       sa.Date,        nullable=False),
        sa.Column("status",
                  sa.Enum(name="upi_mandate_status_enum", create_type=False),
                  nullable=False, server_default="PENDING"),
        sa.Column("mandate_ref_id", sa.String(100), nullable=True),
        sa.Column("created_at",     sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at",     sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_upi_mandates_merchant_id", "upi_mandates", ["merchant_id"])
    op.create_index("ix_upi_mandates_status",      "upi_mandates", ["status"])


def downgrade() -> None:
    op.drop_table("upi_mandates")
    op.drop_table("merchant_vpas")
    op.drop_table("upi_transactions")
    op.execute("DROP TYPE IF EXISTS upi_mandate_frequency_enum;")
    op.execute("DROP TYPE IF EXISTS upi_mandate_status_enum;")
    op.execute("DROP TYPE IF EXISTS upi_status_enum;")
