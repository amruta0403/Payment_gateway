from __future__ import annotations

import pytest
import pytest_asyncio


REGISTER_PAYLOAD = {
    "business_name": "Acme Payments Pvt Ltd",
    "business_type": "PRIVATE_LIMITED",
    "pan": "ABCDE1234F",
    "support_email": "hello@acme.in",
    "support_phone": "+919876543210",
    "business_category": "5411",
}


@pytest.mark.anyio
async def test_register_success(client):
    http, _ = client
    resp = await http.post("/v1/merchants/register", json=REGISTER_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert data["business_name"] == "Acme Payments Pvt Ltd"
    assert data["status"] == "DRAFT"
    assert "id" in data
    assert "fee_config" in data
    assert "onboarding_checklist" in data


@pytest.mark.anyio
async def test_register_invalid_pan(client):
    http, _ = client
    bad = {**REGISTER_PAYLOAD, "pan": "INVALID"}
    resp = await http.post("/v1/merchants/register", json=bad)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_register_invalid_phone(client):
    http, _ = client
    bad = {**REGISTER_PAYLOAD, "support_phone": "9876543210"}  # missing +91
    resp = await http.post("/v1/merchants/register", json=bad)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_register_invalid_gstin(client):
    http, _ = client
    bad = {**REGISTER_PAYLOAD, "gstin": "BADGSTIN"}
    resp = await http.post("/v1/merchants/register", json=bad)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_get_merchant(client, merchant):
    http, principal = client
    merchant_id, _ = merchant
    resp = await http.get(f"/v1/merchants/{merchant_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert str(data["id"]) == str(merchant_id)


@pytest.mark.anyio
async def test_get_merchant_not_found(client):
    import uuid
    http, _ = client
    resp = await http.get(f"/v1/merchants/{uuid.uuid4()}")
    assert resp.status_code in (403, 404)


@pytest.mark.anyio
async def test_update_merchant(client, merchant):
    http, principal = client
    merchant_id, _ = merchant
    resp = await http.put(
        f"/v1/merchants/{merchant_id}",
        json={"display_name": "Acme Pay", "website_url": "https://acmepay.in"},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Acme Pay"


@pytest.mark.anyio
async def test_get_checklist(client, merchant):
    http, _ = client
    merchant_id, _ = merchant
    resp = await http.get(f"/v1/merchants/{merchant_id}/checklist")
    assert resp.status_code == 200
    checklist = resp.json()
    assert "pan_verified" in checklist
    assert "bank_account_added" in checklist


@pytest.mark.anyio
async def test_access_denied_wrong_merchant(client, merchant):
    http, principal = client
    import uuid
    other_id = uuid.uuid4()
    resp = await http.get(f"/v1/merchants/{other_id}")
    assert resp.status_code == 403
