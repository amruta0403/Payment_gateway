"""Initial vault schema: card_tokens, vault_access_log, bin_database

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

# BIN seed data: representative set of common Indian + international BINs
BIN_SEED = [
    ("411111", "VISA",       "CREDIT",  "HDFC Bank",           "IN", True),
    ("400000", "VISA",       "DEBIT",   "State Bank of India",  "IN", True),
    ("404040", "VISA",       "DEBIT",   "ICICI Bank",           "IN", True),
    ("419267", "VISA",       "CREDIT",  "Axis Bank",            "IN", True),
    ("512345", "MASTERCARD", "CREDIT",  "Kotak Mahindra Bank",  "IN", True),
    ("524715", "MASTERCARD", "DEBIT",   "Punjab National Bank", "IN", True),
    ("555555", "MASTERCARD", "CREDIT",  "HDFC Bank",            "IN", True),
    ("371449", "AMEX",       "CREDIT",  "American Express",     "US", False),
    ("340000", "AMEX",       "CREDIT",  "American Express",     "US", False),
    ("606074", "RUPAY",      "DEBIT",   "Bank of Baroda",       "IN", True),
    ("607384", "RUPAY",      "CREDIT",  "State Bank of India",  "IN", True),
    ("652110", "RUPAY",      "PREPAID", "NPCI",                 "IN", True),
    ("601100", "DISCOVER",   "CREDIT",  "Discover",             "US", False),
    ("650000", "DISCOVER",   "CREDIT",  "Discover",             "US", False),
    ("400001", "VISA",       "CREDIT",  "Citibank",             "US", False),
    ("400002", "VISA",       "CREDIT",  "Chase",                "US", False),
    ("520000", "MASTERCARD", "CREDIT",  "Mastercard Test",      "US", False),
    ("400003", "VISA",       "DEBIT",   "IDFC First Bank",      "IN", True),
    ("400004", "VISA",       "CREDIT",  "Yes Bank",             "IN", True),
    ("506900", "RUPAY",      "DEBIT",   "Canara Bank",          "IN", True),
]


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # ── card_tokens ────────────────────────────────────────────────────────────
    op.create_table(
        "card_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("token", postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("pan_encrypted", sa.Text(), nullable=False),
        sa.Column("key_version", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("pan_fingerprint", sa.String(64), nullable=False),
        sa.Column("pan_last4", sa.String(4), nullable=True),
        sa.Column("pan_first6", sa.String(6), nullable=True),
        sa.Column("pan_length", sa.SmallInteger(), nullable=False, server_default="16"),
        sa.Column("expiry_month", sa.SmallInteger(), nullable=True),
        sa.Column("expiry_year", sa.SmallInteger(), nullable=True),
        sa.Column("cardholder_name", sa.Text(), nullable=True),
        sa.Column("card_network", sa.String(20), nullable=True),
        sa.Column("card_category", sa.String(20), nullable=True),
        sa.Column("issuer_bank", sa.String(100), nullable=True),
        sa.Column("issuer_country", sa.String(2), nullable=True),
        sa.Column("is_domestic", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("token", name="uq_card_tokens_token"),
        sa.CheckConstraint("expiry_month BETWEEN 1 AND 12", name="ck_card_tokens_expiry_month"),
    )
    op.create_index("ix_card_tokens_fingerprint_merchant", "card_tokens",
                    ["pan_fingerprint", "merchant_id"])
    op.create_index("ix_card_tokens_merchant_id", "card_tokens", ["merchant_id"])
    op.create_index("ix_card_tokens_customer_id", "card_tokens", ["customer_id"])
    op.create_index("ix_card_tokens_is_active", "card_tokens", ["is_active"])
    op.create_index("ix_card_tokens_token", "card_tokens", ["token"])

    # ── vault_access_log (append-only) ────────────────────────────────────────
    op.create_table(
        "vault_access_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("card_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("requesting_service", sa.String(50), nullable=True),
        sa.Column("requesting_ip", sa.String(45), nullable=True),
        sa.Column("trace_id", sa.String(100), nullable=True),
        sa.Column("outcome", sa.String(20), nullable=False, server_default="success"),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_val_card_token", "vault_access_log", ["card_token"])
    op.create_index("ix_val_created_at", "vault_access_log", ["created_at"])
    op.create_index("ix_val_operation", "vault_access_log", ["operation"])

    # Revoke UPDATE/DELETE/TRUNCATE on vault_access_log (append-only enforcement)
    op.execute("""
        DO $$ BEGIN
            REVOKE UPDATE, DELETE, TRUNCATE ON vault_access_log FROM PUBLIC;
        EXCEPTION WHEN others THEN NULL;
        END $$
    """)

    # ── bin_database ───────────────────────────────────────────────────────────
    op.create_table(
        "bin_database",
        sa.Column("bin", sa.String(6), primary_key=True),
        sa.Column("card_network", sa.String(20), nullable=True),
        sa.Column("card_category", sa.String(20), nullable=True),
        sa.Column("issuer_bank", sa.String(100), nullable=True),
        sa.Column("issuer_country", sa.String(2), nullable=True),
        sa.Column("is_domestic", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    # Seed BIN table
    for bin_row in BIN_SEED:
        op.execute(
            sa.text(
                "INSERT INTO bin_database (bin, card_network, card_category, issuer_bank, issuer_country, is_domestic) "
                "VALUES (:bin, :network, :category, :bank, :country, :domestic) "
                "ON CONFLICT (bin) DO NOTHING"
            ).bindparams(
                bin=bin_row[0],
                network=bin_row[1],
                category=bin_row[2],
                bank=bin_row[3],
                country=bin_row[4],
                domestic=bin_row[5],
            )
        )


def downgrade() -> None:
    op.drop_table("bin_database")
    op.drop_table("vault_access_log")
    op.drop_table("card_tokens")
