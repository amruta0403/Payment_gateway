"""Generic proxy routes — forward requests to microservices with the user's JWT."""
from __future__ import annotations

from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from client import proxy_delete, proxy_get, proxy_post
from config import settings

log = structlog.get_logger()
router = APIRouter(prefix="/api", tags=["proxy"])


def _tok(auth: str) -> str:
    return auth.replace("Bearer ", "")


# ── Transactions ──────────────────────────────────────────────────────────────

@router.get("/transactions")
async def list_transactions(
    page: int = Query(1), page_size: int = Query(20),
    status: str | None = None, payment_method: str | None = None,
    start_date: str | None = None, end_date: str | None = None,
    order_id: str | None = None,
    authorization: str = Header(...),
):
    params = {"page": page, "page_size": page_size}
    if status:         params["status"] = status
    if payment_method: params["payment_method"] = payment_method
    if start_date:     params["start_date"] = start_date
    if end_date:       params["end_date"] = end_date
    if order_id:       params["order_id"] = order_id
    return await proxy_get(settings.TRANSACTION_SERVICE_URL, "/v1/transactions", _tok(authorization), params)


@router.get("/transactions/{txn_id}")
async def get_transaction(txn_id: str, authorization: str = Header(...)):
    return await proxy_get(settings.TRANSACTION_SERVICE_URL, f"/v1/transactions/{txn_id}", _tok(authorization))


# ── Payments ──────────────────────────────────────────────────────────────────

@router.get("/payments")
async def list_payments(
    page: int = Query(1), page_size: int = Query(20),
    status: str | None = None,
    authorization: str = Header(...),
):
    params = {"page": page, "page_size": page_size}
    if status: params["status"] = status
    return await proxy_get(settings.PAYMENT_SERVICE_URL, "/v1/payments", _tok(authorization), params)


@router.get("/payments/{payment_id}")
async def get_payment(payment_id: str, authorization: str = Header(...)):
    return await proxy_get(settings.PAYMENT_SERVICE_URL, f"/v1/payments/{payment_id}", _tok(authorization))


@router.post("/payments")
async def create_payment(request: Request, authorization: str = Header(...)):
    body = await request.json()
    return await proxy_post(settings.PAYMENT_SERVICE_URL, "/v1/payments", _tok(authorization), body)


@router.get("/payments/{payment_id}/events")
async def get_payment_events(payment_id: str, authorization: str = Header(...)):
    return await proxy_get(settings.PAYMENT_SERVICE_URL, f"/v1/payments/{payment_id}/events", _tok(authorization))


# ── Refunds ───────────────────────────────────────────────────────────────────

@router.get("/refunds")
async def list_refunds(
    page: int = Query(1), page_size: int = Query(20),
    authorization: str = Header(...),
):
    return await proxy_get(settings.REFUND_SERVICE_URL, "/v1/refunds", _tok(authorization), {"page": page, "page_size": page_size})


@router.post("/refunds")
async def create_refund(request: Request, authorization: str = Header(...)):
    body = await request.json()
    return await proxy_post(settings.REFUND_SERVICE_URL, "/v1/refunds", _tok(authorization), body)


@router.get("/payments/{payment_id}/refunds")
async def get_payment_refunds(payment_id: str, authorization: str = Header(...)):
    return await proxy_get(settings.REFUND_SERVICE_URL, f"/v1/payments/{payment_id}/refunds", _tok(authorization))


# ── Settlements ───────────────────────────────────────────────────────────────

@router.get("/settlements")
async def list_settlements(
    page: int = Query(1), page_size: int = Query(20),
    status: str | None = None, start_date: str | None = None, end_date: str | None = None,
    authorization: str = Header(...),
):
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if status:     params["status"] = status
    if start_date: params["start_date"] = start_date
    if end_date:   params["end_date"] = end_date
    return await proxy_get(settings.SETTLEMENT_SERVICE_URL, "/v1/settlements", _tok(authorization), params)


@router.get("/settlements/{batch_id}")
async def get_settlement(batch_id: str, authorization: str = Header(...)):
    return await proxy_get(settings.SETTLEMENT_SERVICE_URL, f"/v1/settlements/{batch_id}", _tok(authorization))


# ── Merchant ──────────────────────────────────────────────────────────────────

