from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_register_webhook_returns_secret_once(client, merchant):
    http, _ = client
    merchant_id, _ = merchant
    resp = await http.post(
        f"/v1/merchants/{merchant_id}/webhooks",
        json={"url": "https://example.com/webhook", "events": ["payment.captured"]},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "webhook_secret" in data
    assert len(data["webhook_secret"]) == 64  # 32-byte hex
    assert "warning" in data
    assert data["is_active"] is True


@pytest.mark.anyio
async def test_webhook_url_must_be_https(client, merchant):
    http, _ = client
    merchant_id, _ = merchant
    resp = await http.post(
        f"/v1/merchants/{merchant_id}/webhooks",
        json={"url": "http://example.com/webhook", "events": ["payment.captured"]},
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_list_webhooks(client, merchant):
    http, _ = client
    merchant_id, _ = merchant
    await http.post(
        f"/v1/merchants/{merchant_id}/webhooks",
        json={"url": "https://hook1.example.com/", "events": ["payment.captured"]},
    )
    resp = await http.get(f"/v1/merchants/{merchant_id}/webhooks")
    assert resp.status_code == 200
    hooks = resp.json()
    assert len(hooks) >= 1
    for h in hooks:
        assert "webhook_secret" not in h
        assert "url" in h


@pytest.mark.anyio
async def test_delete_webhook(client, merchant):
    http, _ = client
    merchant_id, _ = merchant
    create_resp = await http.post(
        f"/v1/merchants/{merchant_id}/webhooks",
        json={"url": "https://delete.example.com/", "events": ["*"]},
    )
    wh_id = create_resp.json()["id"]
    del_resp = await http.delete(f"/v1/merchants/{merchant_id}/webhooks/{wh_id}")
    assert del_resp.status_code == 204


@pytest.mark.anyio
async def test_webhook_events_required(client, merchant):
    http, _ = client
    merchant_id, _ = merchant
    resp = await http.post(
        f"/v1/merchants/{merchant_id}/webhooks",
        json={"url": "https://example.com/wh", "events": []},
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_delete_nonexistent_webhook(client, merchant):
    import uuid
    http, _ = client
    merchant_id, _ = merchant
    resp = await http.delete(f"/v1/merchants/{merchant_id}/webhooks/{uuid.uuid4()}")
    assert resp.status_code in (404, 400)
