from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.base import AcquirerAdapter
from dependencies import DbSession, RedisDep, SettingsDep
from models.payment import Transaction, TransactionEvent
from schemas.payment import (
    CaptureRequest,
    PaymentCreateRequest,
    PaymentListResponse,
    PaymentResponse,
    TransactionEventResponse,
)
from services.http_client import ServiceClient
from services.payment_handler import PaymentMethodHandler
from shared.cache.redis_client import get_idempotency, set_idempotency
from shared.db.base import set_rls_context
from shared.exceptions.handlers import (
    CardDeclinedError,
    FraudBlockedError,
    InvalidTransitionError,
    PaymentGatewayError,
)
from shared.kafka.topics import Topics
from shared.models.enums import FraudDecision, PaymentMethod, TransactionStatus
from state_machine import PaymentStateMachine

log = structlog.get_logger()
router = APIRouter(prefix="/payments", tags=["payments"])


def _get_acquirer(request: Request) -> AcquirerAdapter:
    return request.app.state.acquirer


def _row_to_response(p: Transaction, action: dict | None = None) -> PaymentResponse:
    return PaymentResponse(
        id=p.id,
        merchant_id=p.merchant_id,
        amount=p.amount,
        currency=p.currency,
        status=p.status,
        payment_method=p.payment_method,
        card_last4=p.card_last4,
        card_network=p.card_network,
        order_id=p.order_id,
        gateway_txn_id=p.gateway_txn_id,
        fraud_score=p.fraud_score,
        created_at=p.created_at,
        updated_at=p.updated_at,
        action_required=action,
    )


async def _get_principal(request: Request) -> Any:
    validator = request.app.state.keycloak_validator
    dep = validator.get_combined_auth_dependency()
    return await dep(request)