@router.get("/merchants/me")
async def get_my_merchant(authorization: str = Header(...)):
    """Get the logged-in merchant's profile from the JWT merchant_id."""
    token_data = _parse_jwt_claims(_tok(authorization))
    merchant_id = token_data.get("merchant_id")
    if not merchant_id:
        raise HTTPException(400, "No merchant_id in token")
    return await proxy_get(settings.MERCHANT_SERVICE_URL, f"/v1/merchants/{merchant_id}", _tok(authorization))


@router.get("/merchants/{merchant_id}/checklist")
async def get_checklist(merchant_id: str, authorization: str = Header(...)):
    return await proxy_get(settings.MERCHANT_SERVICE_URL, f"/v1/merchants/{merchant_id}/checklist", _tok(authorization))


# ── API Keys ──────────────────────────────────────────────────────────────────

@router.get("/merchants/{merchant_id}/api-keys")
async def list_api_keys(merchant_id: str, authorization: str = Header(...)):
    return await proxy_get(settings.MERCHANT_SERVICE_URL, f"/v1/merchants/{merchant_id}/api-keys", _tok(authorization))


@router.post("/merchants/{merchant_id}/api-keys")
async def create_api_key(merchant_id: str, request: Request, authorization: str = Header(...)):
    body = await request.json()
    return await proxy_post(settings.MERCHANT_SERVICE_URL, f"/v1/merchants/{merchant_id}/api-keys", _tok(authorization), body)


@router.delete("/merchants/{merchant_id}/api-keys/{key_id}")
async def revoke_api_key(merchant_id: str, key_id: str, authorization: str = Header(...)):
    status_code = await proxy_delete(settings.MERCHANT_SERVICE_URL, f"/v1/merchants/{merchant_id}/api-keys/{key_id}", _tok(authorization))
    return {"deleted": status_code == 204}


# ── Webhooks ──────────────────────────────────────────────────────────────────

@router.get("/merchants/{merchant_id}/webhooks")
async def list_webhooks(merchant_id: str, authorization: str = Header(...)):
    return await proxy_get(settings.MERCHANT_SERVICE_URL, f"/v1/merchants/{merchant_id}/webhooks", _tok(authorization))


@router.post("/merchants/{merchant_id}/webhooks")
async def create_webhook(merchant_id: str, request: Request, authorization: str = Header(...)):
    body = await request.json()
    return await proxy_post(settings.MERCHANT_SERVICE_URL, f"/v1/merchants/{merchant_id}/webhooks", _tok(authorization), body)


@router.delete("/merchants/{merchant_id}/webhooks/{webhook_id}")
async def delete_webhook(merchant_id: str, webhook_id: str, authorization: str = Header(...)):
    status_code = await proxy_delete(settings.MERCHANT_SERVICE_URL, f"/v1/merchants/{merchant_id}/webhooks/{webhook_id}", _tok(authorization))
    return {"deleted": status_code == 204}


@router.post("/merchants/{merchant_id}/webhooks/{webhook_id}/test")
async def test_webhook(merchant_id: str, webhook_id: str, authorization: str = Header(...)):
    return await proxy_post(settings.MERCHANT_SERVICE_URL, f"/v1/merchants/{merchant_id}/webhooks/{webhook_id}/test", _tok(authorization))


# ── Bank accounts ─────────────────────────────────────────────────────────────

@router.get("/merchants/{merchant_id}/bank-accounts")
async def list_bank_accounts(merchant_id: str, authorization: str = Header(...)):
    return await proxy_get(settings.MERCHANT_SERVICE_URL, f"/v1/merchants/{merchant_id}/bank-accounts", _tok(authorization))


@router.post("/merchants/{merchant_id}/bank-accounts")
async def add_bank_account(merchant_id: str, request: Request, authorization: str = Header(...)):
    body = await request.json()
    return await proxy_post(settings.MERCHANT_SERVICE_URL, f"/v1/merchants/{merchant_id}/bank-accounts", _tok(authorization), body)


# ── Reports ───────────────────────────────────────────────────────────────────

@router.get("/reports/daily")
async def daily_report(
    start_date: str, end_date: str,
    authorization: str = Header(...),
):
    return await proxy_get(settings.REPORTING_SERVICE_URL, "/v1/reports/daily", _tok(authorization),
                           {"start_date": start_date, "end_date": end_date})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_jwt_claims(token: str) -> dict:
    try:
        import base64, json
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        padding = 4 - len(parts[1]) % 4
        decoded = base64.urlsafe_b64decode(parts[1] + "=" * padding)
        return json.loads(decoded)
    except Exception:
        return {}
