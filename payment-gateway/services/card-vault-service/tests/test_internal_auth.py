from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import DEV_KEY_STORE, DEV_KEY_B64

VALID_PAYLOAD = {
    "pan": "4111111111111111",
    "expiry_month": 12,
    "expiry_year": 2030,
    "cvv": "123",
    "merchant_id": str(uuid.uuid4()),
}


@pytest.fixture
async def raw_client(engine):
    """Client WITHOUT the X-Service-Token header pre-set."""
    from main import app
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    from unittest.mock import AsyncMock, MagicMock
    from services.encryption import CardVaultEncryptor
    from config import Settings

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock()
    pipeline_mock = AsyncMock()
    pipeline_mock.execute = AsyncMock(return_value=[0, None, 0, None])
    mock_redis.pipeline = MagicMock(return_value=pipeline_mock)

    s = Settings(
        INTERNAL_SERVICE_TOKEN="correct-token",
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
        # No X-Service-Token header
    ) as c:
        yield c


# ── Missing token → 403 ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_service_token_returns_403(raw_client):
    resp = await raw_client.post("/vault/tokenize", json=VALID_PAYLOAD)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_wrong_service_token_returns_403(raw_client):
    resp = await raw_client.post(
        "/vault/tokenize",
        json=VALID_PAYLOAD,
        headers={"X-Service-Token": "wrong-token"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_correct_token_allows_access(raw_client):
    resp = await raw_client.post(
        "/vault/tokenize",
        json=VALID_PAYLOAD,
        headers={"X-Service-Token": "correct-token"},
    )
    # 201 = authorized and processed
    assert resp.status_code == 201


# ── Health endpoint is exempt from auth ──────────────────────────────────────

@pytest.mark.asyncio
async def test_health_exempt_from_auth(raw_client):
    resp = await raw_client.get("/health")
    # No token provided — should not return 403
    assert resp.status_code != 403


# ── Empty string token → 403 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_string_token_returns_403(raw_client):
    resp = await raw_client.post(
        "/vault/tokenize",
        json=VALID_PAYLOAD,
        headers={"X-Service-Token": ""},
    )
    assert resp.status_code == 403


# ── charge-data also requires token ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_charge_data_requires_token(raw_client):
    resp = await raw_client.post(
        "/vault/charge-data",
        json={"token": str(uuid.uuid4())},
    )
    assert resp.status_code == 403
