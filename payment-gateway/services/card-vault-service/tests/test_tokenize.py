from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

MERCHANT_ID = str(uuid.uuid4())
VALID_PAYLOAD = {
    "pan": "4111111111111111",
    "expiry_month": 12,
    "expiry_year": 2030,
    "cvv": "123",
    "cardholder_name": "Test User",
    "merchant_id": MERCHANT_ID,
}


# ── Happy path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tokenize_success(client):
    resp = await client.post("/vault/tokenize", json=VALID_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()

    assert "token" in data
    assert data["last4"] == "1111"
    assert data["first6"] == "411111"
    assert "pan" not in str(data)          # PAN must never appear in response
    assert "cvv" not in str(data)          # CVV must never appear in response
    assert data["card_network"] == "VISA"
    assert data["is_domestic"] is True     # default


@pytest.mark.asyncio
async def test_tokenize_returns_uuid_token(client):
    resp = await client.post("/vault/tokenize", json=VALID_PAYLOAD)
    assert resp.status_code == 201
    token_str = resp.json()["token"]
    # Must parse as UUID
    uuid.UUID(token_str)


# ── Deduplication ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tokenize_dedup_same_token(client):
    """Same PAN + merchant → same token returned."""
    r1 = await client.post("/vault/tokenize", json=VALID_PAYLOAD)
    r2 = await client.post("/vault/tokenize", json=VALID_PAYLOAD)
    assert r1.status_code == r2.status_code == 201
    assert r1.json()["token"] == r2.json()["token"]


@pytest.mark.asyncio
async def test_tokenize_different_merchant_different_token(client):
    """Same PAN + different merchant → different tokens."""
    payload2 = {**VALID_PAYLOAD, "merchant_id": str(uuid.uuid4())}
    r1 = await client.post("/vault/tokenize", json=VALID_PAYLOAD)
    r2 = await client.post("/vault/tokenize", json=payload2)
    assert r1.status_code == r2.status_code == 201
    assert r1.json()["token"] != r2.json()["token"]


# ── Expired card ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tokenize_expired_card_rejected(client):
    payload = {**VALID_PAYLOAD, "expiry_year": 2020, "expiry_month": 1}
    resp = await client.post("/vault/tokenize", json=payload)
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()


# ── Invalid Luhn ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tokenize_invalid_luhn_rejected(client):
    payload = {**VALID_PAYLOAD, "pan": "4111111111111112"}  # bad check digit
    resp = await client.post("/vault/tokenize", json=payload)
    # Could be 422 (Pydantic) or 400 (runtime check)
    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_tokenize_non_digit_pan_rejected(client):
    payload = {**VALID_PAYLOAD, "pan": "411111111111111X"}
    resp = await client.post("/vault/tokenize", json=payload)
    assert resp.status_code == 422


# ── Response must never contain PAN ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_tokenize_response_contains_no_pan(client):
    resp = await client.post("/vault/tokenize", json=VALID_PAYLOAD)
    assert resp.status_code == 201
    body_str = resp.text
    # Full PAN must not appear
    assert "4111111111111111" not in body_str
    # CVV must not appear
    assert "123" not in body_str.replace('"201"', "")  # status code 201 is OK
