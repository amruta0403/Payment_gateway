from __future__ import annotations

import base64
import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models.card_token import VaultBase
from services.encryption import CardVaultEncryptor

DEV_KEY = os.urandom(32)
DEV_KEY_STORE = {1: DEV_KEY}
DEV_KEY_B64 = base64.b64encode(DEV_KEY).decode()

VALID_PAN = "4111111111111111"
INVALID_PAN = "4111111111111112"


@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(VaultBase.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncSession:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def encryptor() -> CardVaultEncryptor:
    return CardVaultEncryptor(DEV_KEY_STORE)


@pytest_asyncio.fixture
async def client(engine):
    from main import app
    from config import Settings

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock()
    pipeline_mock = AsyncMock()
    pipeline_mock.execute = AsyncMock(return_value=[0, None, 0, None])
    mock_redis.pipeline = MagicMock(return_value=pipeline_mock)

    s = Settings(
        INTERNAL_SERVICE_TOKEN="test-token",
        SKIP_SUBNET_CHECK=True,
        VAULT_DATABASE_URL="sqlite+aiosqlite:///:memory:",
        CARD_ENCRYPTION_KEY_V1=DEV_KEY_B64,
    )
    app.state.session_factory = factory
    app.state.redis = mock_redis
    app.state.encryptor = CardVaultEncryptor(DEV_KEY_STORE)
    app.state.settings = s

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Service-Token": "test-token"},
    ) as c:
        yield c
from httpx import ASGITransport, AsyncClient

from main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
