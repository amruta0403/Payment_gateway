"""initial schema: transactions + transaction_events

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
    # Extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # Enum types
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE transaction_status_enum AS ENUM (
                'CREATED','PENDING','PROCESSING','AUTHORIZED','CAPTURED',
                'SETTLEMENT_INITIATED','SETTLED','FAILED','CANCELLED',
                'REFUNDED','PARTIALLY_REFUNDED','DISPUTED','CHARGEBACK'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE payment_method_enum AS ENUM (
                'CARD','UPI','NETBANKING','WALLET','EMI','BNPL'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE fraud_decision_enum AS ENUM ('ALLOW','CHALLENGE','BLOCK');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    # transactions
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("captured_amount", sa.BigInteger(), nullable=True),
        sa.Column("refunded_amount", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.Enum("CREATED","PENDING","PROCESSING","AUTHORIZED","CAPTURED",
                                     "SETTLEMENT_INITIATED","SETTLED","FAILED","CANCELLED",
                                     "REFUNDED","PARTIALLY_REFUNDED","DISPUTED","CHARGEBACK",
                                     name="transaction_status_enum", create_type=False), nullable=False),
        sa.Column("payment_method", sa.Enum("CARD","UPI","NETBANKING","WALLET","EMI","BNPL",
                                             name="payment_method_enum", create_type=False), nullable=False),
        sa.Column("card_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("card_last4", sa.String(4), nullable=True),
        sa.Column("card_network", sa.String(20), nullable=True),
        sa.Column("upi_vpa", sa.Text(), nullable=True),
        sa.Column("upi_txn_id", sa.String(100), nullable=True),
        sa.Column("bank_code", sa.String(20), nullable=True),
        sa.Column("wallet_name", sa.String(50), nullable=True),
        sa.Column("wallet_txn_id", sa.String(100), nullable=True),
        sa.Column("gateway_txn_id", sa.String(100), nullable=True),
        sa.Column("acquirer_ref_no", sa.String(100), nullable=True),
        sa.Column("rrn", sa.String(50), nullable=True),
        sa.Column("auth_code", sa.String(20), nullable=True),
        sa.Column("bank_txn_id", sa.String(100), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.Column("customer_email", sa.Text(), nullable=True),
        sa.Column("customer_phone", sa.Text(), nullable=True),
        sa.Column("customer_name", sa.Text(), nullable=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("device_fingerprint", sa.String(255), nullable=True),
        sa.Column("fraud_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("fraud_decision", sa.Enum("ALLOW","CHALLENGE","BLOCK",
                                            name="fraud_decision_enum", create_type=False), nullable=True),
        sa.Column("rule_hits", postgresql.JSON(), nullable=False, server_default="[]"),
        sa.Column("three_ds_status", sa.String(20), nullable=True),
        sa.Column("three_ds_eci", sa.String(5), nullable=True),
        sa.Column("three_ds_cavv", sa.Text(), nullable=True),
        sa.Column("three_ds_xid", sa.String(100), nullable=True),
        sa.Column("order_id", sa.String(100), nullable=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("merchant_metadata", postgresql.JSON(), nullable=False, server_default="{}"),
        sa.Column("callback_url", sa.Text(), nullable=True),
        sa.Column("redirect_url", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        sa.UniqueConstraint("idempotency_key", name="uq_transactions_idempotency_key"),
    )

    op.create_index("ix_transactions_merchant_id", "transactions", ["merchant_id"])
    op.create_index("ix_transactions_status", "transactions", ["status"])
    op.create_index("ix_transactions_order_id", "transactions", ["order_id"])
    op.create_index("ix_transactions_gateway_txn_id", "transactions", ["gateway_txn_id"])
    op.create_index("ix_transactions_merchant_status", "transactions", ["merchant_id", "status"])
    op.create_index("ix_transactions_created_at", "transactions", ["created_at"])
    op.create_index("ix_transactions_is_deleted", "transactions", ["is_deleted"])

    # updated_at trigger
    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_transactions_updated_at
        BEFORE UPDATE ON transactions
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)

    # Row-level security
    op.execute("ALTER TABLE transactions ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS merchant_isolation ON transactions")
    op.execute("""
        CREATE POLICY merchant_isolation ON transactions
        USING (
            current_setting('app.current_user_is_admin', true) = 'true'
            OR merchant_id::text = current_setting('app.current_merchant_id', true)
        )
    """)

    # transaction_events
    op.create_table(
        "transaction_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status", sa.Enum("CREATED","PENDING","PROCESSING","AUTHORIZED","CAPTURED",
                                          "SETTLEMENT_INITIATED","SETTLED","FAILED","CANCELLED",
                                          "REFUNDED","PARTIALLY_REFUNDED","DISPUTED","CHARGEBACK",
                                          name="transaction_status_enum", create_type=False), nullable=True),
        sa.Column("to_status", sa.Enum("CREATED","PENDING","PROCESSING","AUTHORIZED","CAPTURED",
                                        "SETTLEMENT_INITIATED","SETTLED","FAILED","CANCELLED",
                                        "REFUNDED","PARTIALLY_REFUNDED","DISPUTED","CHARGEBACK",
                                        name="transaction_status_enum", create_type=False), nullable=False),
        sa.Column("triggered_by", sa.String(100), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    op.create_index("ix_txn_events_transaction_id", "transaction_events", ["transaction_id"])
    op.create_index("ix_txn_events_created_at", "transaction_events", ["created_at"])


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_transactions_updated_at ON transactions")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    op.drop_table("transaction_events")
    op.drop_table("transactions")
    op.execute("DROP TYPE IF EXISTS fraud_decision_enum")
    op.execute("DROP TYPE IF EXISTS payment_method_enum")
    op.execute("DROP TYPE IF EXISTS transaction_status_enum")
