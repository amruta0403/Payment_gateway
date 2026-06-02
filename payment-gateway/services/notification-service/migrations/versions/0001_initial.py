"""Initial notification-service schema: notification_logs

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

    # ── Enum types ─────────────────────────────────────────────────────────────
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE notification_channel_enum AS ENUM (
                'EMAIL','SMS','PUSH','WEBHOOK','WHATSAPP'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE notification_status_enum AS ENUM (
                'PENDING','QUEUED','SENT','DELIVERED','FAILED','BOUNCED','SUPPRESSED'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    # ── notification_logs ──────────────────────────────────────────────────────
    op.create_table(
        "notification_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),

        # Context references (no FK — cross-service)
        sa.Column("merchant_id",    postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("refund_id",      postgresql.UUID(as_uuid=True), nullable=True),

        # Routing
        sa.Column("channel",
                  sa.Enum("EMAIL","SMS","PUSH","WEBHOOK","WHATSAPP",
                           name="notification_channel_enum", create_type=False),
                  nullable=False),
        sa.Column("recipient",       sa.Text(),        nullable=False),

        # Content
        sa.Column("template_id",    sa.String(100),   nullable=True),
        sa.Column("subject",        sa.String(500),   nullable=True),
        # Body is not stored (PII). Only a SHA-256 fingerprint for dedup.
        sa.Column("body_hash",      sa.String(64),    nullable=True),
        sa.Column("rendered_bytes", sa.Integer(),     nullable=True),

        # Status tracking
        sa.Column("status",
                  sa.Enum("PENDING","QUEUED","SENT","DELIVERED","FAILED","BOUNCED","SUPPRESSED",
                           name="notification_status_enum", create_type=False),
                  nullable=False, server_default="PENDING"),

        # Provider
        sa.Column("provider",           sa.String(50),  nullable=True),
        sa.Column("provider_message_id",sa.String(200), nullable=True),
        sa.Column("provider_response",  postgresql.JSON(), nullable=True),
        sa.Column("error_message",      sa.Text(),      nullable=True),

        # Retry
        sa.Column("retry_count",  sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("max_retries",  sa.SmallInteger(), nullable=False, server_default="3"),
        sa.Column("next_retry_at",sa.DateTime(timezone=True), nullable=True),

        # Timestamps
        sa.Column("scheduled_at",  sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at",       sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at",  sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at",     sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at",     sa.DateTime(timezone=True), nullable=True),

        sa.Column("metadata",   postgresql.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    op.create_index("ix_notif_merchant_id",    "notification_logs", ["merchant_id"])
    op.create_index("ix_notif_transaction_id", "notification_logs", ["transaction_id"])
    op.create_index("ix_notif_channel",        "notification_logs", ["channel"])
    op.create_index("ix_notif_status",         "notification_logs", ["status"])
    op.create_index("ix_notif_created_at",     "notification_logs", ["created_at"])
    op.create_index("ix_notif_next_retry",     "notification_logs", ["next_retry_at"],
                    postgresql_where=sa.text("status = 'FAILED' AND retry_count < max_retries"))
    op.create_index("ix_notif_provider_msg_id","notification_logs", ["provider_message_id"],
                    postgresql_where=sa.text("provider_message_id IS NOT NULL"))

    # ── notification_preferences (per merchant/customer opt-out) ──────────────
    op.create_table(
        "notification_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_type",  sa.String(20),   nullable=False),   # merchant | customer
        sa.Column("entity_id",    postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel",
                  sa.Enum("EMAIL","SMS","PUSH","WEBHOOK","WHATSAPP",
                           name="notification_channel_enum", create_type=False),
                  nullable=False),
        sa.Column("event_type",   sa.String(100),  nullable=False),   # payment.captured, refund.initiated …
        sa.Column("is_enabled",   sa.Boolean(),    nullable=False, server_default="true"),
        sa.Column("created_at",   sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at",   sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("entity_type","entity_id","channel","event_type",
                            name="uq_notif_pref_entity_channel_event"),
    )

    op.create_index("ix_notif_pref_entity", "notification_preferences",
                    ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_table("notification_preferences")
    op.drop_table("notification_logs")
    op.execute("DROP TYPE IF EXISTS notification_status_enum")
    op.execute("DROP TYPE IF EXISTS notification_channel_enum")
