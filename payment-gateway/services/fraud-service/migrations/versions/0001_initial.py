"""Initial fraud-service schema

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
    # ── fraud_blacklist ───────────────────────────────────────────────────────
    op.create_table(
        "fraud_blacklist",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("list_type", sa.String(20), nullable=False),
        sa.Column("value", sa.String(255), nullable=False),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_fraud_bl_list_type_value",
        "fraud_blacklist",
        ["list_type", "value"],
    )

    # ── fraud_rules ───────────────────────────────────────────────────────────
    op.create_table(
        "fraud_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("rule_name", sa.String(100), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("weight", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_fraud_rules_rule_name", "fraud_rules", ["rule_name"])

    # Seed known rules
    op.execute("""
        INSERT INTO fraud_rules (rule_name, description, weight) VALUES
        ('check_ip_blacklist',       'Block transactions from blacklisted IPs',              1.0),
        ('check_card_blacklist',     'Block transactions using blacklisted cards',            1.0),
        ('check_velocity_card',      'Block if same card used >3 times in 60s',              1.0),
        ('check_velocity_ip',        'Block if same IP used >10 times in 60s',               1.0),
        ('check_velocity_email',     'Block if same email used >5 times in 1h',              1.0),
        ('score_international_card', 'Adds 0.30 for intl card on Indian IP',                 1.0),
        ('score_odd_hour',           'Adds 0.10 for transactions 1–4am IST',                 1.0),
        ('score_round_amount',       'Adds 0.10 for round amounts (1L/2L/5L/10L)',           1.0),
        ('score_new_merchant',       'Adds 0.15 for merchants < 7 days old',                 1.0),
        ('score_high_risk_mcc',      'Adds 0.20 for gambling/pharma MCCs',                   1.0)
        ON CONFLICT (rule_name) DO NOTHING;
    """)


def downgrade() -> None:
    op.drop_table("fraud_rules")
    op.drop_table("fraud_blacklist")
