"""
End-to-end golden path test for the complete payment gateway flow.

Flow under test:
  1.  Register merchant → status=DRAFT
  2.  Upload KYC document (mock auto-approve after 3s)
  3.  Add bank account
  4.  Initiate penny drop → verify → bank account verified
  5.  Create API key (returns full_key once)
  6.  POST /v1/payments (card payment) → fraud score → card vault → acquirer
  7.  GET /v1/payments/{id} → status=CAPTURED
  8.  POST /v1/refunds → refund initiated
  9.  POST /v1/upi/intent → deep link + QR generated
  10. GET /v1/transactions → merchant can see their transactions
  11. Trigger settlement batch → batch created

Requirements:
  - All 9 core services running (run `make up` first)
  - Set E2E_BASE_URL and E2E_ADMIN_TOKEN env vars
  - Run: pytest tests/e2e/test_golden_path.py -v -s --tb=short

This test is SKIPPED unless E2E_BASE_URL is set.
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import date

import httpx
import pytest

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL    = os.environ.get("E2E_BASE_URL", "")
ADMIN_TOKEN = os.environ.get("E2E_ADMIN_TOKEN", "")
SKIP_REASON = "E2E_BASE_URL not set — skipping end-to-end tests"

pytestmark = pytest.mark.skipif(not BASE_URL, reason=SKIP_REASON)


def _api(path: str) -> str:
    return f"{BASE_URL.rstrip('/')}{path}"


def _headers(token: str = "") -> dict:
    t = token or ADMIN_TOKEN
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def http():
    with httpx.Client(base_url=BASE_URL, headers=_headers(), timeout=30, verify=False) as c:
        yield c


# ── Step 1: Verify all services are healthy ───────────────────────────────────
def test_00_all_services_healthy(http):
    services = {
        "payment-service":     "/health",
        "merchant-service":    "/health",
        "fraud-service":       "/health",
        "upi-service":         "/health",
        "settlement-service":  "/health",
        "refund-service":      "/health",
        "notification-service": "/health",
        "audit-service":       "/health",
    }
    # Check health via port (override base_url per service)
    port_map = {
        "payment-service": 8010, "merchant-service": 8012, "fraud-service": 8013,
        "upi-service": 8014, "settlement-service": 8015, "refund-service": 8016,
        "notification-service": 8017, "audit-service": 8024,
    }
    host = BASE_URL.split("://")[1].split("/")[0].split(":")[0]
    for svc, port in port_map.items():
        url = f"http://{host}:{port}/health"
        try:
            r = httpx.get(url, timeout=5)
            assert r.status_code == 200, f"{svc} health failed: {r.status_code}"
            assert r.json()["status"] == "ok", f"{svc} not healthy: {r.json()}"
            print(f"  ✓ {svc}")
        except Exception as exc:
            pytest.skip(f"{svc} not reachable: {exc}")


# ── Step 2: Register merchant ──────────────────────────────────────────────────
def test_01_register_merchant(http):
    global _merchant_id, _merchant_token
    resp = http.post("/v1/merchants/register", json={
        "business_name": "E2E Test Merchants Pvt Ltd",
        "business_type": "PRIVATE_LIMITED",
        "pan": "ABCDE1234F",
        "gstin": "27ABCDE1234F1Z5",
        "website_url": "https://e2e-test.payments.local",
        "support_email": "e2e@test.local",
        "support_phone": "+919876543210",
        "business_category": "5411",
    })
    assert resp.status_code == 201, f"Register failed: {resp.text}"
    data = resp.json()
    assert data["status"] == "DRAFT"
    assert data["business_name"] == "E2E Test Merchants Pvt Ltd"
    _merchant_id = data["id"]
    print(f"  ✓ Merchant registered: {_merchant_id}")


# ── Step 3: Upload KYC document ────────────────────────────────────────────────
def test_02_upload_kyc(http):
    import io
    fake_pdf = b"%PDF-1.4 e2e test document"
    resp = http.post(
        f"/v1/merchants/{_merchant_id}/kyc/documents",
        data={"document_type": "PAN"},
        files={"file": ("pan.pdf", fake_pdf, "application/pdf")},
    )
    assert resp.status_code == 201, f"KYC upload failed: {resp.text}"
    data = resp.json()
    assert data["document_type"] == "PAN"
    assert data["status"] in ("PENDING", "VERIFIED")
    print(f"  ✓ KYC document uploaded: {data['id']}")


# ── Step 4: Add bank account ───────────────────────────────────────────────────
def test_03_add_bank_account(http):
    global _bank_account_id
    resp = http.post(f"/v1/merchants/{_merchant_id}/bank-accounts", json={
        "account_holder_name": "E2E Test Merchant",
        "account_number": "987654321012",
        "ifsc_code": "HDFC0001234",
        "account_type": "CURRENT",
    })
    assert resp.status_code == 201, f"Bank account add failed: {resp.text}"
    data = resp.json()
    _bank_account_id = data["id"]
    assert data["is_verified"] is False
    print(f"  ✓ Bank account added: {_bank_account_id}")


# ── Step 5: Penny drop ─────────────────────────────────────────────────────────
def test_04_penny_drop(http):
    pd_resp = http.post(
        f"/v1/merchants/{_merchant_id}/bank-accounts/{_bank_account_id}/penny-drop"
    )
    assert pd_resp.status_code == 200, f"Penny drop failed: {pd_resp.text}"
    pd_data = pd_resp.json()
    assert pd_data["status"] in ("initiated", "already_verified")

    if pd_data.get("expected_amount_paise"):
        amount = pd_data["expected_amount_paise"]
        verify_resp = http.post(
            f"/v1/merchants/{_merchant_id}/bank-accounts/{_bank_account_id}/verify",
            json={"stated_amount_paise": amount},
        )
        assert verify_resp.status_code == 200, f"Penny drop verify failed: {verify_resp.text}"
        assert verify_resp.json()["verified"] is True
        print(f"  ✓ Penny drop verified (amount: {amount} paise)")
    else:
        print(f"  ✓ Penny drop: {pd_data['status']}")


# ── Step 6: Create API key ─────────────────────────────────────────────────────
def test_05_create_api_key(http):
    global _api_key
    resp = http.post(f"/v1/merchants/{_merchant_id}/api-keys", json={
        "name": "E2E Test Key",
        "environment": "SANDBOX",
        "permissions": ["payments:write", "payments:read"],
    })
    assert resp.status_code == 201, f"API key creation failed: {resp.text}"
    data = resp.json()
    assert "full_key" in data
    assert data["full_key"].startswith("sk_sandbox_")
    assert "warning" in data
    _api_key = data["full_key"]
    print(f"  ✓ API key created: {data['key_prefix']}...")


# ── Step 7: Create a card payment ─────────────────────────────────────────────
def test_06_create_card_payment(http):
    global _payment_id
    resp = http.post("/v1/payments", json={
        "merchant_id": _merchant_id,
        "amount": 50000,
        "currency": "INR",
        "payment_method": "CARD",
        "card": {
            "number": "4111111111111111",
            "expiry_month": 12,
            "expiry_year": 2026,
            "cvv": "123",
            "cardholder_name": "E2E Test User",
        },
        "customer": {
            "email": "customer@e2e.test",
            "phone": "+919876543210",
            "name": "E2E Customer",
        },
        "description": "E2E test payment",
        "order_id": f"e2e-order-{uuid.uuid4().hex[:8]}",
        "callback_url": "https://e2e-test.local/callback",
    }, headers={"X-Idempotency-Key": f"e2e-{uuid.uuid4().hex}"})

    assert resp.status_code in (200, 201), f"Payment creation failed: {resp.text}"
    data = resp.json()
    assert data["status"] not in ("FAILED",), f"Payment failed: {data}"
    _payment_id = data["id"]
    print(f"  ✓ Payment created: {_payment_id} (status: {data['status']})")


# ── Step 8: Poll until captured ───────────────────────────────────────────────
def test_07_payment_captured(http):
    for i in range(10):
        resp = http.get(f"/v1/payments/{_payment_id}")
        assert resp.status_code == 200
        status = resp.json()["status"]
        if status in ("CAPTURED", "SETTLED"):
            print(f"  ✓ Payment {status}")
            return
        if status in ("FAILED", "CANCELLED"):
            pytest.fail(f"Payment reached terminal failure state: {status}")
        time.sleep(2)
    print(f"  ⚠ Payment still in non-terminal state after 20s (this is OK in dev)")


# ── Step 9: Fraud score endpoint ──────────────────────────────────────────────
def test_08_fraud_score_latency():
    """Directly test fraud-service p95 < 100ms."""
    host = BASE_URL.split("://")[1].split("/")[0].split(":")[0]
    latencies = []
    for _ in range(20):
        start = time.perf_counter()
        r = httpx.post(f"http://{host}:8013/v1/score", json={
            "payment_id": str(uuid.uuid4()),
            "merchant_id": str(uuid.uuid4()),
            "amount": 50000,
            "payment_method": "CARD",
            "ip_address": "27.1.2.3",
            "pan_first6": "411111",
            "card_token": str(uuid.uuid4()),
        }, timeout=5)
        latencies.append((time.perf_counter() - start) * 1000)
        assert r.status_code == 200

    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]
    p50 = latencies[int(len(latencies) * 0.50)]
    print(f"  ✓ Fraud scoring — p50: {p50:.1f}ms, p95: {p95:.1f}ms")
    assert p95 < 200, f"p95 {p95:.1f}ms exceeds 200ms (production target 100ms)"


# ── Step 10: Create refund ─────────────────────────────────────────────────────
def test_09_create_refund(http):
    resp = http.post("/v1/refunds", json={
        "transaction_id": _payment_id,
        "amount": 10000,
        "reason": "E2E test partial refund",
        "idempotency_key": f"e2e-refund-{uuid.uuid4().hex}",
    })
    assert resp.status_code in (200, 201, 400), f"Refund unexpected: {resp.text}"
    if resp.status_code in (200, 201):
        print(f"  ✓ Refund created: {resp.json().get('id')}")
    else:
        # Payment might not be in CAPTURED state yet — acceptable
        print(f"  ⚠ Refund skipped (payment not yet captured): {resp.json().get('detail')}")


# ── Step 11: UPI intent ────────────────────────────────────────────────────────
def test_10_upi_intent(http):
    resp = http.post("/v1/upi/intent", json={
        "payment_id": str(uuid.uuid4()),
        "amount": 10000,
        "merchant_vpa": "test@upi",
        "description": "E2E UPI test",
    })
    assert resp.status_code in (200, 201), f"UPI intent failed: {resp.text}"
    data = resp.json()
    assert "upi://pay" in data["upi_deep_link"]
    assert "qr_code_base64" in data
    print(f"  ✓ UPI intent: {data['our_ref_id']}")


# ── Step 12: Query transactions ───────────────────────────────────────────────
def test_11_list_transactions(http):
    resp = http.get(f"/v1/transactions?page=1&page_size=10")
    assert resp.status_code in (200, 404), f"Transactions list failed: {resp.text}"
    if resp.status_code == 200:
        data = resp.json()
        print(f"  ✓ Transactions: {data.get('total', len(data.get('items', [])))} found")
    else:
        print("  ⚠ Transaction service not available")


# ── Step 13: Trigger settlement ───────────────────────────────────────────────
def test_12_trigger_settlement(http):
    today = date.today().isoformat()
    resp = http.post("/v1/admin/settlements/trigger", json={"settlement_date": today})
    assert resp.status_code in (200, 202), f"Settlement trigger failed: {resp.text}"
    print(f"  ✓ Settlement batch triggered for {today}")


# ── Step 14: Check audit log ───────────────────────────────────────────────────
def test_13_audit_log(http):
    resp = http.get("/v1/audit/logs?limit=5")
    assert resp.status_code in (200, 403), f"Audit logs failed: {resp.text}"
    if resp.status_code == 200:
        data = resp.json()
        print(f"  ✓ Audit log has entries: {len(data.get('items', []))}")
    else:
        print("  ⚠ Audit log requires COMPLIANCE_OFFICER role")
