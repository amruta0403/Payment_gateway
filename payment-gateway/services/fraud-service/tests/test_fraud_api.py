"""Integration tests for the fraud scoring API."""
from __future__ import annotations

import time
import uuid

import pytest

from tests.conftest import BASE_SCORING_PAYLOAD


# ── /score endpoint ───────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_score_allow_clean_transaction(client):
    resp = await client.post("/v1/score", json=BASE_SCORING_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] in ("ALLOW", "CHALLENGE", "BLOCK")
    assert 0.0 <= data["fraud_score"] <= 1.0
    assert "rule_hits" in data
    assert "evaluated_at" in data


@pytest.mark.anyio
async def test_score_response_under_200ms(client):
    """In test environment with mock Redis, scoring should be well under 200ms."""
    start = time.perf_counter()
    resp = await client.post("/v1/score", json=BASE_SCORING_PAYLOAD)
    elapsed = time.perf_counter() - start
    assert resp.status_code == 200
    # 200ms for test env (production target is 100ms p95)
    assert elapsed < 0.2, f"Scoring took {elapsed*1000:.1f}ms — too slow"


@pytest.mark.anyio
async def test_score_high_risk_mcc_raises_score(client):
    payload = {**BASE_SCORING_PAYLOAD, "merchant_mcc": "7995", "payment_id": str(uuid.uuid4())}
    resp = await client.post("/v1/score", json=payload)
    assert resp.status_code == 200
    # high-risk MCC adds 0.20; with blend this should move the score up
    assert resp.json()["fraud_score"] > 0.0


@pytest.mark.anyio
async def test_score_round_amount_in_rule_hits(client):
    payload = {**BASE_SCORING_PAYLOAD, "amount": 1_000_000, "payment_id": str(uuid.uuid4())}
    resp = await client.post("/v1/score", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    # score_round_amount should fire
    assert "score_round_amount" in data["rule_hits"]


@pytest.mark.anyio
async def test_score_missing_required_field(client):
    bad_payload = {k: v for k, v in BASE_SCORING_PAYLOAD.items() if k != "payment_id"}
    resp = await client.post("/v1/score", json=bad_payload)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_score_new_merchant(client):
    from datetime import datetime, timedelta
    payload = {
        **BASE_SCORING_PAYLOAD,
        "payment_id": str(uuid.uuid4()),
        "merchant_created_at": (datetime.utcnow() - timedelta(days=2)).isoformat(),
    }
    resp = await client.post("/v1/score", json=payload)
    assert resp.status_code == 200
    assert "score_new_merchant" in resp.json()["rule_hits"]


# ── /admin/blacklist endpoints ────────────────────────────────────────────────

@pytest.mark.anyio
async def test_add_to_blacklist(client):
    resp = await client.post(
        "/v1/admin/blacklist/ip",
        json={"value": "10.0.0.1"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "added"


@pytest.mark.anyio
async def test_remove_from_blacklist(client):
    await client.post("/v1/admin/blacklist/ip", json={"value": "10.0.0.2"})
    resp = await client.delete("/v1/admin/blacklist/ip/10.0.0.2")
    assert resp.status_code == 200
    assert resp.json()["status"] == "removed"


@pytest.mark.anyio
async def test_blacklist_invalid_list_type(client):
    resp = await client.post(
        "/v1/admin/blacklist/phone",
        json={"value": "9999999999"},
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_add_card_blacklist(client):
    resp = await client.post(
        "/v1/admin/blacklist/card",
        json={"value": "fp_deadbeef1234"},
    )
    assert resp.status_code == 201


# ── /admin/rules endpoints ────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_list_rules_empty(client):
    resp = await client.get("/v1/admin/rules")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.anyio
async def test_toggle_nonexistent_rule(client):
    resp = await client.post("/v1/admin/rules/nonexistent_rule/toggle")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_score_multiple_rules_blend(client):
    """Blended score = 0.6*rules + 0.4*ml — should be stable float."""
    from datetime import datetime, timedelta
    payload = {
        **BASE_SCORING_PAYLOAD,
        "payment_id": str(uuid.uuid4()),
        "amount": 500_000,            # round amount (+0.10)
        "merchant_mcc": "7995",        # high risk (+0.20)
        "merchant_created_at": (datetime.utcnow() - timedelta(days=3)).isoformat(),
    }
    resp = await client.post("/v1/score", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    # Rules score is at least 0.45 → blended > 0
    assert data["fraud_score"] > 0.1
    assert data["decision"] in ("CHALLENGE", "BLOCK")
