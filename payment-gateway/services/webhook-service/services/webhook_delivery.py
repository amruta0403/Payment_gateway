from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.webhook import WebhookDelivery, WebhookDeliveryStatus, WebhookEndpoint

log = structlog.get_logger()

_MAX_ATTEMPTS = 5
_BACKOFF_DELAYS = [10, 30, 120, 600, 1800]   # seconds: 10s, 30s, 2min, 10min, 30min


def _sign_payload(secret_hash: str, payload_bytes: bytes, timestamp: str) -> str:
    """HMAC-SHA256 signature: HMAC(secret_hash, f'{timestamp}.{payload}')"""
    msg = f"{timestamp}.{payload_bytes.decode()}".encode()
    return hmac.new(secret_hash.encode(), msg, hashlib.sha256).hexdigest()


async def deliver_now(delivery: WebhookDelivery, endpoint: WebhookEndpoint, db: AsyncSession) -> bool:
    """Attempt a single delivery. Returns True on success."""
    payload_bytes = json.dumps(delivery.payload).encode()
    timestamp = str(int(time.time()))
    sig = _sign_payload(endpoint.secret_hash, payload_bytes, timestamp)

    start = time.perf_counter()
    success = False
    response_status = None
    response_body = None
    error_msg = None

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                endpoint.url,
                content=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": f"t={timestamp},v1={sig}",
                    "X-Webhook-Event": delivery.event_type,
                    "X-Webhook-Delivery": str(delivery.id),
                    "User-Agent": "PaymentGateway-Webhooks/1.0",
                },
            )
            response_status = resp.status_code
            response_body = resp.text[:500]
            success = 200 <= resp.status_code < 300
    except httpx.TimeoutException:
        error_msg = "Request timed out"
    except httpx.ConnectError as exc:
        error_msg = f"Connection failed: {exc}"
    except Exception as exc:
        error_msg = str(exc)[:300]

    duration_ms = int((time.perf_counter() - start) * 1000)
    now = datetime.now(timezone.utc)
    attempt_no = delivery.attempt_count + 1

    if success:
        await db.execute(
            update(WebhookDelivery)
            .where(WebhookDelivery.id == delivery.id)
            .values(
                status=WebhookDeliveryStatus.SUCCESS,
                response_status=response_status,
                response_body=response_body,
                duration_ms=duration_ms,
                attempt_count=attempt_no,
                delivered_at=now,
            )
        )
        await db.execute(
            update(WebhookEndpoint)
            .where(WebhookEndpoint.id == endpoint.id)
            .values(last_success_at=now, failure_count=0)
        )
        log.info("webhook.delivered", delivery_id=str(delivery.id), url=endpoint.url[:40])
    else:
        if attempt_no >= _MAX_ATTEMPTS:
            new_status = WebhookDeliveryStatus.ABANDONED
            next_at = None
        else:
            new_status = WebhookDeliveryStatus.RETRYING
            delay = _BACKOFF_DELAYS[min(attempt_no - 1, len(_BACKOFF_DELAYS) - 1)]
            next_at = now + timedelta(seconds=delay)

        await db.execute(
            update(WebhookDelivery)
            .where(WebhookDelivery.id == delivery.id)
            .values(
                status=new_status,
                response_status=response_status,
                response_body=response_body,
                duration_ms=duration_ms,
                attempt_count=attempt_no,
                next_attempt_at=next_at,
                error_message=error_msg,
            )
        )
        await db.execute(
            update(WebhookEndpoint)
            .where(WebhookEndpoint.id == endpoint.id)
            .values(
                last_failure_at=now,
                failure_count=WebhookEndpoint.failure_count + 1,
            )
        )
        log.warning(
            "webhook.failed",
            delivery_id=str(delivery.id),
            attempt=attempt_no,
            status=response_status,
            error=error_msg,
        )

    await db.commit()
    return success
