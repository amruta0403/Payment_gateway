"""Initial refund-service schema: refunds table

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
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # ── Enum types ─────────────────────────────────────────────────────────────
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE refund_status_enum AS ENUM (
                'INITIATED','PROCESSING','PENDING_APPROVAL',
                'SUCCESS','FAILED','REVERSED','PARTIAL'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE refund_type_enum AS ENUM (
                'FULL','PARTIAL','MERCHANT_INIT','CUSTOMER_INIT','CHARGEBACK_REVERSAL'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    # ── updated_at trigger (shared across services — CREATE OR REPLACE is idempotent) ─
    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    # ── refunds ────────────────────────────────────────────────────────────────
    op.create_table(
        "refunds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        # Cross-service ref — no FK (payment-service owns transactions)
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("merchant_id",    postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("amount",    sa.BigInteger(), nullable=False),
        sa.Column("currency",  sa.String(3),    nullable=False, server_default="INR"),

        sa.Column("refund_type",
                  sa.Enum("FULL","PARTIAL","MERCHANT_INIT","CUSTOMER_INIT","CHARGEBACK_REVERSAL",
                           name="refund_type_enum", create_type=False),
                  nullable=False, server_default="FULL"),

        sa.Column("status",
                  sa.Enum("INITIATED","PROCESSING","PENDING_APPROVAL",
                           "SUCCESS","FAILED","REVERSED","PARTIAL",
                           name="refund_status_enum", create_type=False),
                  nullable=False, server_default="INITIATED"),

        sa.Column("reason",            sa.String(200), nullable=True),
        sa.Column("notes",             sa.Text(),      nullable=True),

        # Acquirer / gateway references
        sa.Column("gateway_refund_id", sa.String(100), nullable=True),
        sa.Column("acquirer_rrn",      sa.String(50),  nullable=True),
        sa.Column("bank_ref_no",       sa.String(100), nullable=True),

        # Who initiated
        sa.Column("initiated_by",  postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_by",   postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at",   sa.DateTime(timezone=True),    nullable=True),

        # Error tracking
        sa.Column("error_code",    sa.String(50),  nullable=True),
        sa.Column("error_message", sa.Text(),      nullable=True),

        # Idempotency
        sa.Column("idempotency_key", sa.String(255), nullable=False),

        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at",    sa.DateTime(timezone=True), nullable=True),

        sa.Column("metadata",    postgresql.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_deleted",  sa.Boolean(),      nullable=False, server_default="false"),
        sa.Column("created_at",  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at",  sa.DateTime(timezone=True), nullable=True),

        sa.CheckConstraint("amount > 0",                 name="ck_refunds_amount_positive"),
        sa.UniqueConstraint("idempotency_key",           name="uq_refunds_idempotency_key"),
    )

    op.create_index("ix_refunds_transaction_id", "refunds", ["transaction_id"])
    op.create_index("ix_refunds_merchant_id",    "refunds", ["merchant_id"])
    op.create_index("ix_refunds_status",         "refunds", ["status"])
    op.create_index("ix_refunds_created_at",     "refunds", ["created_at"])
    op.create_index("ix_refunds_gateway_id",     "refunds", ["gateway_refund_id"])
    # Composite: merchant + status for dashboard queries
    op.create_index("ix_refunds_merchant_status", "refunds", ["merchant_id", "status"])

    # ── updated_at trigger ─────────────────────────────────────────────────────
    op.execute("""
        CREATE TRIGGER trg_refunds_updated_at
        BEFORE UPDATE ON refunds
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)

    # ── Row-level security: merchant isolation ─────────────────────────────────
    op.execute("ALTER TABLE refunds ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS merchant_isolation ON refunds")
    op.execute("""
        CREATE POLICY merchant_isolation ON refunds
        USING (
            current_setting('app.current_user_is_admin', true) = 'true'
            OR merchant_id::text = current_setting('app.current_merchant_id', true)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_refunds_updated_at ON refunds")
    op.execute("ALTER TABLE refunds DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS merchant_isolation ON refunds")
    op.drop_table("refunds")
    op.execute("DROP TYPE IF EXISTS refund_type_enum")
    op.execute("DROP TYPE IF EXISTS refund_status_enum")
