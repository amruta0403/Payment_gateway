from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import uuid
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.merchant_webhook import MerchantWebhook, WebhookDelivery
from schemas.merchant import WebhookCreateRequest, WebhookCreateResponse, WebhookListItem
from shared.exceptions.handlers import PaymentGatewayError

log = structlog.get_logger()


async def create_webhook(
    merchant_id: uuid.UUID,
    request: WebhookCreateRequest,
    db: AsyncSession,
) -> WebhookCreateResponse:
    secret = secrets.token_hex(32)
    secret_hash = hashlib.sha256(secret.encode()).hexdigest()

    webhook = MerchantWebhook(
        merchant_id=merchant_id,
        url=str(request.url),
        events=request.events,
        secret_hash=secret_hash,
        is_active=True,
    )
    db.add(webhook)
    await db.commit()

    log.info("webhook.created", merchant_id=str(merchant_id), url=str(request.url))

    return WebhookCreateResponse(
        id=webhook.id,
        url=str(request.url),
        events=request.events,
        webhook_secret=secret,  # shown ONCE
        is_active=True,
        created_at=webhook.created_at,
    )


async def list_webhooks(
    merchant_id: uuid.UUID,
    db: AsyncSession,
) -> list[WebhookListItem]:
    rows = (
        await db.execute(
            select(MerchantWebhook).where(
                MerchantWebhook.merchant_id == merchant_id,
                MerchantWebhook.is_deleted.is_(False),
            ).order_by(MerchantWebhook.created_at.desc())
        )
    ).scalars().all()

    return [
        WebhookListItem(
            id=r.id,
            url=r.url,
            events=r.events,
            is_active=r.is_active,
            last_triggered_at=r.last_triggered_at,
            failure_count=r.failure_count,
            created_at=r.created_at,
        )
        for r in rows
    ]


async def delete_webhook(
    webhook_id: uuid.UUID,
    merchant_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    result = await db.execute(
        update(MerchantWebhook)
        .where(
            MerchantWebhook.id == webhook_id,
            MerchantWebhook.merchant_id == merchant_id,
        )
        .values(is_active=False, is_deleted=True)
        .returning(MerchantWebhook.id)
    )
    if not result.fetchone():
        raise PaymentGatewayError("Webhook not found")
    await db.commit()


async def send_test_webhook(
    webhook_id: uuid.UUID,
    merchant_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    webhook = (
        await db.execute(
            select(MerchantWebhook).where(
                MerchantWebhook.id == webhook_id,
                MerchantWebhook.merchant_id == merchant_id,
                MerchantWebhook.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()

    if not webhook:
        raise PaymentGatewayError("Webhook not found")

    payload = {
        "event": "test",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data": {
            "message": "This is a test webhook delivery from Payment Gateway",
            "merchant_id": str(merchant_id),
        },
    }

    body_bytes = json.dumps(payload).encode()
    timestamp = str(int(time.time()))

    # HMAC-SHA256 signature: HMAC(secret_hash, "timestamp.body")
    # Note: In practice we'd use the real secret, not its hash.
    # secret_hash is stored — we sign with it as the key.
    sig = hmac.new(
        webhook.secret_hash.encode(),
        f"{timestamp}.{body_bytes.decode()}".encode(),
        hashlib.sha256,
    ).hexdigest()

    start = time.monotonic()
    success = False
    response_status = None
    response_body = None
    error_message = None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                webhook.url,
                content=body_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": f"t={timestamp},v1={sig}",
                    "X-Webhook-Event": "test",
                },
            )
            response_status = resp.status_code
            response_body = resp.text[:500]
            success = 200 <= resp.status_code < 300
    except Exception as exc:
        error_message = str(exc)
        log.warning("webhook.delivery.failed", webhook_id=str(webhook_id), error=str(exc))

    duration_ms = int((time.monotonic() - start) * 1000)

    delivery = WebhookDelivery(
        webhook_id=webhook_id,
        event_type="test",
        payload=payload,
        response_status=response_status,
        response_body=response_body,
        duration_ms=duration_ms,
        success=success,
        error_message=error_message,
    )
    db.add(delivery)

    if not success:
        await db.execute(
            update(MerchantWebhook)
            .where(MerchantWebhook.id == webhook_id)
            .values(failure_count=MerchantWebhook.failure_count + 1)
        )
    else:
        await db.execute(
            update(MerchantWebhook)
            .where(MerchantWebhook.id == webhook_id)
            .values(last_triggered_at=datetime.now(timezone.utc))
        )

    await db.commit()

    return {
        "status": "delivered" if success else "failed",
        "response_status": response_status,
        "duration_ms": duration_ms,
        "error": error_message,
    }
