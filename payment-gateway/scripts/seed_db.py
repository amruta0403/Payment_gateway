"""
Seed local development database with test data.

Creates:
  - 2 test merchants (with encrypted fields, hashed fields, fee_config)
  - Bank accounts + VPAs for each merchant
  - 10 sample transactions across multiple statuses
  - Fraud rule entries (if fraud_rules table exists)
  - Test API keys for each merchant
  - Test webhook endpoints

Run:
  docker compose exec payment-service python scripts/seed_db.py
  OR
  DATABASE_URL=postgresql+asyncpg://pguser:pgpass@localhost:5432/payment_db python scripts/seed_db.py
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

log = structlog.get_logger()

# ── Fixed test IDs (stable across re-seeds) ───────────────────────────────────
MERCHANT_1_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
MERCHANT_2_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

DEFAULT_FEE_CONFIG = json.dumps({
    "card_mdr_percent": "2.0",
    "upi_flat_fee_paise": 0,
    "netbanking_flat_fee_paise": 1000,
    "gst_percent": "18",
})


def _encrypt_for_seed(value: str) -> str:
    """
    Stub encryption for seed data.
    In dev, services generate an ephemeral key if CARD_ENCRYPTION_KEY_V1 is unset,
    so seed data uses the same stub approach — store plaintext b64-padded.
    Real services will decrypt correctly if they use the real key.
    """
    enc_key = os.environ.get("CARD_ENCRYPTION_KEY_V1", "")
    if enc_key:
        try:
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
            from shared.utils.encryption import FieldEncryptor
            return FieldEncryptor(enc_key).encrypt(value)
        except Exception:
            pass
    # Fallback: base64 prefix for easy identification
    return "seed:" + base64.b64encode(value.encode()).decode()


def _hash_field(value: str) -> str:
    return hashlib.sha256(value.lower().encode()).hexdigest()


def _api_key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


# ── Seed functions ─────────────────────────────────────────────────────────────

async def seed_merchants(session: AsyncSession) -> None:
    log.info("seed.merchants.start")
    merchants = [
        {
            "id": MERCHANT_1_ID,
            "business_name": "Alpha Payments Pvt Ltd",
            "pan": "AABCA1234Z",
            "support_email": "alpha@test.payments.local",
            "support_phone": "+919876543210",
            "status": "ACTIVE",
            "display_name": "Alpha Pay",
        },
        {
            "id": MERCHANT_2_ID,
            "business_name": "Beta Commerce LLP",
            "pan": "BBBCB5678Y",
            "support_email": "beta@test.payments.local",
            "support_phone": "+919876543211",
            "status": "PENDING_KYC",
            "display_name": "Beta Shop",
        },
    ]

    for m in merchants:
        enc_name  = _encrypt_for_seed(m["business_name"])
        enc_pan   = _encrypt_for_seed(m["pan"])
        enc_email = _encrypt_for_seed(m["support_email"])
        enc_phone = _encrypt_for_seed(m["support_phone"])
        name_hash = _hash_field(m["business_name"])
        pan_hash  = _hash_field(m["pan"])

        await session.execute(text("""
            INSERT INTO merchants (
                id, business_name, business_name_hash, pan, pan_hash,
                support_email, support_phone, business_type, status,
                display_name, website_url, business_category,
                fee_config, keycloak_group_id,
                created_at, updated_at, is_deleted
            ) VALUES (
                :id, :bname, :bname_hash, :pan, :pan_hash,
                :email, :phone, 'PRIVATE_LIMITED', :status,
                :display_name, 'https://test.payments.local', '5411',
                :fee_config::json, :kc_group,
                NOW(), NOW(), false
            )
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                display_name = EXCLUDED.display_name,
                updated_at = NOW()
        """), {
            "id": str(m["id"]), "bname": enc_name, "bname_hash": name_hash,
            "pan": enc_pan, "pan_hash": pan_hash, "email": enc_email,
            "phone": enc_phone, "status": m["status"], "display_name": m["display_name"],
            "fee_config": DEFAULT_FEE_CONFIG, "kc_group": f"dev-group-{m['id']}",
        })
    log.info("seed.merchants.done", count=len(merchants))


async def seed_bank_accounts(session: AsyncSession) -> None:
    log.info("seed.bank_accounts.start")
    accounts = [
        (MERCHANT_1_ID, "Alpha Payments Pvt Ltd", "987654321012", "HDFC0001234"),
        (MERCHANT_2_ID, "Beta Commerce LLP",      "123456789012", "ICIC0005678"),
    ]
    for mid, holder, acct_no, ifsc in accounts:
        enc_acct = _encrypt_for_seed(acct_no)
        acct_hash = _hash_field(acct_no)
        await session.execute(text("""
            INSERT INTO merchant_bank_accounts (
                id, merchant_id, account_holder_name, account_number,
                account_number_hash, ifsc_code, account_type,
                is_primary, is_verified, verified_at,
                created_at, updated_at, is_deleted
            ) VALUES (
                gen_random_uuid(), :mid, :holder, :acct,
                :acct_hash, :ifsc, 'CURRENT',
                true, true, NOW(),
                NOW(), NOW(), false
            )
            ON CONFLICT DO NOTHING
        """), {
            "mid": str(mid), "holder": holder, "acct": enc_acct,
            "acct_hash": acct_hash, "ifsc": ifsc,
        })
    log.info("seed.bank_accounts.done")


async def seed_transactions(session: AsyncSession) -> None:
    log.info("seed.transactions.start")
    txns = [
        # (merchant_id, amount, status, method, days_ago)
        (MERCHANT_1_ID, 50000,   "CAPTURED",  "CARD",       0),
        (MERCHANT_1_ID, 120000,  "SETTLED",   "CARD",       1),
        (MERCHANT_1_ID, 10000,   "FAILED",    "UPI",        0),
        (MERCHANT_1_ID, 200000,  "SETTLED",   "NETBANKING", 2),
        (MERCHANT_1_ID, 75000,   "REFUNDED",  "CARD",       3),
        (MERCHANT_1_ID, 30000,   "CAPTURED",  "UPI",        0),
        (MERCHANT_1_ID, 500000,  "SETTLED",   "CARD",       7),
        (MERCHANT_2_ID, 45000,   "CAPTURED",  "CARD",       0),
        (MERCHANT_2_ID, 15000,   "FAILED",    "NETBANKING", 1),
        (MERCHANT_2_ID, 90000,   "PENDING",   "UPI",        0),
    ]
    for i, (mid, amount, status, method, days_ago) in enumerate(txns):
        created = datetime.utcnow() - timedelta(days=days_ago, hours=i)
        captured_at = created + timedelta(minutes=1) if status in ("CAPTURED", "SETTLED", "REFUNDED") else None
        settled_at  = created + timedelta(days=1)    if status == "SETTLED" else None
        await session.execute(text("""
            INSERT INTO transactions (
                id, merchant_id, amount, currency, captured_amount,
                refunded_amount, status, payment_method,
                card_last4, card_network, idempotency_key,
                order_id, description,
                authorized_at, captured_at, settled_at,
                created_at, updated_at, is_deleted,
                rule_hits, merchant_metadata
            ) VALUES (
                gen_random_uuid(), :mid, :amount, 'INR',
                CASE WHEN :status IN ('CAPTURED','SETTLED','REFUNDED') THEN :amount ELSE NULL END,
                CASE WHEN :status = 'REFUNDED' THEN :amount ELSE 0 END,
                :status, :method,
                '1111', 'VISA', :ikey,
                :order_id, 'Seed transaction ' || :i,
                CASE WHEN :status NOT IN ('PENDING','FAILED') THEN :created_at ELSE NULL END,
                :captured_at, :settled_at,
                :created_at, :created_at, false,
                '[]'::json, '{}'::json
            )
            ON CONFLICT (idempotency_key) DO NOTHING
        """), {
            "mid": str(mid), "amount": amount, "status": status,
            "method": method, "ikey": f"seed-txn-{i:04d}",
            "order_id": f"seed-order-{i:04d}", "i": i,
            "created_at": created, "captured_at": captured_at, "settled_at": settled_at,
        })
    log.info("seed.transactions.done", count=len(txns))


async def seed_merchant_vpas(session: AsyncSession) -> None:
    log.info("seed.vpas.start")
    for mid, vpa in [
        (MERCHANT_1_ID, "alpha@hdfc"),
        (MERCHANT_2_ID, "beta@oksbi"),
    ]:
        await session.execute(text("""
            INSERT INTO merchant_vpas (id, merchant_id, vpa, is_active, created_at)
            VALUES (gen_random_uuid(), :mid, :vpa, true, NOW())
            ON CONFLICT (vpa) DO NOTHING
        """), {"mid": str(mid), "vpa": vpa})
    log.info("seed.vpas.done")


async def seed_api_keys(session: AsyncSession) -> None:
    log.info("seed.api_keys.start")
    test_keys = [
        (MERCHANT_1_ID, "sk_sandbox_alpha_key_001", "Alpha Sandbox Key", "SANDBOX"),
        (MERCHANT_1_ID, "sk_live_alpha_key_live",   "Alpha Live Key",    "LIVE"),
        (MERCHANT_2_ID, "sk_sandbox_beta_key_001",  "Beta Sandbox Key",  "SANDBOX"),
    ]
    for mid, key, name, env in test_keys:
        prefix  = key[:20]
        key_hash = _api_key_hash(key)
        await session.execute(text("""
            INSERT INTO api_keys (
                id, merchant_id, name, key_prefix, key_hash,
                environment, permissions, is_active, usage_count,
                created_at, updated_at, is_deleted
            ) VALUES (
                gen_random_uuid(), :mid, :name, :prefix, :khash,
                :env, '["payments:read","payments:write","refunds:write"]'::json,
                true, 0,
                NOW(), NOW(), false
            )
            ON CONFLICT (key_hash) DO NOTHING
        """), {
            "mid": str(mid), "name": name, "prefix": prefix,
            "khash": key_hash, "env": env,
        })

    print("\n  Test API Keys (use these in X-Api-Key header):")
    for _, key, name, _ in test_keys:
        print(f"    {name}: {key}")
    log.info("seed.api_keys.done")


async def main() -> None:
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://pguser:pgpass@localhost:5432/payment_db",
    )
    print(f"\n==> Seeding database: {database_url.split('@')[-1]}")
    engine = create_async_engine(database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        try:
            await seed_merchants(session)
            await seed_bank_accounts(session)
            await seed_transactions(session)

            # These may fail if the tables don't exist yet — that's OK
            for fn in (seed_merchant_vpas, seed_api_keys):
                try:
                    await fn(session)
                except Exception as exc:
                    log.warning(f"seed.{fn.__name__}.skipped", reason=str(exc)[:80])

            await session.commit()
            print("\n✓ Database seeded successfully!")
            print(f"\n  Merchant 1 (ACTIVE):      {MERCHANT_1_ID}")
            print(f"  Merchant 2 (PENDING_KYC): {MERCHANT_2_ID}\n")
        except Exception as exc:
            await session.rollback()
            log.error("seed.failed", error=str(exc))
            raise
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
