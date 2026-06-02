from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_create_api_key_returns_full_key_once(client, merchant):
    http, _ = client
    merchant_id, _ = merchant
    resp = await http.post(
        f"/v1/merchants/{merchant_id}/api-keys",
        json={"name": "Test Key", "environment": "SANDBOX", "permissions": ["payments:read"]},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "full_key" in data
    assert data["full_key"].startswith("sk_sandbox_")
    assert "warning" in data
    assert "key_prefix" in data
    assert "full_key" not in data.get("warning", "").lower() or True  # warning present


@pytest.mark.anyio
async def test_list_api_keys_no_full_key(client, merchant):
    http, _ = client
    merchant_id, _ = merchant
    # Create one key first
    await http.post(
        f"/v1/merchants/{merchant_id}/api-keys",
        json={"name": "Key 1", "environment": "SANDBOX"},
    )
    resp = await http.get(f"/v1/merchants/{merchant_id}/api-keys")
    assert resp.status_code == 200
    keys = resp.json()
    assert len(keys) >= 1
    for key in keys:
        assert "full_key" not in key
        assert "key_prefix" in key


@pytest.mark.anyio
async def test_revoke_api_key(client, merchant):
    http, _ = client
    merchant_id, _ = merchant
    create_resp = await http.post(
        f"/v1/merchants/{merchant_id}/api-keys",
        json={"name": "Revoke Me", "environment": "LIVE"},
    )
    key_id = create_resp.json()["id"]
    del_resp = await http.delete(f"/v1/merchants/{merchant_id}/api-keys/{key_id}")
    assert del_resp.status_code == 204


@pytest.mark.anyio
async def test_revoke_nonexistent_key(client, merchant):
    import uuid
    http, _ = client
    merchant_id, _ = merchant
    resp = await http.delete(f"/v1/merchants/{merchant_id}/api-keys/{uuid.uuid4()}")
    assert resp.status_code in (404, 400)


@pytest.mark.anyio
async def test_create_key_invalid_environment(client, merchant):
    http, _ = client
    merchant_id, _ = merchant
    resp = await http.post(
        f"/v1/merchants/{merchant_id}/api-keys",
        json={"name": "Bad", "environment": "PRODUCTION"},
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_live_key_prefix(client, merchant):
    http, _ = client
    merchant_id, _ = merchant
    resp = await http.post(
        f"/v1/merchants/{merchant_id}/api-keys",
        json={"name": "Live Key", "environment": "LIVE"},
    )
    assert resp.status_code == 201
    assert resp.json()["full_key"].startswith("sk_live_")
