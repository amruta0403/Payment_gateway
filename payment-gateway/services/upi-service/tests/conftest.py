from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
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


def _make_mock_redis():
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock()
    r.setex = AsyncMock()
    r.exists = AsyncMock(return_value=False)
    r.ping = AsyncMock(return_value=True)
    r.aclose = AsyncMock()
    return r


# ── Fake principal ────────────────────────────────────────────────────────────

class FakePrincipal:
    sub: str = str(uuid.uuid4())
    merchant_id: uuid.UUID = uuid.uuid4()
    roles: list[str] = ["MERCHANT_OWNER"]


# ── Test lifespan ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def _test_lifespan(app):
    import models.upi_transaction  # noqa: F401

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from adapters.mock_npci import MockNpciClient
    from services.upi_service import UpiService

    mock_redis = _make_mock_redis()
    enc = FieldEncryptor(TEST_ENC_KEY)

    npci_client = MockNpciClient(
        session_factory=_test_factory,
        kafka_producer=None,
        resolution_delay=0,  # instant resolution in tests
    )

    settings_mock = MagicMock()
    settings_mock.ENVIRONMENT = "development"
    settings_mock.GATEWAY_VPA = "test@upi"
    settings_mock.NPCI_CALLBACK_SECRET = "test-secret"

    app.state.session_factory = _test_factory
    app.state.redis = mock_redis
    app.state.kafka_producer = None
    app.state.encryptor = enc
    app.state.settings = settings_mock
    app.state.upi_service = UpiService(
        npci_client=npci_client,
        session_factory=_test_factory,
        redis=mock_redis,
        kafka_producer=None,
        encryptor=enc,
        gateway_vpa="test@upi",
    )

    yield

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _test_engine.dispose()


import main as _main  # noqa: E402
_main.app.router.lifespan_context = _test_lifespan


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db_session():
    async with _test_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session):
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
def mock_npci():
    from adapters.mock_npci import MockNpciClient
    return MockNpciClient(
        session_factory=_test_factory,
        kafka_producer=None,
        resolution_delay=0,
    )


BASE_COLLECT_PAYLOAD = {
    "payment_id": str(uuid.uuid4()),
    "payer_vpa": "success@upi",
    "amount": 10000,
    "description": "Test payment",
    "expiry_seconds": 300,
    "merchant_vpa": "test@upi",
}
