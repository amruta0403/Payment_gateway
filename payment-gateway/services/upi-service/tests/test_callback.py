from __future__ import annotations

import json
import uuid

import pytest

from models.upi_transaction import UpiStatus
from tests.conftest import BASE_COLLECT_PAYLOAD


async def _create_txn(http, pid: str | None = None) -> str:
    """Helper: create a collect transaction and return our_ref_id."""
    payload = {**BASE_COLLECT_PAYLOAD, "payment_id": pid or str(uuid.uuid4())}
    resp = await http.post("/v1/upi/collect", json=payload)
    assert resp.status_code == 201
    return resp.json()["our_ref_id"]


def _build_callback(ref_id: str, status: str = "SUCCESS") -> dict:
    return {
        "txnId": f"NPCI{ref_id}",
        "refId": ref_id,
        "txnRef": ref_id,
        "amount": "100.00",
        "status": status,
        "respCode": "00" if status == "SUCCESS" else "U30",
        "respMsg": "Transaction successful" if status == "SUCCESS" else "Declined",
        "payerVPA": "success@upi",
        "payeeVPA": "test@upi",
        "txnAuthDate": "2025-01-01T10:00:00",
    }


@pytest.mark.anyio
async def test_callback_success_updates_status(client, db_session):
    from sqlalchemy import select
    from models.upi_transaction import UpiTransaction

    http, _ = client
    ref_id = await _create_txn(http)

    resp = await http.post(
        "/upi/callback",
        json=_build_callback(ref_id, "SUCCESS"),
        headers={"X-UPI-Signature": "mock-sig"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"

    txn = (
        await db_session.execute(
            select(UpiTransaction).where(UpiTransaction.our_ref_id == ref_id)
        )
    ).scalar_one()
    assert txn.status == UpiStatus.SUCCESS
    assert txn.callback_received_at is not None


@pytest.mark.anyio
async def test_callback_failure_updates_status(client, db_session):
    from sqlalchemy import select
    from models.upi_transaction import UpiTransaction

    http, _ = client
    ref_id = await _create_txn(http)

    resp = await http.post(
        "/upi/callback",
        json=_build_callback(ref_id, "FAILURE"),
        headers={"X-UPI-Signature": "mock-sig"},
    )
    assert resp.status_code == 200

    txn = (
        await db_session.execute(
            select(UpiTransaction).where(UpiTransaction.our_ref_id == ref_id)
        )
    ).scalar_one()
    assert txn.status == UpiStatus.FAILED
    assert txn.decline_code == "U30"


@pytest.mark.anyio
async def test_callback_stores_raw_payload(client, db_session):
    from sqlalchemy import select
    from models.upi_transaction import UpiTransaction

    http, _ = client
    ref_id = await _create_txn(http)
    cb = _build_callback(ref_id)

    await http.post("/upi/callback", json=cb, headers={"X-UPI-Signature": "mock-sig"})

    txn = (
        await db_session.execute(
            select(UpiTransaction).where(UpiTransaction.our_ref_id == ref_id)
        )
    ).scalar_one()
    assert txn.raw_callback is not None
    assert txn.raw_callback["txnId"] == f"NPCI{ref_id}"


@pytest.mark.anyio
async def test_callback_no_signature_accepted_in_mock(client):
    """Mock client's validate_callback always returns True."""
    http, _ = client
    ref_id = await _create_txn(http)
    resp = await http.post(
        "/upi/callback",
        json=_build_callback(ref_id),
        # No X-UPI-Signature header
    )
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_callback_missing_required_field(client):
    http, _ = client
    bad_payload = {
        "txnId": "NPCI123",
        # missing refId and other required fields
        "status": "SUCCESS",
    }
    resp = await http.post("/upi/callback", json=bad_payload)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_mock_validate_callback_always_true(mock_npci):
    valid = await mock_npci.validate_callback(
        headers={"X-UPI-Signature": "bad-sig"},
        body=b'{"some":"payload"}',
    )
    assert valid is True
