"""Initial settlement-service schema

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
            CREATE TYPE settlement_status_enum AS ENUM
                ('PENDING','PROCESSING','COMPLETED','FAILED','RECONCILED');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE payout_method_enum AS ENUM ('IMPS','NEFT','RTGS');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE payout_status_enum AS ENUM
                ('INITIATED','PROCESSING','SUCCESS','FAILED');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # ── settlement_batches ────────────────────────────────────────────────────
    op.create_table(
        "settlement_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("merchant_id",       postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("settlement_date",   sa.Date,       nullable=False),
        sa.Column("gross_amount",      sa.BigInteger, nullable=False),
        sa.Column("fee_amount",        sa.BigInteger, nullable=False),
        sa.Column("gst_on_fee",        sa.BigInteger, nullable=False),
        sa.Column("net_amount",        sa.BigInteger, nullable=False),
        sa.Column("transaction_count", sa.Integer,    nullable=False, server_default="0"),
        sa.Column("status",
                  sa.Enum(name="settlement_status_enum", create_type=False),
                  nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sb_merchant_id",      "settlement_batches", ["merchant_id"])
    op.create_index("ix_sb_settlement_date",  "settlement_batches", ["settlement_date"])
    op.create_index("ix_sb_status",           "settlement_batches", ["status"])

    op.execute("""
        CREATE TRIGGER settlement_batches_set_updated_at
        BEFORE UPDATE ON settlement_batches
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)

    # ── settlement_transactions ───────────────────────────────────────────────
    op.create_table(
        "settlement_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("batch_id",
                  postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("settlement_batches.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("fee",    sa.BigInteger, nullable=False),
        sa.Column("gst",    sa.BigInteger, nullable=False),
        sa.Column("net",    sa.BigInteger, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_st_batch_id",       "settlement_transactions", ["batch_id"])
    op.create_index("ix_st_transaction_id", "settlement_transactions", ["transaction_id"])

    # ── settlement_payouts ────────────────────────────────────────────────────
    op.create_table(
        "settlement_payouts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("batch_id",
                  postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("settlement_batches.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("merchant_bank_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount",        sa.BigInteger, nullable=False),
        sa.Column("payout_method",
                  sa.Enum(name="payout_method_enum", create_type=False),
                  nullable=False, server_default="IMPS"),
        sa.Column("status",
                  sa.Enum(name="payout_status_enum", create_type=False),
                  nullable=False, server_default="INITIATED"),
        sa.Column("utr_number",     sa.String(50), nullable=True),
        sa.Column("failure_reason", sa.Text,       nullable=True),
        sa.Column("initiated_at",   sa.DateTime(timezone=True),
                  nullable=True, server_default=sa.text("NOW()")),
        sa.Column("completed_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at",     sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at",     sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sp_batch_id", "settlement_payouts", ["batch_id"])
    op.create_index("ix_sp_status",   "settlement_payouts", ["status"])


def downgrade() -> None:
    op.drop_table("settlement_payouts")
    op.drop_table("settlement_transactions")
    op.drop_table("settlement_batches")
    op.execute("DROP TYPE IF EXISTS payout_status_enum;")
    op.execute("DROP TYPE IF EXISTS payout_method_enum;")
    op.execute("DROP TYPE IF EXISTS settlement_status_enum;")
