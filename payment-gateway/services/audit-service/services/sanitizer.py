"""
sanitise_for_audit — strips PII and secrets before writing to append-only audit log.
Max recursion depth: 3. Returns a new dict; never mutates the input.
"""
from __future__ import annotations

import re
from typing import Any

# Keys whose values are always redacted (case-insensitive substring match)
_SENSITIVE_KEYS = frozenset({
    "pan", "cvv", "card_number", "card_cvv", "password", "passwd",
    "secret", "key", "token", "otp", "pin", "ssn", "aadhar",
    "account_number", "ifsc", "swift", "routing_number",
    "private_key", "access_token", "refresh_token", "api_key",
    "authorization", "x-service-token",
})

# Patterns that look like card numbers (13–19 consecutive digits)
_CARD_RE = re.compile(r"\b\d{13,19}\b")
# Patterns that look like IBAN / account numbers
_ACCT_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7,15}\b")
_MAX_DEPTH = 3


def _is_sensitive_key(key: str) -> bool:
    key_lower = key.lower()
    return any(s in key_lower for s in _SENSITIVE_KEYS)


def _redact_string(value: str) -> str:
    value = _CARD_RE.sub("[REDACTED_CARD]", value)
    value = _ACCT_RE.sub("[REDACTED_ACCT]", value)
    return value


def sanitise_for_audit(data: Any, depth: int = 0) -> Any:
    """
    Recursively sanitise a dict/list for audit storage.
    - Sensitive keys → "[REDACTED]"
    - String values containing card-like patterns → "[REDACTED_CARD]"
    - Depth > 3 → "[DEPTH_LIMIT]"
    """
    if depth > _MAX_DEPTH:
        return "[DEPTH_LIMIT]"

    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for k, v in data.items():
            if _is_sensitive_key(str(k)):
                result[k] = "[REDACTED]"
            elif isinstance(v, str):
                result[k] = _redact_string(v)
            elif isinstance(v, (dict, list)):
                result[k] = sanitise_for_audit(v, depth + 1)
            else:
                result[k] = v
        return result

    if isinstance(data, list):
        return [sanitise_for_audit(item, depth + 1) for item in data]

    if isinstance(data, str):
        return _redact_string(data)

    return data