@router.post("", response_model=PaymentResponse, status_code=201)
async def create_payment(
    request: Request,
    body: PaymentCreateRequest,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> PaymentResponse:
    if not x_idempotency_key:
        raise HTTPException(status_code=400, detail="X-Idempotency-Key header is required")

    principal = await _get_principal(request)
    merchant_id = uuid.UUID(principal.merchant_id)
    trace_id: str | None = getattr(request.state, "request_id", None)

    # ── Idempotency check ─────────────────────────────────────────────────────
    cached = await get_idempotency(redis, str(merchant_id), x_idempotency_key)
    if cached:
        log.info("payment.idempotency.hit", key=x_idempotency_key)
        return PaymentResponse(**cached)

    # ── Create record ─────────────────────────────────────────────────────────
    payment = Transaction(
        merchant_id=merchant_id,
        amount=body.amount,
        currency=body.currency,
        payment_method=body.payment_method,
        idempotency_key=x_idempotency_key,
        order_id=body.order_id,
        description=body.description,
        callback_url=str(body.callback_url) if body.callback_url else None,
        customer_email=body.customer.email,
        customer_phone=body.customer.phone,
        customer_name=body.customer.name,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        merchant_metadata=body.metadata,
        status=TransactionStatus.CREATED,
    )
    db.add(payment)
    await db.flush()

    await PaymentStateMachine.transition(
        payment, TransactionStatus.PENDING, db, triggered_by="api"
    )

    # ── Fraud scoring ─────────────────────────────────────────────────────────
    try:
        fc = ServiceClient(settings.FRAUD_SERVICE_URL, settings.INTERNAL_SERVICE_TOKEN, trace_id)
        fraud_resp = await fc.post(
            "/score",
            json={
                "payment_id": str(payment.id),
                "merchant_id": str(merchant_id),
                "amount": body.amount,
                "payment_method": body.payment_method.value,
                "ip_address": payment.ip_address or "0.0.0.0",
                "card_token": None,
                "card_fingerprint": None,
                "customer_email_hash": None,
                "customer_phone_hash": None,
            },
        )
        score = float(fraud_resp.get("fraud_score", 0.0))
        decision_str = fraud_resp.get("decision", "ALLOW")
        payment.fraud_score = score
        payment.fraud_decision = FraudDecision(decision_str)
        payment.rule_hits = fraud_resp.get("rule_hits", [])

        if payment.fraud_decision == FraudDecision.BLOCK:
            await PaymentStateMachine.transition(
                payment,
                TransactionStatus.FAILED,
                db,
                triggered_by="fraud_engine",
                message="Blocked by fraud engine",
                metadata={"fraud_score": score, "rule_hits": payment.rule_hits},
            )
            await db.commit()
            raise FraudBlockedError("Transaction blocked by fraud detection")

    except FraudBlockedError:
        raise
    except Exception as exc:
        # Fraud service unavailable → fail open, log warning
        log.warning("fraud.service.unreachable", error=str(exc))

    # ── Route to payment method ───────────────────────────────────────────────
    handler = PaymentMethodHandler(
        card_vault_url=settings.CARD_VAULT_SERVICE_URL,
        upi_url=settings.UPI_SERVICE_URL,
        netbanking_url=settings.NETBANKING_SERVICE_URL,
        service_token=settings.INTERNAL_SERVICE_TOKEN,
        acquirer=_get_acquirer(request),
        gateway_vpa=settings.GATEWAY_VPA,
        trace_id=trace_id,
    )

    action_required: dict | None = None
    new_status = TransactionStatus.PROCESSING

    try:
        if body.payment_method == PaymentMethod.CARD:
            result = await handler.handle_card(payment, body.card.model_dump(), merchant_id)
            action_required = result.get("action_required")
            new_status = TransactionStatus.CAPTURED

        elif body.payment_method == PaymentMethod.UPI:
            result = await handler.handle_upi(payment, body.upi_vpa, merchant_id)
            action_required = result.get("action_required")
            new_status = TransactionStatus.PENDING  # completes asynchronously

        elif body.payment_method == PaymentMethod.NETBANKING:
            result = await handler.handle_netbanking(payment, body.bank_code, merchant_id)
            action_required = result.get("action_required")
            new_status = TransactionStatus.PENDING  # completes via redirect

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Payment method {body.payment_method.value} not yet supported",
            )

    except (CardDeclinedError, FraudBlockedError):
        await PaymentStateMachine.transition(
            payment,
            TransactionStatus.FAILED,
            db,
            triggered_by="acquirer",
            message=payment.error_message,
        )
        await db.commit()
        raise

    except HTTPException:
        raise

    except Exception as exc:
        log.exception("payment.handler.unexpected_error", error=str(exc))
        payment.error_code = "PROCESSING_ERROR"
        payment.error_message = str(exc)
        await PaymentStateMachine.transition(
            payment,
            TransactionStatus.FAILED,
            db,
            triggered_by="system",
            message=str(exc),
        )
        await db.commit()
        raise PaymentGatewayError("Payment processing failed") from exc

    await PaymentStateMachine.transition(
        payment, new_status, db, triggered_by="payment_processor"
    )

    # ── Publish Kafka event ───────────────────────────────────────────────────
    producer = getattr(request.app.state, "kafka_producer", None)
    if producer:
        try:
            await producer.publish(
                Topics.PAYMENT_INITIATED,
                "payment.initiated",
                {
                    "transaction_id": str(payment.id),
                    "merchant_id": str(merchant_id),
                    "amount": payment.amount,
                    "currency": payment.currency,
                    "payment_method": payment.payment_method.value,
                    "status": payment.status.value,
                },
                key=str(payment.id),
                trace_id=trace_id,
            )
        except Exception as exc:
            log.warning("kafka.publish.failed", error=str(exc))

    await db.commit()

    resp = _row_to_response(payment, action_required)
    await set_idempotency(
        redis, str(merchant_id), x_idempotency_key, resp.model_dump(mode="json")
    )
    return resp


@router.get("", response_model=PaymentListResponse)
async def list_payments(
    request: Request,
    db: DbSession,
    settings: SettingsDep,
    status: TransactionStatus | None = None,
    payment_method: PaymentMethod | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    order_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> PaymentListResponse:
    principal = await _get_principal(request)
    merchant_id = uuid.UUID(principal.merchant_id)

    # Apply RLS (belt-and-suspenders on top of WHERE clause)
    conn = await db.connection()
    await set_rls_context(conn, str(merchant_id))

    base = select(Transaction).where(
        Transaction.merchant_id == merchant_id,
        Transaction.is_deleted.is_(False),
    )
    if status:
        base = base.where(Transaction.status == status)
    if payment_method:
        base = base.where(Transaction.payment_method == payment_method)
    if from_date:
        base = base.where(Transaction.created_at >= from_date)
    if to_date:
        base = base.where(Transaction.created_at <= to_date)
    if order_id:
        base = base.where(Transaction.order_id == order_id)
    if cursor:
        base = base.where(Transaction.created_at < datetime.fromisoformat(cursor))

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await db.execute(base.order_by(Transaction.created_at.desc()).limit(limit))
    ).scalars().all()

    next_cursor = rows[-1].created_at.isoformat() if len(rows) == limit else None
    return PaymentListResponse(
        items=[_row_to_response(p) for p in rows],
        total=total,
        cursor=next_cursor,
    )


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    request: Request,
    payment_id: uuid.UUID,
    db: DbSession,
    settings: SettingsDep,
) -> PaymentResponse:
    principal = await _get_principal(request)
    merchant_id = uuid.UUID(principal.merchant_id)

    payment = await db.get(Transaction, payment_id)
    if not payment or payment.merchant_id != merchant_id or payment.is_deleted:
        raise HTTPException(status_code=404, detail="Payment not found")

    # Mask encrypted VPA before returning
    if payment.upi_vpa:
        from shared.utils.masking import mask_vpa
        payment.upi_vpa = mask_vpa(payment.upi_vpa)

    return _row_to_response(payment)


