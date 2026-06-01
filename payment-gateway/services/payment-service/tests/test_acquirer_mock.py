from __future__ import annotations

import pytest

from adapters.mock import MockAcquirerAdapter


@pytest.fixture
def acquirer() -> MockAcquirerAdapter:
    return MockAcquirerAdapter()


# ── charge() ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_success_card(acquirer):
    result = await acquirer.charge(
        token="tok_abc",
        amount=10000,
        currency="INR",
        metadata={"card_number": "4111111111111111"},
    )
    assert result.success is True
    assert result.gateway_txn_id is not None
    assert result.auth_code is not None
    assert result.rrn is not None


@pytest.mark.asyncio
async def test_insufficient_funds_card(acquirer):
    result = await acquirer.charge(
        token="tok_abc",
        amount=10000,
        currency="INR",
        metadata={"card_number": "4000000000000002"},
    )
    assert result.success is False
    assert result.error_code == "insufficient_funds"


@pytest.mark.asyncio
async def test_expired_card(acquirer):
    result = await acquirer.charge(
        token="tok_abc",
        amount=10000,
        currency="INR",
        metadata={"card_number": "4000000000000069"},
    )
    assert result.success is False
    assert result.error_code == "expired_card"


@pytest.mark.asyncio
async def test_processing_error_card(acquirer):
    result = await acquirer.charge(
        token="tok_abc",
        amount=10000,
        currency="INR",
        metadata={"card_number": "4000000000000119"},
    )
    assert result.success is False
    assert result.error_code == "processing_error"


@pytest.mark.asyncio
async def test_unknown_card_succeeds(acquirer):
    result = await acquirer.charge(
        token="tok_abc",
        amount=50000,
        currency="INR",
        metadata={"card_number": "5500000000000004"},
    )
    assert result.success is True


# ── capture() ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_capture_success(acquirer):
    result = await acquirer.capture(txn_id="mock_gtxn_abc123", amount=10000)
    assert result.success is True
    assert result.gateway_txn_id == "mock_gtxn_abc123"
    assert result.rrn is not None


# ── refund() ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refund_success(acquirer):
    result = await acquirer.refund(txn_id="mock_gtxn_abc123", amount=5000)
    assert result.success is True
    assert result.refund_id is not None


# ── void() ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_void_success(acquirer):
    result = await acquirer.void(txn_id="mock_gtxn_abc123")
    assert result.success is True
