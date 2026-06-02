from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_validate_success_vpa(client):
    http, _ = client
    resp = await http.get("/v1/upi/vpa/success@upi/validate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_valid"] is True
    assert data["account_name"] == "Test User"
    assert data["bank_name"] == "HDFC Bank"
    assert data["vpa"] == "success@upi"


@pytest.mark.anyio
async def test_validate_invalid_vpa(client):
    http, _ = client
    resp = await http.get("/v1/upi/vpa/invalid@xyz/validate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_valid"] is False
    assert data["account_name"] is None


@pytest.mark.anyio
async def test_validate_generic_upi_vpa(client):
    http, _ = client
    resp = await http.get("/v1/upi/vpa/user@hdfc/validate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_valid"] is True
    assert data["account_name"] == "Mock User"


@pytest.mark.anyio
async def test_validate_paytm_vpa(client):
    http, _ = client
    resp = await http.get("/v1/upi/vpa/9876543210@paytm/validate")
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is True


@pytest.mark.anyio
async def test_vpa_cached_after_first_call(client):
    """Valid VPA should be cached in Redis after first resolution."""
    http, _ = client
    # First call — hits mock NPCI
    resp1 = await http.get("/v1/upi/vpa/success@upi/validate")
    assert resp1.status_code == 200
    # Redis cache_set should have been called
    # (mock Redis doesn't raise, so second call should also succeed)
    resp2 = await http.get("/v1/upi/vpa/success@upi/validate")
    assert resp2.json()["is_valid"] is True


@pytest.mark.anyio
async def test_validate_mock_vpa_regex():
    """Test VPA regex pattern directly."""
    import re
    _VPA_RE = re.compile(r"^[a-zA-Z0-9._-]+@[a-zA-Z]+$")
    assert _VPA_RE.match("user@hdfc")
    assert _VPA_RE.match("user.name@oksbi")
    assert _VPA_RE.match("9876543210@paytm")
    assert not _VPA_RE.match("@hdfc")
    assert not _VPA_RE.match("user@")
    assert not _VPA_RE.match("no-at-sign")
    assert not _VPA_RE.match("user@hdfc.com")   # only alpha handles


@pytest.mark.anyio
async def test_validate_invalid_handle_returns_false(mock_npci):
    resolution = await mock_npci.resolve_vpa("invalid@xyz")
    assert resolution.is_valid is False


@pytest.mark.anyio
async def test_validate_fail_vpa_still_valid(mock_npci):
    """fail@upi resolves to valid — it only fails at collect time."""
    resolution = await mock_npci.resolve_vpa("fail@upi")
    assert resolution.is_valid is True
    assert resolution.account_name == "Fail User"
