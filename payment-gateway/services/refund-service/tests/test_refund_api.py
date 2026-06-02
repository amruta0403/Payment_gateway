"""Tests for refund service API."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.db.base import Base
from shared.utils.encryption import FieldEncryptor

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_test_factory = async_sessionmaker(_test_engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def _test_lifespan(app):
    import models.refund  # noqa
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    settings_mock = MagicMock()
    settings_mock.ENVIRONMENT = "development"
    settings_mock.PAYMENT_SERVICE_URL = "http://payment-service:8010"
    settings_mock.UPI_SERVICE_URL = "http://upi-service:8014"
    settings_mock.INTERNAL_SERVICE_TOKEN = "test-token"

    app.state.session_factory = _test_factory
    app.state.redis = AsyncMock()
    app.state.kafka_producer = None
    app.state.settings = settings_mock
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _test_engine.dispose()


import main as _main
_main.app.router.lifespan_context = _test_lifespan


class FakePrincipal:
    sub = str(uuid.uuid4())
    merchant_id = uuid.uuid4()
    roles = ["MERCHANT_OWNER"]


@pytest_asyncio.fixture
async def client(tmp_path):
    from main import app
    from dependencies import get_db_session, get_principal

    principal = FakePrincipal()

    async def _fake_db():
        async with _test_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _fake_db
    app.dependency_overrides[get_principal] = lambda: principal

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, principal

    app.dependency_overrides.clear()


def _refund_payload(txn_id: str = None) -> dict:
    return {
        "transaction_id": txn_id or str(uuid.uuid4()),
        "amount": 5000,
        "reason": "Customer requested refund",
        "idempotency_key": f"idem_{uuid.uuid4().hex}",
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_create_refund_dev_mode_succeeds(client):
    http, principal = client
    txn_id = str(uuid.uuid4())

    # Mock payment-service fetch call
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": txn_id,
        "merchant_id": str(principal.merchant_id),
        "amount": 10000,
        "refunded_amount": 0,
        "currency": "INR",
        "status": "CAPTURED",
        "payment_method": "CARD",
    }

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = mock_http
        mock_http.get.return_value = mock_resp
        mock_http.post.return_value = MagicMock(status_code=500)  # acquirer fails → dev mock

        resp = await http.post("/v1/refunds", json=_refund_payload(txn_id))

    assert resp.status_code == 201
    data = resp.json()
    assert data["amount"] == 5000
    assert data["status"] in ("SUCCESS", "PROCESSING", "INITIATED")
    assert str(data["transaction_id"]) == txn_id


@pytest.mark.anyio
async def test_create_refund_idempotency(client):
    http, principal = client
    payload = _refund_payload()
    txn_id = payload["transaction_id"]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": txn_id, "merchant_id": str(principal.merchant_id),
        "amount": 10000, "refunded_amount": 0, "currency": "INR",
        "status": "CAPTURED", "payment_method": "CARD",
    }

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = mock_http
        mock_http.get.return_value = mock_resp
        mock_http.post.return_value = MagicMock(status_code=500)

        r1 = await http.post("/v1/refunds", json=payload)
        r2 = await http.post("/v1/refunds", json=payload)

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


@pytest.mark.anyio
async def test_create_refund_amount_too_large(client):
    http, principal = client
    payload = {**_refund_payload(), "amount": 99999999}
    txn_id = payload["transaction_id"]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": txn_id, "merchant_id": str(principal.merchant_id),
        "amount": 5000, "refunded_amount": 0, "currency": "INR",
        "status": "CAPTURED", "payment_method": "CARD",
    }

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = mock_http
        mock_http.get.return_value = mock_resp

        resp = await http.post("/v1/refunds", json=payload)

    assert resp.status_code == 400


@pytest.mark.anyio
async def test_get_refund_not_found(client):
    http, _ = client
    resp = await http.get(f"/v1/refunds/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_list_payment_refunds_empty(client):
    http, _ = client
    resp = await http.get(f"/v1/payments/{uuid.uuid4()}/refunds")
    assert resp.status_code == 200
    assert resp.json() == []
