from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.db.base import Base

# ── In-memory test DB ─────────────────────────────────────────────────────────
_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_test_factory = async_sessionmaker(_test_engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def _test_lifespan(app):
    import models.settlement_batch      # noqa: F401
    import models.settlement_transaction  # noqa: F401
    import models.settlement_payout     # noqa: F401

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.aclose = AsyncMock()

    settings_mock = MagicMock()
    settings_mock.ENVIRONMENT = "development"

    app.state.session_factory = _test_factory
    app.state.redis = mock_redis
    app.state.kafka_producer = None
    app.state.settings = settings_mock

    yield

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _test_engine.dispose()


import main as _main  # noqa: E402
_main.app.router.lifespan_context = _test_lifespan


class FakePrincipal:
    sub: str = str(uuid.uuid4())
    merchant_id: uuid.UUID = uuid.uuid4()
    roles: list[str] = ["ADMIN", "FINANCE_OPS"]


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
