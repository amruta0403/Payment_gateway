"""
Tests for the reconcile Celery task and FastAPI settlement API endpoints.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from models.settlement_batch import SettlementBatch, SettlementStatus
from models.settlement_payout import PayoutStatus, SettlementPayout
from models.settlement_transaction import SettlementTransaction


async def _insert_batch(db, merchant_id=None, status=SettlementStatus.COMPLETED, net=10000):
    mid = merchant_id or uuid.uuid4()
    batch = SettlementBatch(
        merchant_id=mid,
        settlement_date=date.today(),
        gross_amount=12360,
        fee_amount=2000,
        gst_on_fee=360,
        net_amount=net,
        transaction_count=1,
        status=status,
    )
    db.add(batch)
    await db.flush()
    return batch


# ── Reconcile task unit tests ─────────────────────────────────────────────────

@patch("tasks.settlement.get_sync_db")
@patch("tasks.settlement.initiate_payout")
def test_reconcile_requeues_failed_batches(mock_initiate, mock_db_ctx):
    from tasks.settlement import reconcile

    failed = MagicMock()
    failed.id = uuid.uuid4()
    failed.status = SettlementStatus.FAILED
    failed.settlement_date = (datetime.utcnow() - timedelta(days=1)).date()

    stuck = []

    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.side_effect = [
        [failed],  # failed batches query
        stuck,     # stuck batches query
    ]

    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=db)
    cm.__exit__ = MagicMock(return_value=False)
    mock_db_ctx.return_value = cm

    result = reconcile.run()

    mock_initiate.delay.assert_called_once_with(str(failed.id))
    assert result["requeued"] == 1
    assert result["stuck"] == 0


@patch("tasks.settlement.get_sync_db")
@patch("tasks.settlement.initiate_payout")
def test_reconcile_alerts_on_stuck_batches(mock_initiate, mock_db_ctx, caplog):
    import logging
    from tasks.settlement import reconcile

    stuck_batch = MagicMock()
    stuck_batch.id = uuid.uuid4()
    stuck_batch.status = SettlementStatus.PROCESSING
    stuck_batch.settlement_date = (datetime.utcnow() - timedelta(days=7)).date()

    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.side_effect = [[], [stuck_batch]]

    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=db)
    cm.__exit__ = MagicMock(return_value=False)
    mock_db_ctx.return_value = cm

    result = reconcile.run()
    assert result["stuck"] == 1
    mock_initiate.delay.assert_not_called()


# ── FastAPI endpoint tests ────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_list_settlements_empty(client):
    http, _ = client
    resp = await http.get("/v1/settlements")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.anyio
async def test_list_settlements_returns_batches(client, db_session):
    http, principal = client
    batch = await _insert_batch(db_session, status=SettlementStatus.COMPLETED)
    await db_session.commit()

    resp = await http.get("/v1/settlements")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["status"] == "COMPLETED"


@pytest.mark.anyio
async def test_get_settlement_detail(client, db_session):
    http, _ = client
    batch = await _insert_batch(db_session)
    await db_session.commit()

    resp = await http.get(f"/v1/settlements/{batch.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(batch.id)
    assert "transactions" in data
    assert "payouts" in data


@pytest.mark.anyio
async def test_get_settlement_not_found(client):
    http, _ = client
    resp = await http.get(f"/v1/settlements/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.anyio
@patch("tasks.settlement.create_daily_batch")
async def test_trigger_settlement(mock_task, client):
    http, _ = client
    resp = await http.post(
        "/v1/admin/settlements/trigger",
        json={"settlement_date": str(date.today())},
    )
    assert resp.status_code == 202
    mock_task.delay.assert_called_once()


@pytest.mark.anyio
async def test_retry_payout_failed_batch(client, db_session):
    http, _ = client
    batch = await _insert_batch(db_session, status=SettlementStatus.FAILED)
    await db_session.commit()

    with patch("tasks.settlement.initiate_payout") as mock_payout:
        resp = await http.post(f"/v1/admin/settlements/{batch.id}/retry-payout")
        assert resp.status_code == 202
        mock_payout.delay.assert_called_once_with(str(batch.id))


@pytest.mark.anyio
async def test_retry_payout_completed_batch_rejected(client, db_session):
    http, _ = client
    batch = await _insert_batch(db_session, status=SettlementStatus.COMPLETED)
    await db_session.commit()

    resp = await http.post(f"/v1/admin/settlements/{batch.id}/retry-payout")
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_rbi_report_csv(client, db_session):
    http, _ = client
    batch = await _insert_batch(db_session, status=SettlementStatus.COMPLETED)
    await db_session.commit()

    start = date.today() - timedelta(days=1)
    end = date.today() + timedelta(days=1)
    resp = await http.get(f"/v1/admin/reports/rbi?start_date={start}&end_date={end}")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    body = resp.text
    assert "Batch ID" in body
    assert "Merchant ID" in body
