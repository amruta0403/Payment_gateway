"""
Tests for create_daily_batch Celery task using mock sync DB.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from unittest.mock import MagicMock, patch, call

import pytest

from utils.fee_calculator import calculate_fee


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_txn(merchant_id, amount=10000, method="CARD", captured_at=None):
    t = MagicMock()
    t.id = uuid.uuid4()
    t.merchant_id = merchant_id
    t.amount = amount
    t.captured_amount = amount
    t.payment_method = method
    t.captured_at = captured_at or datetime(2025, 1, 1, 12, 0, 0)
    t.status = "CAPTURED"
    return t


def _fake_fee_config():
    return {
        "card_mdr_percent": "2.0",
        "upi_flat_fee_paise": 0,
        "netbanking_flat_fee_paise": 1000,
        "gst_percent": "18",
    }


# ── Fee math tests (drive the logic inline) ───────────────────────────────────

def test_batch_fee_math_single_card_txn():
    fee_config = _fake_fee_config()
    txn = _fake_txn(uuid.uuid4(), amount=10000, method="CARD")
    fee = calculate_fee(txn.captured_amount, txn.payment_method, fee_config)

    gross = txn.captured_amount  # 10000
    assert fee.gross == 10000
    assert fee.fee_paise == 200      # 2%
    assert fee.gst_paise == 36       # 18% of 200
    assert fee.net_paise == 9764
    assert gross == fee.fee_paise + fee.gst_paise + fee.net_paise


def test_batch_fee_math_multi_txns():
    fee_config = _fake_fee_config()
    mid = uuid.uuid4()
    txns = [
        _fake_txn(mid, amount=10000, method="CARD"),
        _fake_txn(mid, amount=50000, method="UPI"),
        _fake_txn(mid, amount=30000, method="NETBANKING"),
    ]
    fees = [calculate_fee(t.captured_amount, t.payment_method, fee_config) for t in txns]

    gross = sum(t.captured_amount for t in txns)
    total_fee = sum(f.fee_paise for f in fees)
    total_gst = sum(f.gst_paise for f in fees)
    net = gross - total_fee - total_gst

    # UPI < threshold → no fee
    assert fees[1].fee_paise == 0
    # NETBANKING → 1000 flat
    assert fees[2].fee_paise == 1000
    # Net must be positive
    assert net > 0
    # Components must sum to gross
    assert gross == total_fee + total_gst + net


def test_batch_fee_math_upi_zero_mdr():
    fee_config = _fake_fee_config()
    txn = _fake_txn(uuid.uuid4(), amount=100_000, method="UPI")   # ₹1000 < ₹2000 limit
    fee = calculate_fee(txn.captured_amount, txn.payment_method, fee_config)
    assert fee.fee_paise == 0
    assert fee.net_paise == 100_000


def test_batch_net_never_negative():
    """Validate that even a 100-paise transaction doesn't produce negative net."""
    fee_config = {**_fake_fee_config(), "netbanking_flat_fee_paise": 200_000}  # insane fee
    # Fee bigger than amount — net would be negative
    with pytest.raises(AssertionError, match="Net paise cannot be negative"):
        calculate_fee(100, "NETBANKING", fee_config)


@patch("tasks.settlement.get_sync_db")
@patch("tasks.settlement.initiate_payout")
def test_create_daily_batch_calls_initiate_payout(mock_initiate, mock_db_ctx):
    """Verify create_daily_batch queues initiate_payout for each merchant."""
    from tasks.settlement import _create_batch_for_merchant

    merchant_id = uuid.uuid4()
    settlement_date = date(2025, 1, 1)
    txns = [_fake_txn(merchant_id, 10000, "CARD")]
    fee_config = _fake_fee_config()

    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = txns
    db.execute.return_value.scalar_one_or_none.return_value = fee_config
    db.flush.return_value = None
    db.commit.return_value = None

    # Mock the SettlementBatch add/flush
    batch_mock = MagicMock()
    batch_mock.id = uuid.uuid4()

    with patch("tasks.settlement.SettlementBatch", return_value=batch_mock):
        with patch("tasks.settlement.SettlementTransaction"):
            _create_batch_for_merchant(db, merchant_id, settlement_date)

    mock_initiate.delay.assert_called_once()


def test_fee_breakdown_components_match_gross():
    """Stress test: for 1000 amounts, gross == fee + gst + net always holds."""
    fee_config = _fake_fee_config()
    for amount in range(1, 1001):
        for method in ("CARD", "UPI", "NETBANKING"):
            b = calculate_fee(amount, method, fee_config)
            assert b.gross == b.fee_paise + b.gst_paise + b.net_paise, (
                f"invariant broken for {method} amount={amount}: "
                f"{b.fee_paise}+{b.gst_paise}+{b.net_paise}!={b.gross}"
            )
