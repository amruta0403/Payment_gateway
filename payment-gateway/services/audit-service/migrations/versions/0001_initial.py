"""Initial audit-service schema: audit_logs partitioned table

Audit_logs is PARTITION BY RANGE(created_at) with monthly partitions 2025–2026.
The application user (payment_app_user) may only INSERT and SELECT —
UPDATE, DELETE, TRUNCATE are explicitly revoked so the log is append-only.

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

# Generate all (year, month) pairs for 2025 and 2026
_PARTITION_MONTHS = [
    (y, m) for y in (2025, 2026) for m in range(1, 13)
]


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ── audit_logs (parent — partitioned by month) ─────────────────────────────
    # Primary key must include the partition key (created_at) for PostgreSQL.
    # We use (id, created_at) so each child partition can enforce PK uniqueness.
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id          UUID          NOT NULL DEFAULT gen_random_uuid(),
            service     VARCHAR(50)   NOT NULL,
            entity_type VARCHAR(50)   NOT NULL,
            entity_id   UUID,
            action      VARCHAR(50)   NOT NULL,
            actor_id    UUID,
            actor_type  VARCHAR(20),
            merchant_id UUID,
            old_state   JSONB,
            new_state   JSONB,
            diff        JSONB,
            metadata    JSONB         NOT NULL DEFAULT '{}',
            ip_address  VARCHAR(45),
            user_agent  TEXT,
            request_id  VARCHAR(100),
            trace_id    VARCHAR(100),
            created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)

    # ── Indexes on parent (propagate to all partitions) ────────────────────────
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_service
        ON audit_logs (service)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_entity
        ON audit_logs (entity_type, entity_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_actor
        ON audit_logs (actor_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_merchant_id
        ON audit_logs (merchant_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at
        ON audit_logs (created_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_action
        ON audit_logs (action)
    """)

    # ── Monthly partitions 2025-01 … 2026-12 ──────────────────────────────────
    for year, month in _PARTITION_MONTHS:
        ny, nm = _next_month(year, month)
        partition_name = f"audit_logs_{year}_{month:02d}"
        start = f"{year}-{month:02d}-01"
        end   = f"{ny}-{nm:02d}-01"
        op.execute(f"""
            CREATE TABLE IF NOT EXISTS {partition_name}
            PARTITION OF audit_logs
            FOR VALUES FROM ('{start}') TO ('{end}')
        """)

    # ── Default partition — catches rows outside 2025-2026 range ──────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs_default
        PARTITION OF audit_logs DEFAULT
    """)

    # ── Append-only enforcement ────────────────────────────────────────────────
    # Only revoke if the role exists (idempotent via DO block)
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'payment_app_user') THEN
                REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM payment_app_user;
                GRANT  INSERT, SELECT          ON audit_logs TO   payment_app_user;
            END IF;
        END $$
    """)

    # Also restrict on PUBLIC as belt-and-suspenders
    op.execute("""
        DO $$ BEGIN
            REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM PUBLIC;
        EXCEPTION WHEN others THEN NULL;
        END $$
    """)


def downgrade() -> None:
    # Drop partitions first, then the parent
    for year, month in reversed(_PARTITION_MONTHS):
        partition_name = f"audit_logs_{year}_{month:02d}"
        op.execute(f"DROP TABLE IF EXISTS {partition_name}")
    op.execute("DROP TABLE IF EXISTS audit_logs_default")
    op.execute("DROP TABLE IF EXISTS audit_logs")
