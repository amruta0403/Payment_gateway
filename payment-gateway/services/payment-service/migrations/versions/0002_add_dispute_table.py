"""Add dispute_chargebacks table

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-01 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enum types ─────────────────────────────────────────────────────────────
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE dispute_type_enum AS ENUM (
                'CHARGEBACK','PRE_ARBITRATION','RETRIEVAL','FRAUD_REPORT','DUPLICATE'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE dispute_status_enum AS ENUM (
                'OPEN','EVIDENCE_REQUIRED','EVIDENCE_SUBMITTED',
                'UNDER_REVIEW','WON','LOST','EXPIRED','WITHDRAWN'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    # ── dispute_chargebacks ────────────────────────────────────────────────────
    op.create_table(
        "dispute_chargebacks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),

        sa.Column("transaction_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("transactions.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("dispute_type",
                  sa.Enum("CHARGEBACK","PRE_ARBITRATION","RETRIEVAL",
                           "FRAUD_REPORT","DUPLICATE",
                           name="dispute_type_enum", create_type=False),
                  nullable=False),

        # Scheme-specific reason codes (e.g. Visa "4853", MC "4853")
        sa.Column("reason_code",        sa.String(20),  nullable=True),
        sa.Column("reason_description", sa.Text(),      nullable=True),
        sa.Column("scheme_case_id",     sa.String(100), nullable=True),  # network's case ID

        sa.Column("amount",   sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3),    nullable=False, server_default="INR"),

        sa.Column("status",
                  sa.Enum("OPEN","EVIDENCE_REQUIRED","EVIDENCE_SUBMITTED",
                           "UNDER_REVIEW","WON","LOST","EXPIRED","WITHDRAWN",
                           name="dispute_status_enum", create_type=False),
                  nullable=False, server_default="OPEN"),

        # Key dates
        sa.Column("due_date",       sa.Date(),                 nullable=True),
        sa.Column("responded_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at",    sa.DateTime(timezone=True), nullable=True),

        # Acquirer reference
        sa.Column("acquirer_dispute_id", sa.String(100), nullable=True),
        sa.Column("acquirer_ref_no",     sa.String(100), nullable=True),

        # Evidence
        # List of {type: "letter_of_cancellation", s3_key: "...", uploaded_at: "..."}
        sa.Column("evidence_documents", postgresql.JSON(), nullable=False,
                  server_default="[]"),
        sa.Column("merchant_notes",     sa.Text(), nullable=True),
        sa.Column("gateway_notes",      sa.Text(), nullable=True),

        # Who handled it
        sa.Column("assigned_to",  postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_by",  postgresql.UUID(as_uuid=True), nullable=True),

        sa.Column("metadata",   postgresql.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_deleted", sa.Boolean(),      nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),

        sa.CheckConstraint("amount > 0", name="ck_disputes_amount_positive"),
    )

    op.create_index("ix_disputes_transaction_id",   "dispute_chargebacks", ["transaction_id"])
    op.create_index("ix_disputes_merchant_id",      "dispute_chargebacks", ["merchant_id"])
    op.create_index("ix_disputes_status",           "dispute_chargebacks", ["status"])
    op.create_index("ix_disputes_due_date",         "dispute_chargebacks", ["due_date"])
    op.create_index("ix_disputes_scheme_case_id",   "dispute_chargebacks", ["scheme_case_id"])
    op.create_index("ix_disputes_merchant_status",  "dispute_chargebacks",
                    ["merchant_id", "status"])
    op.create_index("ix_disputes_created_at",       "dispute_chargebacks", ["created_at"])

    # ── updated_at trigger ─────────────────────────────────────────────────────
    # set_updated_at() already exists from 0001 — just add the trigger
    op.execute("""
        CREATE TRIGGER trg_disputes_updated_at
        BEFORE UPDATE ON dispute_chargebacks
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)

    # ── RLS: merchants see only their own disputes ─────────────────────────────
    op.execute("ALTER TABLE dispute_chargebacks ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS merchant_isolation ON dispute_chargebacks")
    op.execute("""
        CREATE POLICY merchant_isolation ON dispute_chargebacks
        USING (
            current_setting('app.current_user_is_admin', true) = 'true'
            OR merchant_id::text = current_setting('app.current_merchant_id', true)
        )
    """)

    # ── Backfill: mark existing disputed/chargeback transactions ──────────────
    # This INSERT creates one OPEN dispute record for every transaction already
    # in a DISPUTED or CHARGEBACK terminal state so history is consistent.
    op.execute("""
        INSERT INTO dispute_chargebacks
            (transaction_id, merchant_id, dispute_type, amount, currency, status)
        SELECT
            id,
            merchant_id,
            CASE WHEN status = 'CHARGEBACK' THEN 'CHARGEBACK' ELSE 'FRAUD_REPORT' END,
            amount,
            currency,
            'OPEN'
        FROM transactions
        WHERE status IN ('DISPUTED', 'CHARGEBACK')
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_disputes_updated_at ON dispute_chargebacks")
    op.execute("ALTER TABLE dispute_chargebacks DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS merchant_isolation ON dispute_chargebacks")
    op.drop_table("dispute_chargebacks")
    op.execute("DROP TYPE IF EXISTS dispute_status_enum")
    op.execute("DROP TYPE IF EXISTS dispute_type_enum")
