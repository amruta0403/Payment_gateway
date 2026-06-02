"""
Tests for fee_calculator — ALL results must be integers, never floats.
Verify the integer arithmetic invariant: gross == fee + gst + net.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from utils.fee_calculator import FeeBreakdown, calculate_fee

DEFAULT_FEE_CONFIG = {
    "card_mdr_percent": "2.0",
    "upi_flat_fee_paise": 0,
    "netbanking_flat_fee_paise": 1000,
    "gst_percent": "18",
}


def _check_invariants(b: FeeBreakdown) -> None:
    """All fields must be int; gross must equal components sum."""
    assert isinstance(b.gross, int)
    assert isinstance(b.fee_paise, int)
    assert isinstance(b.gst_paise, int)
    assert isinstance(b.net_paise, int)
    assert b.gross == b.fee_paise + b.gst_paise + b.net_paise
    assert b.net_paise >= 0


# ── CARD ──────────────────────────────────────────────────────────────────────

def test_card_typical():
    b = calculate_fee(10000, "CARD", DEFAULT_FEE_CONFIG)   # ₹100
    _check_invariants(b)
    assert b.gross == 10000
    # 2% MDR = 200, 18% GST on 200 = 36, net = 9764
    assert b.fee_paise == 200
    assert b.gst_paise == 36
    assert b.net_paise == 9764


def test_card_zero_mdr():
    cfg = {**DEFAULT_FEE_CONFIG, "card_mdr_percent": "0"}
    b = calculate_fee(50000, "CARD", cfg)
    _check_invariants(b)
    assert b.fee_paise == 0
    assert b.gst_paise == 0
    assert b.net_paise == 50000


def test_card_1_rupee():
    b = calculate_fee(100, "CARD", DEFAULT_FEE_CONFIG)   # ₹1
    _check_invariants(b)
    # 2% of 100 = 2, 18% of 2 = 0 (rounds down), net = 98
    assert b.fee_paise == 2
    assert b.net_paise == 98


def test_card_rounding_half_up():
    # 2.5% MDR, odd amount → needs ROUND_HALF_UP
    cfg = {**DEFAULT_FEE_CONFIG, "card_mdr_percent": "2.5"}
    b = calculate_fee(301, "CARD", cfg)   # 2.5% of 301 = 7.525 → rounds to 8
    _check_invariants(b)
    assert b.fee_paise == 8


def test_card_large_amount():
    b = calculate_fee(100_000_00, "CARD", DEFAULT_FEE_CONFIG)  # ₹1,00,000
    _check_invariants(b)
    assert b.fee_paise == 200_000
    assert b.gst_paise == 36_000
    assert b.net_paise == 9_764_000


def test_card_no_floats_in_result():
    b = calculate_fee(99999, "CARD", DEFAULT_FEE_CONFIG)
    for field in (b.gross, b.fee_paise, b.gst_paise, b.net_paise):
        assert type(field) is int, f"Expected int, got {type(field)} for {field}"


# ── UPI ───────────────────────────────────────────────────────────────────────

def test_upi_below_threshold_zero_fee():
    # RBI mandate: zero MDR for P2M ≤ ₹2,000 (200,000 paise)
    b = calculate_fee(200_000, "UPI", DEFAULT_FEE_CONFIG)
    _check_invariants(b)
    assert b.fee_paise == 0
    assert b.gst_paise == 0
    assert b.net_paise == 200_000


def test_upi_exactly_at_threshold():
    b = calculate_fee(200_000, "UPI", DEFAULT_FEE_CONFIG)
    _check_invariants(b)
    assert b.fee_paise == 0


def test_upi_above_threshold_flat_fee():
    cfg = {**DEFAULT_FEE_CONFIG, "upi_flat_fee_paise": 500}
    b = calculate_fee(200_001, "UPI", cfg)
    _check_invariants(b)
    assert b.fee_paise == 500
    assert b.gst_paise == 90   # 18% of 500


def test_upi_small_amount():
    b = calculate_fee(1, "UPI", DEFAULT_FEE_CONFIG)
    _check_invariants(b)
    assert b.fee_paise == 0
    assert b.net_paise == 1


# ── NETBANKING ────────────────────────────────────────────────────────────────

def test_netbanking_flat_fee():
    b = calculate_fee(50000, "NETBANKING", DEFAULT_FEE_CONFIG)
    _check_invariants(b)
    assert b.fee_paise == 1000
    assert b.gst_paise == 180   # 18% of 1000
    assert b.net_paise == 48820


def test_netbanking_custom_flat_fee():
    cfg = {**DEFAULT_FEE_CONFIG, "netbanking_flat_fee_paise": 2000}
    b = calculate_fee(50000, "NETBANKING", cfg)
    _check_invariants(b)
    assert b.fee_paise == 2000
    assert b.gst_paise == 360


# ── Invariant enforcement ─────────────────────────────────────────────────────

def test_invariant_sum_always_holds():
    """Exhaustively check 50 random amounts across all methods."""
    import random
    methods = ["CARD", "UPI", "NETBANKING"]
    for _ in range(50):
        amount = random.randint(1, 10_000_000)
        for method in methods:
            b = calculate_fee(amount, method, DEFAULT_FEE_CONFIG)
            _check_invariants(b)


def test_unknown_method_zero_fee():
    b = calculate_fee(10000, "CRYPTO", DEFAULT_FEE_CONFIG)
    _check_invariants(b)
    assert b.fee_paise == 0
    assert b.net_paise == 10000
