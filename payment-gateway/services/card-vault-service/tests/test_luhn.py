from __future__ import annotations

import pytest

from utils.card_utils import luhn_check


# ── Valid cards (known-good PANs from test suites) ────────────────────────────

@pytest.mark.parametrize("pan", [
    "4111111111111111",   # Visa test card
    "4012888888881881",   # Visa
    "4222222222222",      # Visa (13-digit)
    "5500005555555559",   # Mastercard
    "5105105105105100",   # Mastercard
    "371449635398431",    # Amex
    "6011111111111117",   # Discover
    "3530111333300000",   # JCB
])
def test_luhn_valid(pan: str):
    assert luhn_check(pan) is True, f"Expected {pan} to pass Luhn"


# ── Invalid cards ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pan", [
    "4111111111111112",   # off by one in check digit
    "4000000000000000",
    "1234567890123456",
    "0000000000000000",
    "9999999999999999",
    "4111111111111113",
])
def test_luhn_invalid(pan: str):
    assert luhn_check(pan) is False, f"Expected {pan} to fail Luhn"


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_luhn_non_digit_returns_false():
    assert luhn_check("411111111111111X") is False


def test_luhn_empty_returns_false():
    assert luhn_check("") is False


def test_luhn_single_digit():
    # Single digit 0: sum=0, 0%10=0 → True (degenerate but mathematically correct)
    assert luhn_check("0") is True


def test_luhn_spaces_in_input_fail():
    # We expect raw digits — spaces not stripped here (caller should strip)
    assert luhn_check("4111 1111 1111 1111") is False
