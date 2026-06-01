from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from models.payment import Transaction, TransactionEvent
from shared.exceptions.handlers import InvalidTransitionError
from shared.models.enums import PaymentMethod, TransactionStatus
from state_machine import PaymentStateMachine


@pytest.fixture
def db():
    mock = AsyncMock()
    mock.add = MagicMock()
    mock.flush = AsyncMock()
    return mock


@pytest.fixture
def payment(make_transaction):
    return make_transaction(status=TransactionStatus.CREATED)


# ── Valid transitions ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_created_to_pending(payment, db):
    result = await PaymentStateMachine.transition(
        payment, TransactionStatus.PENDING, db, triggered_by="test"
    )
    assert result.status == TransactionStatus.PENDING
    db.add.assert_called_once()
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_pending_to_processing(make_transaction, db):
    p = make_transaction(status=TransactionStatus.PENDING)
    await PaymentStateMachine.transition(p, TransactionStatus.PROCESSING, db, "test")
    assert p.status == TransactionStatus.PROCESSING


@pytest.mark.asyncio
async def test_processing_to_authorized(make_transaction, db):
    p = make_transaction(status=TransactionStatus.PROCESSING)
    await PaymentStateMachine.transition(p, TransactionStatus.AUTHORIZED, db, "test")
    assert p.status == TransactionStatus.AUTHORIZED
    assert p.authorized_at is not None


@pytest.mark.asyncio
async def test_authorized_to_captured(make_transaction, db):
    p = make_transaction(status=TransactionStatus.AUTHORIZED)
    await PaymentStateMachine.transition(p, TransactionStatus.CAPTURED, db, "test")
    assert p.status == TransactionStatus.CAPTURED
    assert p.captured_at is not None


@pytest.mark.asyncio
async def test_captured_to_settlement_initiated(make_transaction, db):
    p = make_transaction(status=TransactionStatus.CAPTURED)
    await PaymentStateMachine.transition(p, TransactionStatus.SETTLEMENT_INITIATED, db, "settlement")
    assert p.status == TransactionStatus.SETTLEMENT_INITIATED


@pytest.mark.asyncio
async def test_settlement_initiated_to_settled(make_transaction, db):
    p = make_transaction(status=TransactionStatus.SETTLEMENT_INITIATED)
    await PaymentStateMachine.transition(p, TransactionStatus.SETTLED, db, "settlement")
    assert p.status == TransactionStatus.SETTLED
    assert p.settled_at is not None


@pytest.mark.asyncio
async def test_failed_timestamp_set(make_transaction, db):
    p = make_transaction(status=TransactionStatus.PENDING)
    await PaymentStateMachine.transition(p, TransactionStatus.FAILED, db, "acquirer")
    assert p.status == TransactionStatus.FAILED
    assert p.failed_at is not None


@pytest.mark.asyncio
async def test_cancelled_timestamp_set(make_transaction, db):
    p = make_transaction(status=TransactionStatus.AUTHORIZED)
    await PaymentStateMachine.transition(p, TransactionStatus.CANCELLED, db, "merchant")
    assert p.status == TransactionStatus.CANCELLED
    assert p.cancelled_at is not None


# ── Invalid transitions ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_created_cannot_go_to_captured(payment, db):
    with pytest.raises(InvalidTransitionError):
        await PaymentStateMachine.transition(
            payment, TransactionStatus.CAPTURED, db, "test"
        )


@pytest.mark.asyncio
async def test_created_cannot_go_to_settled(payment, db):
    with pytest.raises(InvalidTransitionError):
        await PaymentStateMachine.transition(
            payment, TransactionStatus.SETTLED, db, "test"
        )


@pytest.mark.asyncio
async def test_failed_is_terminal(make_transaction, db):
    p = make_transaction(status=TransactionStatus.FAILED)
    with pytest.raises(InvalidTransitionError):
        await PaymentStateMachine.transition(p, TransactionStatus.PENDING, db, "test")


@pytest.mark.asyncio
async def test_cancelled_is_terminal(make_transaction, db):
    p = make_transaction(status=TransactionStatus.CANCELLED)
    with pytest.raises(InvalidTransitionError):
        await PaymentStateMachine.transition(p, TransactionStatus.PENDING, db, "test")


@pytest.mark.asyncio
async def test_settled_cannot_go_to_failed(make_transaction, db):
    p = make_transaction(status=TransactionStatus.SETTLED)
    with pytest.raises(InvalidTransitionError):
        await PaymentStateMachine.transition(p, TransactionStatus.FAILED, db, "test")


@pytest.mark.asyncio
async def test_transition_records_event(make_transaction, db):
    p = make_transaction(status=TransactionStatus.CREATED)
    from_status = p.status
    await PaymentStateMachine.transition(
        p, TransactionStatus.PENDING, db, triggered_by="api", message="test message"
    )
    # The TransactionEvent should have been added to the session
    event: TransactionEvent = db.add.call_args[0][0]
    assert event.from_status == from_status
    assert event.to_status == TransactionStatus.PENDING
    assert event.triggered_by == "api"
    assert event.message == "test message"
