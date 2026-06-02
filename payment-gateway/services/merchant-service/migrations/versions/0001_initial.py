"""Initial merchant-service schema

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
            CREATE TYPE business_type_enum AS ENUM (
                'SOLE_PROPRIETOR','PARTNERSHIP','PRIVATE_LIMITED',
                'PUBLIC_LIMITED','LLP','TRUST','NGO','GOVERNMENT'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE merchant_status_enum AS ENUM (
                'DRAFT','PENDING_KYC','ACTIVE','SUSPENDED','CLOSED'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE kyc_document_type_enum AS ENUM (
                'PAN','GSTIN','CANCELLED_CHEQUE','INCORPORATION_CERT',
                'BOARD_RESOLUTION','UTILITY_BILL','PASSPORT','AADHAAR'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE kyc_document_status_enum AS ENUM (
                'PENDING','UNDER_REVIEW','VERIFIED','REJECTED','EXPIRED'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # ── merchants ─────────────────────────────────────────────────────────────
    op.create_table(
        "merchants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_name", sa.Text, nullable=False),
        sa.Column("pan", sa.Text, nullable=True),
        sa.Column("gstin", sa.Text, nullable=True),
        sa.Column("support_email", sa.Text, nullable=True),
        sa.Column("support_phone", sa.Text, nullable=True),
        sa.Column("business_name_hash", sa.String(64), nullable=True),
        sa.Column("pan_hash", sa.String(64), nullable=True),
        sa.Column("gstin_hash", sa.String(64), nullable=True),
        sa.Column("business_type",
                  sa.Enum(name="business_type_enum", create_type=False),
                  nullable=False),
        sa.Column("status",
                  sa.Enum(name="merchant_status_enum", create_type=False),
                  nullable=False, server_default="DRAFT"),
        sa.Column("website_url", sa.String(500), nullable=True),
        sa.Column("business_category", sa.String(10), nullable=True),
        sa.Column("fee_config", postgresql.JSON, nullable=False,
                  server_default="{}"),
        sa.Column("keycloak_group_id", sa.String(100), nullable=True),
        sa.Column("display_name", sa.String(200), nullable=True),
        sa.Column("logo_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_merchants_status", "merchants", ["status"])
    op.create_index("ix_merchants_pan_hash", "merchants", ["pan_hash"])
    op.create_index("ix_merchants_gstin_hash", "merchants", ["gstin_hash"])
    op.create_index("ix_merchants_business_name_hash", "merchants", ["business_name_hash"])

    # updated_at trigger
    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER merchants_set_updated_at
        BEFORE UPDATE ON merchants
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)

    # Row-Level Security
    op.execute("ALTER TABLE merchants ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY merchants_rls ON merchants
        USING (
            current_setting('app.current_merchant_id', TRUE) IS NULL
            OR id::text = current_setting('app.current_merchant_id', TRUE)
        );
    """)

    # ── merchant_bank_accounts ────────────────────────────────────────────────
    op.create_table(
        "merchant_bank_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_holder_name", sa.String(200), nullable=False),
        sa.Column("account_number", sa.Text, nullable=False),
        sa.Column("account_number_hash", sa.String(64), nullable=True),
        sa.Column("ifsc_code", sa.String(11), nullable=False),
        sa.Column("account_type", sa.String(20), nullable=False, server_default="CURRENT"),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("penny_drop_ref", sa.String(100), nullable=True),
        sa.Column("penny_drop_amount", sa.SmallInteger, nullable=True),
        sa.Column("penny_drop_initiated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mba_merchant_id", "merchant_bank_accounts", ["merchant_id"])

    # ── kyc_documents ─────────────────────────────────────────────────────────
    op.create_table(
        "kyc_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_type",
                  sa.Enum(name="kyc_document_type_enum", create_type=False),
                  nullable=False),
        sa.Column("status",
                  sa.Enum(name="kyc_document_status_enum", create_type=False),
                  nullable=False, server_default="PENDING"),
        sa.Column("s3_key_encrypted", sa.Text, nullable=True),
        sa.Column("file_hash", sa.String(64), nullable=True),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column("mime_type", sa.String(50), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_kyc_docs_merchant_id", "kyc_documents", ["merchant_id"])
    op.create_index("ix_kyc_docs_status", "kyc_documents", ["status"])
    op.create_index("ix_kyc_docs_document_type", "kyc_documents", ["document_type"])

    # ── api_keys ──────────────────────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_prefix", sa.String(60), nullable=False, unique=True),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("environment", sa.String(10), nullable=False, server_default="SANDBOX"),
        sa.Column("permissions", postgresql.JSON, nullable=False, server_default="[]"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_ip", sa.String(45), nullable=True),
        sa.Column("usage_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_keys_merchant_id", "api_keys", ["merchant_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])
    op.create_index("ix_api_keys_is_active", "api_keys", ["is_active"])

    # ── merchant_webhooks ─────────────────────────────────────────────────────
    op.create_table(
        "merchant_webhooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("events", postgresql.JSON, nullable=False, server_default="[]"),
        sa.Column("secret_hash", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_webhooks_merchant_id", "merchant_webhooks", ["merchant_id"])

    # ── webhook_deliveries ────────────────────────────────────────────────────
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("webhook_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("merchant_webhooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("response_status", sa.SmallInteger, nullable=True),
        sa.Column("response_body", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("attempt_count", sa.SmallInteger, nullable=False, server_default="1"),
        sa.Column("success", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_wh_deliveries_webhook_id", "webhook_deliveries", ["webhook_id"])
    op.create_index("ix_wh_deliveries_created_at", "webhook_deliveries", ["created_at"])


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    op.drop_table("merchant_webhooks")
    op.drop_table("api_keys")
    op.drop_table("kyc_documents")
    op.drop_table("merchant_bank_accounts")
    op.execute("DROP TRIGGER IF EXISTS merchants_set_updated_at ON merchants;")
    op.drop_table("merchants")
    op.execute("DROP TYPE IF EXISTS kyc_document_status_enum;")
    op.execute("DROP TYPE IF EXISTS kyc_document_type_enum;")
    op.execute("DROP TYPE IF EXISTS merchant_status_enum;")
    op.execute("DROP TYPE IF EXISTS business_type_enum;")
