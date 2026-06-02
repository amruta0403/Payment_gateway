"""Tests for audit PII sanitizer."""
from __future__ import annotations

import pytest
from services.sanitizer import sanitise_for_audit


def test_pan_key_is_redacted():
    data = {"pan": "4111111111111111", "amount": 1000}
    result = sanitise_for_audit(data)
    assert result["pan"] == "[REDACTED]"
    assert result["amount"] == 1000


def test_cvv_is_redacted():
    assert sanitise_for_audit({"cvv": "123"})["cvv"] == "[REDACTED]"


def test_password_is_redacted():
    assert sanitise_for_audit({"password": "secret123"})["password"] == "[REDACTED]"


def test_token_is_redacted():
    assert sanitise_for_audit({"access_token": "eyJhbGci..."})["access_token"] == "[REDACTED]"


def test_api_key_is_redacted():
    assert sanitise_for_audit({"api_key": "sk_live_abc123"})["api_key"] == "[REDACTED]"


def test_card_number_string_is_redacted():
    data = {"description": "Card 4111111111111111 used"}
    result = sanitise_for_audit(data)
    assert "4111111111111111" not in result["description"]
    assert "[REDACTED_CARD]" in result["description"]


def test_safe_fields_pass_through():
    data = {"transaction_id": "txn_abc", "amount": 5000, "status": "CAPTURED"}
    result = sanitise_for_audit(data)
    assert result == data


def test_nested_dict_is_sanitised():
    data = {
        "payment": {
            "card": {"pan": "4111111111111111", "last4": "1111"},
            "amount": 1000,
        }
    }
    result = sanitise_for_audit(data)
    assert result["payment"]["card"]["pan"] == "[REDACTED]"
    assert result["payment"]["card"]["last4"] == "1111"
    assert result["payment"]["amount"] == 1000


def test_depth_limit_is_enforced():
    # 4 levels deep — depth 3 is the limit
    data = {"a": {"b": {"c": {"d": {"sensitive_key": "secret"}}}}}
    result = sanitise_for_audit(data)
    # At depth 3, the value is "[DEPTH_LIMIT]"
    assert result["a"]["b"]["c"] == "[DEPTH_LIMIT]"


def test_list_items_are_sanitised():
    data = {"events": [{"pan": "4111111111111111"}, {"amount": 500}]}
    result = sanitise_for_audit(data)
    assert result["events"][0]["pan"] == "[REDACTED]"
    assert result["events"][1]["amount"] == 500


def test_empty_dict_returns_empty():
    assert sanitise_for_audit({}) == {}


def test_non_dict_returns_as_is():
    assert sanitise_for_audit(42) == 42
    assert sanitise_for_audit(None) is None
    assert sanitise_for_audit([1, 2, 3]) == [1, 2, 3]


def test_card_number_exact_match():
    """13 to 19 digit numbers in strings should be redacted."""
    assert "[REDACTED_CARD]" in sanitise_for_audit({"x": "5500000000000004"})["x"]


def test_short_numbers_not_redacted():
    """Phone numbers and amounts (< 13 digits) should NOT be redacted."""
    data = {"phone": "9876543210", "amount": 10000}
    result = sanitise_for_audit(data)
    assert result["phone"] == "9876543210"
    assert result["amount"] == 10000


def test_multiple_sensitive_keys_all_redacted():
    data = {
        "pan": "val1",
        "cvv": "val2",
        "password": "val3",
        "secret": "val4",
        "otp": "val5",
    }
    result = sanitise_for_audit(data)
    for k in data:
        assert result[k] == "[REDACTED]", f"Key {k} was not redacted"
