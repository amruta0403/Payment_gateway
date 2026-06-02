"""Tests for audit log API endpoints."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.db.base import Base

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_test_factory = async_sessionmaker(_test_engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def _test_lifespan(app):
    import models.audit_log  # noqa
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    settings_mock = MagicMock()
    settings_mock.ENVIRONMENT = "development"
    settings_mock.KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"

    app.state.session_factory = _test_factory
    app.state.redis = AsyncMock()
    app.state.kafka_producer = None
    app.state.settings = settings_mock

    # Mock the Kafka consumer task so it doesn't try to connect
    import asyncio
    async def _noop():
        await asyncio.sleep(9999)
    app.state.consumer_task = asyncio.create_task(_noop())

    yield

    app.state.consumer_task.cancel()
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _test_engine.dispose()


import main as _main
_main.app.router.lifespan_context = _test_lifespan


class FakePrincipal:
    sub = str(uuid.uuid4())
    merchant_id = uuid.uuid4()
    roles = ["COMPLIANCE_OFFICER", "ADMIN"]


@pytest_asyncio.fixture
async def client():
    from main import app
    from dependencies import get_db_session, get_principal

    principal = FakePrincipal()

    async def _fake_db():
        async with _test_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _fake_db
    app.dependency_overrides[get_principal] = lambda: principal

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


async def _insert_log(db_session, service="payment-service", action="payment.captured"):
    from models.audit_log import AuditLog
    log = AuditLog(
        service=service,
        entity_type="transaction",
        action=action,
        merchant_id=uuid.uuid4(),
        metadata_={"test": True},
        kafka_topic="payment.captured",
    )
    db_session.add(log)
    await db_session.commit()
    return log


@pytest.mark.anyio
async def test_list_audit_logs_empty(client):
    resp = await client.get("/v1/audit/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["has_more"] is False


@pytest.mark.anyio
async def test_list_audit_logs_returns_entries(client):
    async with _test_factory() as session:
        await _insert_log(session, service="payment-service")
        await _insert_log(session, service="merchant-service")

    resp = await client.get("/v1/audit/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) >= 2


@pytest.mark.anyio
async def test_list_audit_logs_filter_by_service(client):
    async with _test_factory() as session:
        await _insert_log(session, service="upi-service")

    resp = await client.get("/v1/audit/logs?service=upi-service")
    assert resp.status_code == 200
    items = resp.json()["items"]
    for item in items:
        assert item["service"] == "upi-service"


@pytest.mark.anyio
async def test_export_csv_max_31_days(client):
    from datetime import date, timedelta
    start = date(2025, 1, 1)
    end = start + timedelta(days=35)
    resp = await client.get(f"/v1/audit/logs/export?start_date={start}&end_date={end}")
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_export_csv_valid_range(client):
    from datetime import date, timedelta
    start = date(2025, 1, 1)
    end = start + timedelta(days=7)
    resp = await client.get(f"/v1/audit/logs/export?start_date={start}&end_date={end}")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "audit_" in resp.headers["content-disposition"]


@pytest.mark.anyio
async def test_kong_access_log_ingestion(client):
    payload = {
        "service": "payment-service",
        "request_id": str(uuid.uuid4()),
        "method": "POST",
        "path": "/v1/payments",
        "status_code": 201,
        "latency_ms": 45,
        "client_ip": "1.2.3.4",
    }
    resp = await client.post("/v1/internal/kong-access-log", json=payload)
    assert resp.status_code == 202
    assert resp.json()["accepted"] is True


@pytest.mark.anyio
async def test_sanitizer_integration_in_consumer():
    """Confirm sanitise_for_audit strips PAN from Kafka event data."""
    from services.sanitizer import sanitise_for_audit
    event = {
        "payment_id": str(uuid.uuid4()),
        "pan": "4111111111111111",
        "amount": 10000,
    }
    clean = sanitise_for_audit(event)
    assert clean["pan"] == "[REDACTED]"
    assert clean["amount"] == 10000