@router.post("/{payment_id}/capture", response_model=PaymentResponse)
async def capture_payment(
    request: Request,
    payment_id: uuid.UUID,
    body: CaptureRequest,
    db: DbSession,
    settings: SettingsDep,
) -> PaymentResponse:
    principal = await _get_principal(request)
    merchant_id = uuid.UUID(principal.merchant_id)
    trace_id = getattr(request.state, "request_id", None)

    payment = await db.get(Transaction, payment_id)
    if not payment or payment.merchant_id != merchant_id or payment.is_deleted:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment.status != TransactionStatus.AUTHORIZED:
        raise InvalidTransitionError(
            f"Payment must be AUTHORIZED to capture (current: {payment.status.value})"
        )

    capture_amount = body.amount or payment.amount
    result = await _get_acquirer(request).capture(payment.gateway_txn_id, capture_amount)
    if not result.success:
        raise CardDeclinedError(result.error_message or "Capture failed")

    payment.captured_amount = capture_amount
    payment.rrn = result.rrn or payment.rrn

    await PaymentStateMachine.transition(
        payment,
        TransactionStatus.CAPTURED,
        db,
        triggered_by="merchant",
        message=f"Captured {capture_amount} paise",
    )

    producer = getattr(request.app.state, "kafka_producer", None)
    if producer:
        try:
            await producer.publish(
                Topics.PAYMENT_CAPTURED,
                "payment.captured",
                {"transaction_id": str(payment.id), "captured_amount": capture_amount},
                key=str(payment.id),
                trace_id=trace_id,
            )
        except Exception:
            pass

    await db.commit()
    return _row_to_response(payment)


@router.post("/{payment_id}/cancel", response_model=PaymentResponse)
async def cancel_payment(
    request: Request,
    payment_id: uuid.UUID,
    db: DbSession,
    settings: SettingsDep,
) -> PaymentResponse:
    principal = await _get_principal(request)
    merchant_id = uuid.UUID(principal.merchant_id)

    payment = await db.get(Transaction, payment_id)
    if not payment or payment.merchant_id != merchant_id or payment.is_deleted:
        raise HTTPException(status_code=404, detail="Payment not found")

    cancellable = {
        TransactionStatus.CREATED,
        TransactionStatus.PENDING,
        TransactionStatus.AUTHORIZED,
    }
    if payment.status not in cancellable:
        raise InvalidTransitionError(
            f"Cannot cancel payment in status {payment.status.value}"
        )

    if payment.status == TransactionStatus.AUTHORIZED and payment.gateway_txn_id:
        void_result = await _get_acquirer(request).void(payment.gateway_txn_id)
        if not void_result.success:
            log.warning(
                "payment.void.failed",
                payment_id=str(payment_id),
                error=void_result.error_message,
            )

    await PaymentStateMachine.transition(
        payment, TransactionStatus.CANCELLED, db, triggered_by="merchant"
    )
    await db.commit()
    return _row_to_response(payment)


@router.get("/{payment_id}/events", response_model=list[TransactionEventResponse])
async def get_payment_events(
    request: Request,
    payment_id: uuid.UUID,
    db: DbSession,
    settings: SettingsDep,
) -> list[TransactionEventResponse]:
    principal = await _get_principal(request)
    merchant_id = uuid.UUID(principal.merchant_id)

    payment = await db.get(Transaction, payment_id)
    if not payment or payment.merchant_id != merchant_id or payment.is_deleted:
        raise HTTPException(status_code=404, detail="Payment not found")

    stmt = (
        select(TransactionEvent)
        .where(TransactionEvent.transaction_id == payment_id)
        .order_by(TransactionEvent.created_at.asc())
    )
    events = (await db.execute(stmt)).scalars().all()
    return [TransactionEventResponse.model_validate(e) for e in events]
