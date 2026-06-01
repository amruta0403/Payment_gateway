from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models.payment import Transaction, TransactionEvent
from shared.db.base import Base
from shared.models.enums import PaymentMethod, TransactionStatus


@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncSession:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def make_transaction():
    def _make(
        status: TransactionStatus = TransactionStatus.CREATED,
        payment_method: PaymentMethod = PaymentMethod.CARD,
        amount: int = 10000,
        merchant_id: uuid.UUID | None = None,
    ) -> Transaction:
        t = Transaction(
            id=uuid.uuid4(),
            merchant_id=merchant_id or uuid.uuid4(),
            amount=amount,
            currency="INR",
            status=status,
            payment_method=payment_method,
            idempotency_key=str(uuid.uuid4()),
        )
        return t
    return _make


@pytest_asyncio.fixture
async def client(engine):
    from main import app

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock()
    mock_redis.ping = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=0)
    mock_redis.pipeline = MagicMock(return_value=AsyncMock())

    mock_producer = AsyncMock()
    mock_producer.publish = AsyncMock()

    mock_principal = MagicMock()
    mock_principal.merchant_id = str(uuid.uuid4())
    mock_principal.sub = str(uuid.uuid4())
    combined_dep = AsyncMock(return_value=mock_principal)
    mock_keycloak = MagicMock()
    mock_keycloak.get_combined_auth_dependency = MagicMock(return_value=combined_dep)

    from adapters.mock import MockAcquirerAdapter

    app.state.session_factory = factory
    app.state.redis = mock_redis
    app.state.kafka_producer = mock_producer
    app.state.keycloak_validator = mock_keycloak
    app.state.acquirer = MockAcquirerAdapter()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
from httpx import ASGITransport, AsyncClient

from main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
