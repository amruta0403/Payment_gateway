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


# ── Mock Redis with pipeline support ──────────────────────────────────────────

class _MockPipeline:
    def __init__(self):
        self._results = []

    def zremrangebyscore(self, *a, **kw):
        self._results.append(0)
        return self

    def zadd(self, *a, **kw):
        self._results.append(1)
        return self

    def zcard(self, *a, **kw):
        self._results.append(0)   # always 0 count → never velocity-block
        return self

    def expire(self, *a, **kw):
        self._results.append(True)
        return self

    def get(self, *a, **kw):
        self._results.append(None)
        return self

    async def execute(self):
        r = list(self._results)
        self._results.clear()
        return r

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass


def _make_mock_redis():
    r = AsyncMock()
    r.exists = AsyncMock(return_value=False)   # nothing blacklisted
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock(return_value=True)
    r.delete = AsyncMock(return_value=1)
    r.incr = AsyncMock(return_value=1)
    r.ping = AsyncMock(return_value=True)
    r.pipeline = MagicMock(return_value=_MockPipeline())
    r.aclose = AsyncMock()
    return r


# ── Fake principal ────────────────────────────────────────────────────────────

class FakePrincipal:
    sub: str = str(uuid.uuid4())
    merchant_id: uuid.UUID | None = None
    roles: list[str] = ["RISK_ANALYST", "ADMIN"]


# ── Test lifespan — replaces real DB/Redis/Kafka connections ─────────────────

@asynccontextmanager
async def _test_lifespan(app):
    import models.fraud  # noqa: F401 — populate metadata

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from rules.engine import RulesEngine
    from model.scorer import FraudMLScorer

    mock_redis = _make_mock_redis()
    settings_mock = MagicMock()
    settings_mock.ENVIRONMENT = "development"

    app.state.session_factory = _test_factory
    app.state.redis = mock_redis
    app.state.kafka_producer = None
    app.state.rules_engine = RulesEngine(redis=mock_redis)
    app.state.ml_scorer = FraudMLScorer()
    app.state.settings = settings_mock

    yield

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _test_engine.dispose()


# Patch lifespan before any fixture imports `app`
import main as _main  # noqa: E402
_main.app.router.lifespan_context = _test_lifespan


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db_session():
    async with _test_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
def mock_redis():
    return _make_mock_redis()


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
        yield c

    app.dependency_overrides.clear()


# ── Shared scoring payload ────────────────────────────────────────────────────

BASE_SCORING_PAYLOAD = {
    "payment_id": str(uuid.uuid4()),
    "merchant_id": str(uuid.uuid4()),
    "amount": 50000,
    "payment_method": "CARD",
    "ip_address": "27.1.2.3",
    "pan_first6": "411111",
    "card_token": str(uuid.uuid4()),
    "customer_email_hash": "abc123",
}
