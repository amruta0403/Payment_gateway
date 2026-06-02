from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.db.base import Base
from shared.utils.encryption import FieldEncryptor

# ── Test DB ───────────────────────────────────────────────────────────────────
TEST_ENC_KEY = FieldEncryptor.generate_key_b64()
_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_test_factory = async_sessionmaker(_test_engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def _test_lifespan(app):
    """Replace real lifespan — no PostgreSQL/Redis/Kafka needed."""
    # Import models so metadata is populated before create_all
    import models.merchant  # noqa: F401
    import models.merchant_bank_account  # noqa: F401
    import models.kyc_document  # noqa: F401
    import models.api_key  # noqa: F401
    import models.merchant_webhook  # noqa: F401

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    settings_mock = MagicMock()
    settings_mock.ENVIRONMENT = "development"
    settings_mock.S3_KYC_BUCKET = "test-bucket"
    settings_mock.KEYCLOAK_URL = "http://keycloak:8080"
    settings_mock.KEYCLOAK_REALM = "payment-gateway"
    settings_mock.RAZORPAY_KEY_ID = ""
    settings_mock.RAZORPAY_KEY_SECRET = ""

    app.state.session_factory = _test_factory
    app.state.encryptor = FieldEncryptor(TEST_ENC_KEY)
    app.state.kafka_producer = None
    app.state.s3_client = None
    app.state.redis = AsyncMock()
    app.state.settings = settings_mock

    yield

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _test_engine.dispose()


# Patch the lifespan before any test imports `app`
import main as _main_module  # noqa: E402
_main_module.app.router.lifespan_context = _test_lifespan


# ── Principal stub ────────────────────────────────────────────────────────────

class FakePrincipal:
    sub: str = str(uuid.uuid4())
    merchant_id: uuid.UUID | None = None
    roles: list[str] = ["MERCHANT_OWNER"]
    email: str = "test@example.com"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with _test_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    from main import app
    from dependencies import get_db_session, get_principal

    principal = FakePrincipal()

    async def _fake_db():
        yield db_session

    app.dependency_overrides[get_db_session] = _fake_db
    app.dependency_overrides[get_principal] = lambda: principal

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, principal

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def merchant(db_session: AsyncSession, client):
    """Create a test merchant via the API and return (merchant_id, principal)."""
    http, principal = client
    resp = await http.post(
        "/v1/merchants/register",
        json={
            "business_name": "Test Merchants Pvt Ltd",
            "business_type": "PRIVATE_LIMITED",
            "pan": "ABCDE1234F",
            "gstin": "27ABCDE1234F1Z5",
            "website_url": "https://example.com",
            "support_email": "support@example.com",
            "support_phone": "+919876543210",
            "business_category": "5411",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    merchant_id = uuid.UUID(data["id"])
    # Set principal's merchant_id so subsequent calls pass access checks
    principal.merchant_id = merchant_id
    return merchant_id, principal
