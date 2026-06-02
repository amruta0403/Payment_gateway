from __future__ import annotations

import asyncio
import random
import string
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.base import NpciClient, NpciCollectRequest
from models.upi_transaction import (
    MerchantVpa,
    UpiMandate,
    UpiMandateFrequency,
    UpiMandateStatus,
    UpiStatus,
    UpiTransaction,
)
from schemas.upi import (
    CollectRequest,
    CollectResponse,
    IntentRequest,
    IntentResponse,
    MandateCreateRequest,
    MandateResponse,
    UpiCallbackPayload,
    UpiStatusResponse,
)
from shared.cache.redis_client import cache_get, cache_set
from shared.exceptions.handlers import PaymentGatewayError
from shared.kafka.topics import Topics

log = structlog.get_logger()

_DEFAULT_EXPIRY_SECONDS = 300
_VPA_CACHE_TTL = 300  # 5 minutes


def _make_ref_id() -> str:
    dt = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    suffix = "".join(random.choices(string.digits, k=6))
    return f"PG{dt}{suffix}"


class UpiService:
    def __init__(
        self,
        npci_client: NpciClient,
        session_factory,
        redis,
        kafka_producer,
        encryptor=None,
        gateway_vpa: str = "merchant@hdfc",
    ) -> None:
        self._npci = npci_client
        self._factory = session_factory
        self._redis = redis
        self._kafka = kafka_producer
        self._enc = encryptor
        self._gateway_vpa = gateway_vpa

    def _encrypt(self, value: str | None) -> str | None:
        if not value or not self._enc:
            return value
        return self._enc.encrypt(value)

    def _decrypt(self, value: str | None) -> str | None:
        if not value or not self._enc:
            return value
        try:
            return self._enc.decrypt(value)
        except Exception:
            return None

    async def _get_merchant_vpa(self, merchant_id: uuid.UUID, db: AsyncSession) -> str:
        row = (
            await db.execute(
                select(MerchantVpa).where(
                    MerchantVpa.merchant_id == merchant_id,
                    MerchantVpa.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        return row.vpa if row else self._gateway_vpa

    # ── Collect ───────────────────────────────────────────────────────────────

    async def initiate_collect(
        self,
        payment_id: uuid.UUID,
        request: CollectRequest,
        merchant_id: uuid.UUID,
        db: AsyncSession,
    ) -> CollectResponse:
        payee_vpa = await self._get_merchant_vpa(merchant_id, db)
        our_ref_id = _make_ref_id()

        npci_req = NpciCollectRequest(
            our_ref_id=our_ref_id,
            payer_vpa=request.payer_vpa,
            payee_vpa=payee_vpa,
            amount=request.amount,
            description=request.description,
            expiry_seconds=request.expiry_seconds,
        )
        npci_resp = await self._npci.send_collect(npci_req)

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=request.expiry_seconds)

        txn = UpiTransaction(
            transaction_id=payment_id,
            merchant_id=merchant_id,
            our_ref_id=our_ref_id,
            npci_txn_id=npci_resp.npci_txn_id,
            vpa_payer=self._encrypt(request.payer_vpa),
            vpa_payee=payee_vpa,
            amount=request.amount,
            status=npci_resp.status,
            collect_expiry_at=expires_at,
            decline_code=npci_resp.decline_code,
            decline_reason=npci_resp.decline_reason,
        )
        db.add(txn)
        await db.commit()

        if npci_resp.status == UpiStatus.PENDING:
            asyncio.create_task(
                self.poll_until_terminal(our_ref_id)
            )

        return CollectResponse(
            our_ref_id=our_ref_id,
            npci_txn_id=npci_resp.npci_txn_id,
            status=npci_resp.status,
            expires_at=expires_at,
        )

    # ── Intent ────────────────────────────────────────────────────────────────

    async def generate_intent(
        self,
        payment_id: uuid.UUID,
        request: IntentRequest,
        merchant_id: uuid.UUID,
        db: AsyncSession,
    ) -> IntentResponse:
        payee_vpa = await self._get_merchant_vpa(merchant_id, db)
        our_ref_id = _make_ref_id()
        amount_rupees = request.amount / 100

        deep_link = (
            f"upi://pay?pa={payee_vpa}"
            f"&pn=PaymentGateway"
            f"&am={amount_rupees:.2f}"
            f"&cu=INR"
            f"&tn={request.description}"
            f"&tr={our_ref_id}"
        )
        qr_b64 = self._npci.generate_qr(payee_vpa, request.amount, request.description)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=_DEFAULT_EXPIRY_SECONDS)

        txn = UpiTransaction(
            transaction_id=payment_id,
            merchant_id=merchant_id,
            our_ref_id=our_ref_id,
            vpa_payee=payee_vpa,
            amount=request.amount,
            status=UpiStatus.INITIATED,
            upi_deep_link=deep_link,
            qr_code_base64=qr_b64,
            collect_expiry_at=expires_at,
        )
        db.add(txn)
        await db.commit()

        asyncio.create_task(self.poll_until_terminal(our_ref_id))

        return IntentResponse(
            our_ref_id=our_ref_id,
            upi_deep_link=deep_link,
            qr_code_base64=qr_b64,
            expires_at=expires_at,
        )

    # ── Poll until terminal ───────────────────────────────────────────────────

    async def poll_until_terminal(
        self,
        our_ref_id: str,
        max_attempts: int = 12,
    ) -> None:
        delays = [5, 10, 20, 30, 30, 30, 30, 30, 60, 60, 60, 60]
        for i, delay in enumerate(delays[:max_attempts]):
            await asyncio.sleep(delay)
            try:
                result = await self._npci.check_status(our_ref_id)
                if result.status in (UpiStatus.SUCCESS, UpiStatus.FAILED, UpiStatus.EXPIRED):
                    await self._finalize_transaction(our_ref_id, result)
                    return
            except Exception as exc:
                log.warning("upi.poll.error", ref_id=our_ref_id, attempt=i, error=str(exc))

        await self._expire_transaction(our_ref_id)

    async def _finalize_transaction(self, our_ref_id: str, result) -> None:
        now = datetime.now(timezone.utc)
        async with self._factory() as session:
            await session.execute(
                update(UpiTransaction)
                .where(UpiTransaction.our_ref_id == our_ref_id)
                .values(
                    status=result.status,
                    completed_at=result.completed_at or now,
                    npci_txn_id=result.npci_txn_id,
                    decline_code=result.decline_code,
                    decline_reason=result.decline_reason,
                )
            )
            await session.commit()

        if self._kafka and result.status == UpiStatus.SUCCESS:
            try:
                await self._kafka.publish(
                    Topics.UPI_COLLECT_COMPLETED,
                    "upi.collect.completed",
                    {"our_ref_id": our_ref_id, "status": result.status.value},
                    key=our_ref_id,
                )
            except Exception as exc:
                log.warning("upi.finalize.kafka_error", error=str(exc))

    async def _expire_transaction(self, our_ref_id: str) -> None:
        async with self._factory() as session:
            await session.execute(
                update(UpiTransaction)
                .where(
                    UpiTransaction.our_ref_id == our_ref_id,
                    UpiTransaction.status == UpiStatus.PENDING,
                )
                .values(status=UpiStatus.EXPIRED, completed_at=datetime.now(timezone.utc))
            )
            await session.commit()
        log.info("upi.transaction.expired", ref_id=our_ref_id)

    # ── Callback ──────────────────────────────────────────────────────────────

    async def handle_callback(
        self,
        payload: UpiCallbackPayload,
        signature_header: str,
        raw_body: bytes,
        db: AsyncSession,
    ) -> bool:
        valid = await self._npci.validate_callback(
            {"X-UPI-Signature": signature_header}, raw_body
        )
        if not valid:
            log.warning("upi.callback.invalid_signature", ref_id=payload.refId)
            return False

        status = (
            UpiStatus.SUCCESS
            if payload.status.upper() == "SUCCESS"
            else UpiStatus.FAILED
        )
        now = datetime.now(timezone.utc)

        await db.execute(
            update(UpiTransaction)
            .where(UpiTransaction.our_ref_id == payload.refId)
            .values(
                status=status,
                npci_txn_id=payload.txnId,
                vpa_payer=self._encrypt(payload.payerVPA),
                callback_received_at=now,
                completed_at=now if status == UpiStatus.SUCCESS else None,
                raw_callback=payload.model_dump(),
                decline_code=payload.respCode if status == UpiStatus.FAILED else None,
                decline_reason=payload.respMsg if status == UpiStatus.FAILED else None,
            )
        )
        await db.commit()

        if self._kafka:
            topic = (
                Topics.UPI_COLLECT_COMPLETED
                if status == UpiStatus.SUCCESS
                else Topics.UPI_COLLECT_FAILED
            )
            try:
                await self._kafka.publish(
                    topic,
                    f"upi.{status.value.lower()}",
                    {"ref_id": payload.refId, "npci_txn_id": payload.txnId},
                    key=payload.refId,
                )
            except Exception as exc:
                log.warning("upi.callback.kafka_error", error=str(exc))

        return True

    # ── VPA validate (with Redis cache) ──────────────────────────────────────

    async def validate_vpa(self, vpa: str) -> dict:
        cache_key = f"vpa:{vpa.lower()}"
        cached = await cache_get(self._redis, cache_key)
        if cached:
            return cached

        resolution = await self._npci.resolve_vpa(vpa)
        result = {
            "vpa": vpa,
            "is_valid": resolution.is_valid,
            "account_name": resolution.account_name,
            "bank_name": resolution.bank_name,
        }
        if resolution.is_valid:
            await cache_set(self._redis, cache_key, result, ttl=_VPA_CACHE_TTL)
        return result

    # ── Mandate ───────────────────────────────────────────────────────────────

    async def create_mandate(
        self,
        merchant_id: uuid.UUID,
        request: MandateCreateRequest,
        db: AsyncSession,
    ) -> MandateResponse:
        mandate = UpiMandate(
            merchant_id=merchant_id,
            customer_vpa=self._encrypt(request.customer_vpa) or request.customer_vpa,
            amount=request.amount,
            frequency=request.frequency,
            start_date=request.start_date,
            end_date=request.end_date,
            status=UpiMandateStatus.PENDING,
        )
        db.add(mandate)
        await db.commit()
        await db.refresh(mandate)
        return self._mandate_response(mandate)

    async def get_mandate(self, mandate_id: uuid.UUID, db: AsyncSession) -> MandateResponse:
        m = await db.get(UpiMandate, mandate_id)
        if not m:
            raise PaymentGatewayError("Mandate not found")
        return self._mandate_response(m)

    async def execute_mandate(
        self, mandate_id: uuid.UUID, amount: int, db: AsyncSession
    ) -> dict:
        m = await db.get(UpiMandate, mandate_id)
        if not m or m.status != UpiMandateStatus.ACTIVE:
            raise PaymentGatewayError("Mandate not active")
        # In production: call NPCI mandate debit API
        return {"status": "debit_initiated", "mandate_id": str(mandate_id), "amount": amount}

    async def revoke_mandate(self, mandate_id: uuid.UUID, db: AsyncSession) -> None:
        m = await db.get(UpiMandate, mandate_id)
        if not m:
            raise PaymentGatewayError("Mandate not found")
        m.status = UpiMandateStatus.REVOKED
        await db.commit()

    def _mandate_response(self, m: UpiMandate) -> MandateResponse:
        return MandateResponse(
            id=m.id,
            merchant_id=m.merchant_id,
            customer_vpa=self._decrypt(m.customer_vpa) or m.customer_vpa,
            amount=m.amount,
            frequency=m.frequency,
            start_date=m.start_date,
            end_date=m.end_date,
            status=m.status,
            mandate_ref_id=m.mandate_ref_id,
            created_at=m.created_at,
        )
