from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from shared.models.enums import TransactionStatus


# ── POST /v1/payments ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_payment_card_success(client):
    resp = await client.post(
        "/v1/payments",
        json={
            "amount": 10000,
            "currency": "INR",
            "payment_method": "CARD",
            "card": {
                "number": "4111111111111111",
                "expiry_month": 12,
                "expiry_year": 2026,
                "cvv": "123",
                "cardholder_name": "Test User",
            },
            "customer": {
                "email": "test@example.com",
                "phone": "+919876543210",
                "name": "Test User",
            },
        },
        headers={"X-Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == TransactionStatus.CAPTURED.value
    assert data["payment_method"] == "CARD"
    assert data["amount"] == 10000


@pytest.mark.asyncio
async def test_create_payment_missing_idempotency_key(client):
    resp = await client.post(
        "/v1/payments",
        json={
            "amount": 10000,
            "currency": "INR",
            "payment_method": "CARD",
            "card": {
                "number": "4111111111111111",
                "expiry_month": 12,
                "expiry_year": 2026,
                "cvv": "123",
            },
            "customer": {"email": "test@example.com", "phone": "+919876543210"},
        },
    )
    assert resp.status_code == 400
    assert "Idempotency" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_payment_invalid_amount_zero(client):
    resp = await client.post(
        "/v1/payments",
        json={
            "amount": 0,
            "currency": "INR",
            "payment_method": "CARD",
            "card": {
                "number": "4111111111111111",
                "expiry_month": 12,
                "expiry_year": 2026,
                "cvv": "123",
            },
            "customer": {"email": "test@example.com", "phone": "+919876543210"},
        },
        headers={"X-Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 422  # Pydantic validation


@pytest.mark.asyncio
async def test_create_payment_invalid_luhn(client):
    resp = await client.post(
        "/v1/payments",
        json={
            "amount": 10000,
            "currency": "INR",
            "payment_method": "CARD",
            "card": {
                "number": "4111111111111112",  # fails Luhn
                "expiry_month": 12,
                "expiry_year": 2026,
                "cvv": "123",
            },
            "customer": {"email": "test@example.com", "phone": "+919876543210"},
        },
        headers={"X-Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_payment_fraud_blocked(client):
    from unittest.mock import patch

    fraud_resp = {
        "fraud_score": 0.95,
        "decision": "BLOCK",
        "rule_hits": ["ip_blacklist"],
        "reasons": ["ip_blacklist"],
    }
    with patch(
        "services.http_client.ServiceClient.post",
        new_callable=AsyncMock,
        return_value=fraud_resp,
    ):
        resp = await client.post(
            "/v1/payments",
            json={
                "amount": 10000,
                "currency": "INR",
                "payment_method": "CARD",
                "card": {
                    "number": "4111111111111111",
                    "expiry_month": 12,
                    "expiry_year": 2026,
                    "cvv": "123",
                },
                "customer": {"email": "fraud@example.com", "phone": "+919876543210"},
            },
            headers={"X-Idempotency-Key": str(uuid.uuid4())},
        )
    assert resp.status_code == 402
    assert resp.json()["error"]["code"] == "FRAUD_BLOCKED"


@pytest.mark.asyncio
async def test_create_payment_declined_card(client):
    resp = await client.post(
        "/v1/payments",
        json={
            "amount": 10000,
            "currency": "INR",
            "payment_method": "CARD",
            "card": {
                "number": "4000000000000002",  # insufficient_funds
                "expiry_month": 12,
                "expiry_year": 2026,
                "cvv": "123",
            },
            "customer": {"email": "test@example.com", "phone": "+919876543210"},
        },
        headers={"X-Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 402
    assert resp.json()["error"]["code"] == "CARD_DECLINED"


@pytest.mark.asyncio
async def test_idempotency_replay(client):
    idem_key = str(uuid.uuid4())
    payload = {
        "amount": 10000,
        "currency": "INR",
        "payment_method": "CARD",
        "card": {
            "number": "4111111111111111",
            "expiry_month": 12,
            "expiry_year": 2026,
            "cvv": "123",
        },
        "customer": {"email": "test@example.com", "phone": "+919876543210"},
    }

    resp1 = await client.post("/v1/payments", json=payload, headers={"X-Idempotency-Key": idem_key})
    assert resp1.status_code == 201
    first_id = resp1.json()["id"]

    # Second request with same key should return cached response
    # (In test, Redis mock returns None first time; we need to simulate cache hit)
    # This tests the idempotency path via Redis mock returning cached data
    from unittest.mock import patch
    import json
    cached_resp = resp1.json()
    with patch(
        "shared.cache.redis_client.get_idempotency",
        new_callable=AsyncMock,
        return_value=cached_resp,
    ):
        resp2 = await client.post("/v1/payments", json=payload, headers={"X-Idempotency-Key": idem_key})
    assert resp2.status_code == 201
    assert resp2.json()["id"] == first_id


# ── GET /v1/payments ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_payments_returns_200(client):
    resp = await client.get("/v1/payments")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


# ── GET /v1/payments/{id} ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_nonexistent_payment_returns_404(client):
    resp = await client.get(f"/v1/payments/{uuid.uuid4()}")
    assert resp.status_code == 404
