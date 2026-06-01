"""Seed local development database with test merchants and transactions."""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()

TEST_MERCHANT_1_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
TEST_MERCHANT_2_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

DEFAULT_FEE_CONFIG = {
    "card_mdr_percent": "2.0",
    "upi_flat_fee_paise": 0,
    "netbanking_flat_fee_paise": 1000,
    "gst_percent": "18",
}


async def seed_merchants(session: AsyncSession) -> None:
    for merchant_id, name, email in [
        (TEST_MERCHANT_1_ID, "Test Merchant Alpha", "alpha@test.com"),
        (TEST_MERCHANT_2_ID, "Test Merchant Beta", "beta@test.com"),
    ]:
        await session.execute(
            text("""
                INSERT INTO merchants (id, business_name, business_type, status,
                    support_email, fee_config, created_at, updated_at, is_deleted)
                VALUES (:id, :name, 'PRIVATE_LIMITED', 'ACTIVE',
                    :email, :fee_config::jsonb, NOW(), NOW(), false)
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": merchant_id,
                "name": name,
                "email": email,
                "fee_config": str(DEFAULT_FEE_CONFIG).replace("'", '"'),
            },
        )
    log.info("seed.merchants.done")


async def seed_bank_accounts(session: AsyncSession) -> None:
    for merchant_id in [TEST_MERCHANT_1_ID, TEST_MERCHANT_2_ID]:
        await session.execute(
            text("""
                INSERT INTO merchant_bank_accounts
                    (id, merchant_id, account_holder_name, account_number, ifsc_code,
                     account_type, is_primary, is_verified, created_at, is_deleted)
                VALUES (gen_random_uuid(), :mid, 'Test Account',
                    '00112233445566', 'HDFC0001234',
                    'CURRENT', true, true, NOW(), false)
                ON CONFLICT DO NOTHING
            """),
            {"mid": merchant_id},
        )
    log.info("seed.bank_accounts.done")


async def seed_transactions(session: AsyncSession) -> None:
    statuses = ["CAPTURED", "SETTLED", "FAILED", "PENDING", "REFUNDED"]
    for i, status in enumerate(statuses):
        await session.execute(
            text("""
                INSERT INTO transactions
                    (id, merchant_id, amount, currency, status, payment_method,
                     idempotency_key, created_at, updated_at, is_deleted)
                VALUES (gen_random_uuid(), :mid, :amount, 'INR', :status, 'CARD',
                    :ikey, NOW(), NOW(), false)
                ON CONFLICT DO NOTHING
            """),
            {
                "mid": TEST_MERCHANT_1_ID,
                "amount": (i + 1) * 10000,
                "status": status,
                "ikey": f"seed-txn-{i:04d}",
            },
        )
    log.info("seed.transactions.done")


async def main() -> None:
    import os

    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://pguser:pgpass@localhost:5432/payment_db",
    )
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        try:
            await seed_merchants(session)
            await seed_bank_accounts(session)
            await seed_transactions(session)
            await session.commit()
            log.info("seed.complete")
            print("\n✓ Database seeded successfully\n")
        except Exception as exc:
            await session.rollback()
            log.error("seed.failed", error=str(exc))
            raise

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
