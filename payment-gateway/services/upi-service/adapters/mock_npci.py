from __future__ import annotations

import asyncio
import base64
import io
import random
import string
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import structlog

from adapters.base import (
    NpciClient,
    NpciCollectRequest,
    NpciCollectResponse,
    NpciStatusResponse,
    VpaResolution,
)
from models.upi_transaction import UpiStatus
from shared.kafka.topics import Topics

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

log = structlog.get_logger()

# ── Known test VPAs ───────────────────────────────────────────────────────────
_KNOWN_VPA_MAP: dict[str, VpaResolution] = {
    "success@upi":  VpaResolution(is_valid=True,  account_name="Test User",  bank_name="HDFC Bank"),
    "fail@upi":     VpaResolution(is_valid=True,  account_name="Fail User",  bank_name="SBI"),
    "timeout@upi":  VpaResolution(is_valid=True,  account_name="Slow User",  bank_name="ICICI"),
    "invalid@xyz":  VpaResolution(is_valid=False),
}

# Valid UPI handle suffixes
_VALID_HANDLES = frozenset({
    "upi", "hdfc", "sbi", "oksbi", "okaxis", "paytm", "icici",
    "kotak", "ybl", "ibl", "okhdfcbank", "okicici", "axis",
})


def _is_valid_vpa(vpa: str) -> bool:
    if "@" not in vpa:
        return False
    parts = vpa.split("@", 1)
    return len(parts[0]) > 0 and parts[1].lower() in _VALID_HANDLES


def _make_ref_id() -> str:
    dt = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    suffix = "".join(random.choices(string.digits, k=6))
    return f"PG{dt}{suffix}"


class MockNpciClient(NpciClient):
    """In-process UPI mock — no real NPCI calls. Used for ENVIRONMENT=development."""

    def __init__(
        self,
        session_factory=None,
        kafka_producer=None,
        resolution_delay: float = 5.0,
    ) -> None:
        self._session_factory = session_factory
        self._kafka = kafka_producer
        self._resolution_delay = resolution_delay
        # In-memory status store for stateless check_status
        self._statuses: dict[str, NpciStatusResponse] = {}

    # ── NpciClient interface ──────────────────────────────────────────────────

    async def resolve_vpa(self, vpa: str) -> VpaResolution:
        vpa_lower = vpa.lower()
        if vpa_lower in _KNOWN_VPA_MAP:
            return _KNOWN_VPA_MAP[vpa_lower]
        if _is_valid_vpa(vpa_lower):
            return VpaResolution(is_valid=True, account_name="Mock User", bank_name="Mock Bank")
        return VpaResolution(is_valid=False)

    async def send_collect(self, req: NpciCollectRequest) -> NpciCollectResponse:
        payer = req.payer_vpa.lower()

        if payer == "fail@upi":
            return NpciCollectResponse(
                our_ref_id=req.our_ref_id,
                status=UpiStatus.FAILED,
                decline_code="U30",
                decline_reason="Transaction declined by payer bank",
            )

        if payer == "timeout@upi":
            await asyncio.sleep(6)
            return NpciCollectResponse(
                our_ref_id=req.our_ref_id,
                status=UpiStatus.FAILED,
                decline_code="U99",
                decline_reason="Transaction timed out",
            )

        # Normal: return PENDING, resolve in background
        from datetime import timedelta
        expires = datetime.now(timezone.utc) + timedelta(seconds=req.expiry_seconds)

        resp = NpciCollectResponse(
            our_ref_id=req.our_ref_id,
            status=UpiStatus.PENDING,
            npci_txn_id=f"NPCI{_make_ref_id()}",
            expires_at=expires,
        )
        # Store initial status
        self._statuses[req.our_ref_id] = NpciStatusResponse(
            status=UpiStatus.PENDING,
            npci_txn_id=resp.npci_txn_id,
        )

        if self._resolution_delay > 0:
            asyncio.create_task(self._resolve_after(req.our_ref_id, resp.npci_txn_id))
        else:
            # Immediate resolution for tests with delay=0
            await self._resolve_after(req.our_ref_id, resp.npci_txn_id)

        return resp

    async def check_status(self, our_ref_id: str) -> NpciStatusResponse:
        return self._statuses.get(
            our_ref_id,
            NpciStatusResponse(status=UpiStatus.PENDING),
        )

    async def validate_callback(self, headers: dict, body: bytes) -> bool:
        # Mock always validates
        return True

    def generate_qr(self, vpa: str, amount: int, description: str) -> str | None:
        deep_link = (
            f"upi://pay?pa={vpa}&pn=PaymentGateway"
            f"&am={amount/100:.2f}&cu=INR&tn={description}"
        )
        try:
            import qrcode  # type: ignore[import]

            buf = io.BytesIO()
            img = qrcode.make(deep_link)
            img.save(buf)
            return base64.b64encode(buf.getvalue()).decode()
        except ImportError:
            # qrcode not installed — return base64 of a placeholder
            placeholder = b"\x89PNG\r\n\x1a\n"  # minimal PNG header stub
            return base64.b64encode(placeholder).decode()

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _resolve_after(self, our_ref_id: str, npci_txn_id: str | None) -> None:
        if self._resolution_delay > 0:
            await asyncio.sleep(self._resolution_delay)

        now = datetime.now(timezone.utc)
        self._statuses[our_ref_id] = NpciStatusResponse(
            status=UpiStatus.SUCCESS,
            npci_txn_id=npci_txn_id,
            completed_at=now,
        )

        if self._session_factory:
            try:
                from sqlalchemy import update
                from models.upi_transaction import UpiTransaction
                async with self._session_factory() as session:
                    await session.execute(
                        update(UpiTransaction)
                        .where(UpiTransaction.our_ref_id == our_ref_id)
                        .values(
                            status=UpiStatus.SUCCESS,
                            completed_at=now,
                            npci_txn_id=npci_txn_id,
                        )
                    )
                    await session.commit()
                log.info("mock.upi.auto_resolved", ref_id=our_ref_id)
            except Exception as exc:
                log.warning("mock.upi.resolve.db_error", ref_id=our_ref_id, error=str(exc))

        if self._kafka:
            try:
                await self._kafka.publish(
                    Topics.UPI_COLLECT_COMPLETED,
                    "upi.collect.completed",
                    {"our_ref_id": our_ref_id, "status": "SUCCESS"},
                    key=our_ref_id,
                )
            except Exception as exc:
                log.warning("mock.upi.resolve.kafka_error", error=str(exc))
