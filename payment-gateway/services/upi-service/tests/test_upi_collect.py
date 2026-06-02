from __future__ import annotations

import uuid

import pytest

from tests.conftest import BASE_COLLECT_PAYLOAD


@pytest.mark.anyio
async def test_collect_success_pending(client):
    http, _ = client
    resp = await http.post("/v1/upi/collect", json=BASE_COLLECT_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] in ("PENDING", "SUCCESS")
    assert data["our_ref_id"].startswith("PG")
    assert "expires_at" in data


@pytest.mark.anyio
async def test_collect_fail_vpa_returns_failed(client):
    http, _ = client
    payload = {**BASE_COLLECT_PAYLOAD, "payer_vpa": "fail@upi", "payment_id": str(uuid.uuid4())}
    resp = await http.post("/v1/upi/collect", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "FAILED"


@pytest.mark.anyio
async def test_collect_invalid_vpa_format(client):
    http, _ = client
    payload = {**BASE_COLLECT_PAYLOAD, "payer_vpa": "not-a-vpa", "payment_id": str(uuid.uuid4())}
    resp = await http.post("/v1/upi/collect", json=payload)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_collect_creates_db_record(client, db_session):
    from sqlalchemy import select
    from models.upi_transaction import UpiTransaction

    http, _ = client
    pid = str(uuid.uuid4())
    payload = {**BASE_COLLECT_PAYLOAD, "payment_id": pid}
    resp = await http.post("/v1/upi/collect", json=payload)
    assert resp.status_code == 201
    our_ref = resp.json()["our_ref_id"]

    txn = (
        await db_session.execute(
            select(UpiTransaction).where(UpiTransaction.our_ref_id == our_ref)
        )
    ).scalar_one_or_none()
    assert txn is not None
    assert str(txn.transaction_id) == pid
    assert txn.amount == 10000


@pytest.mark.anyio
async def test_intent_generates_deep_link(client):
    http, _ = client
    resp = await http.post(
        "/v1/upi/intent",
        json={
            "payment_id": str(uuid.uuid4()),
            "amount": 50000,
            "merchant_vpa": "test@upi",
            "description": "Order #1234",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "upi://pay" in data["upi_deep_link"]
    assert "am=500.00" in data["upi_deep_link"]
    assert data["our_ref_id"].startswith("PG")


@pytest.mark.anyio
async def test_get_transaction_status(client, db_session):
    http, _ = client
    pid = str(uuid.uuid4())
    payload = {**BASE_COLLECT_PAYLOAD, "payment_id": pid}
    await http.post("/v1/upi/collect", json=payload)

    resp = await http.get(f"/v1/upi/transaction/{pid}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "our_ref_id" in data
    assert data["status"] in ("PENDING", "SUCCESS", "FAILED")


@pytest.mark.anyio
async def test_get_status_not_found(client):
    http, _ = client
    resp = await http.get(f"/v1/upi/transaction/{uuid.uuid4()}/status")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_mock_auto_resolution(db_session):
    """With resolution_delay=0, send_collect immediately auto-resolves to SUCCESS."""
    from sqlalchemy import select
    from adapters.mock_npci import MockNpciClient
    from adapters.base import NpciCollectRequest
    from models.upi_transaction import UpiTransaction, UpiStatus

    client = MockNpciClient(
        session_factory=None,  # no DB update in this test
        kafka_producer=None,
        resolution_delay=0,
    )
    ref_id = "PGTEST000001"
    req = NpciCollectRequest(
        our_ref_id=ref_id,
        payer_vpa="success@upi",
        payee_vpa="test@upi",
        amount=10000,
        description="test",
    )
    resp = await client.send_collect(req)
    # With delay=0, _resolve_after runs synchronously
    status_resp = await client.check_status(ref_id)
    assert status_resp.status == UpiStatus.SUCCESS
