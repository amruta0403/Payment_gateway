from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.refund import Refund, RefundStatus, RefundType
from schemas.refund import RefundCreateRequest, RefundResponse
from shared.exceptions.handlers import PaymentGatewayError
from shared.kafka.topics import Topics

log = structlog.get_logger()


class RefundValidationError(PaymentGatewayError):
    http_status = 400
    code = "REFUND_VALIDATION_ERROR"
    message = "Refund validation failed"


class RefundNotFoundError(PaymentGatewayError):
    http_status = 404
    code = "REFUND_NOT_FOUND"
    message = "Refund not found"


async def create_refund(
    request: RefundCreateRequest,
    merchant_id: uuid.UUID,
    initiated_by: uuid.UUID | None,
    db: AsyncSession,
    settings,
    kafka_producer=None,
) -> RefundResponse:
    # ── 1. Idempotency check ──────────────────────────────────────────────────
    existing = (
        await db.execute(
            select(Refund).where(Refund.idempotency_key == request.idempotency_key)
        )
    ).scalar_one_or_none()
    if existing:
        log.info("refund.idempotency_hit", key=request.idempotency_key)
        return _to_response(existing)

    # ── 2. Fetch original transaction from payment-service ────────────────────
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{settings.PAYMENT_SERVICE_URL}/v1/payments/{request.transaction_id}",
            headers={"X-Service-Token": settings.INTERNAL_SERVICE_TOKEN},
        )

    if resp.status_code == 404:
        raise RefundValidationError("Transaction not found")
    if resp.status_code != 200:
        raise RefundValidationError(f"Could not fetch transaction: HTTP {resp.status_code}")

    txn = resp.json()

    if str(txn.get("merchant_id")) != str(merchant_id):
        raise RefundValidationError("Transaction does not belong to this merchant")

    if txn.get("status") not in ("CAPTURED", "SETTLED", "PARTIALLY_REFUNDED"):
        raise RefundValidationError(
            f"Transaction status '{txn.get('status')}' is not refundable"
        )

    # ── 3. Validate amount ────────────────────────────────────────────────────
    refundable = txn.get("amount", 0) - txn.get("refunded_amount", 0)
    if request.amount > refundable:
        raise RefundValidationError(
            f"Refund amount {request.amount} exceeds refundable {refundable} paise"
        )

    # ── 4. Create refund record ───────────────────────────────────────────────
    refund_type = (
        RefundType.FULL if request.amount == txn.get("amount", 0)
        else RefundType.PARTIAL
    )
    refund = Refund(
        transaction_id=request.transaction_id,
        merchant_id=merchant_id,
        amount=request.amount,
        currency=txn.get("currency", "INR"),
        refund_type=refund_type,
        status=RefundStatus.INITIATED,
        reason=request.reason,
        notes=request.notes,
        initiated_by=initiated_by,
        idempotency_key=request.idempotency_key,
    )
    db.add(refund)
    await db.flush()

    # ── 5. Route to acquirer via payment-service internal endpoint ─────────────
    payment_method = txn.get("payment_method", "CARD").upper()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            if payment_method == "UPI":
                target = f"{settings.UPI_SERVICE_URL}/internal/refund"
            else:
                target = f"{settings.PAYMENT_SERVICE_URL}/internal/refund"

            r = await client.post(
                target,
                headers={"X-Service-Token": settings.INTERNAL_SERVICE_TOKEN},
                json={
                    "transaction_id": str(request.transaction_id),
                    "refund_id": str(refund.id),
                    "amount": request.amount,
                    "reason": request.reason or "",
                },
            )

        if r.status_code in (200, 201):
            data = r.json()
            refund.status = RefundStatus.PROCESSING
            refund.gateway_refund_id = data.get("gateway_refund_id")
            refund.utr_number = data.get("utr_number")
        elif settings.ENVIRONMENT == "development":
            # Dev: mock success
            refund.status = RefundStatus.SUCCESS
            refund.gateway_refund_id = f"mock_refund_{refund.id.hex[:8]}"
            refund.processed_at = datetime.now(timezone.utc)
        else:
            err = r.json().get("detail", "Acquirer refund failed")
            refund.status = RefundStatus.FAILED
            refund.error_message = str(err)[:500]

    except httpx.TimeoutException:
        if settings.ENVIRONMENT == "development":
            refund.status = RefundStatus.PROCESSING
        else:
            refund.status = RefundStatus.FAILED
            refund.error_message = "Acquirer timeout"

    await db.commit()
    await db.refresh(refund)
    log.info("refund.created", refund_id=str(refund.id), status=refund.status.value)

    # ── 7. Publish Kafka event ────────────────────────────────────────────────
    if kafka_producer:
        try:
            await kafka_producer.publish(
                Topics.REFUND_INITIATED,
                "refund.initiated",
                {
                    "refund_id": str(refund.id),
                    "transaction_id": str(request.transaction_id),
                    "merchant_id": str(merchant_id),
                    "amount": request.amount,
                    "status": refund.status.value,
                },
                key=str(refund.id),
            )
        except Exception as exc:
            log.warning("refund.kafka.failed", error=str(exc))

    return _to_response(refund)


async def get_refund(refund_id: uuid.UUID, merchant_id: uuid.UUID, db: AsyncSession) -> RefundResponse:
    refund = (
        await db.execute(
            select(Refund).where(
                Refund.id == refund_id,
                Refund.merchant_id == merchant_id,
                Refund.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if not refund:
        raise RefundNotFoundError()
    return _to_response(refund)


async def list_refunds_for_payment(
    transaction_id: uuid.UUID,
    merchant_id: uuid.UUID,
    db: AsyncSession,
) -> list[RefundResponse]:
    rows = (
        await db.execute(
            select(Refund).where(
                Refund.transaction_id == transaction_id,
                Refund.merchant_id == merchant_id,
                Refund.is_deleted.is_(False),
            ).order_by(Refund.created_at.desc())
        )
    ).scalars().all()
    return [_to_response(r) for r in rows]


def _to_response(refund: Refund) -> RefundResponse:
    return RefundResponse(
        id=refund.id,
        transaction_id=refund.transaction_id,
        merchant_id=refund.merchant_id,
        amount=refund.amount,
        currency=refund.currency,
        refund_type=refund.refund_type,
        status=refund.status,
        reason=refund.reason,
        gateway_refund_id=refund.gateway_refund_id,
        utr_number=refund.utr_number,
        error_code=refund.error_code,
        error_message=refund.error_message,
        processed_at=refund.processed_at,
        created_at=refund.created_at,
    )
