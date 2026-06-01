from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog

from adapters.base import AcquirerAdapter, CaptureResult, ChargeResult, RefundResult, VoidResult

log = structlog.get_logger()

# Test card number → (outcome, error_code)
_CARD_BEHAVIOUR: dict[str, tuple[str, str | None]] = {
    "4111111111111111": ("SUCCESS", None),
    "4000000000000002": ("DECLINED", "insufficient_funds"),
    "4000000000000069": ("DECLINED", "expired_card"),
    "4000000000000119": ("ERROR", "processing_error"),
}


class MockAcquirerAdapter(AcquirerAdapter):
    """
    Simulates an acquirer in development/test mode.
    Behaviour is driven by card_number passed in metadata["card_number"].
    Any other card number results in SUCCESS.
    """

    async def charge(
        self,
        token: str,
        amount: int,
        currency: str,
        metadata: dict[str, Any],
    ) -> ChargeResult:
        await asyncio.sleep(0.2)  # simulate network latency

        card_number = metadata.get("card_number", "")
        outcome, error_code = _CARD_BEHAVIOUR.get(card_number, ("SUCCESS", None))

        log.debug(
            "mock_acquirer.charge",
            card_last4=card_number[-4:] if len(card_number) >= 4 else "????",
            outcome=outcome,
        )

        if outcome == "SUCCESS":
            return ChargeResult(
                success=True,
                gateway_txn_id=f"mock_gtxn_{uuid.uuid4().hex[:16]}",
                auth_code=f"AUTH{uuid.uuid4().hex[:6].upper()}",
                rrn=f"RRN{uuid.uuid4().hex[:12].upper()}",
                acquirer_ref_no=f"ARN{uuid.uuid4().hex[:10].upper()}",
            )
        elif outcome == "DECLINED":
            return ChargeResult(
                success=False,
                error_code=error_code,
                error_message=f"Card declined: {error_code}",
            )
        else:
            return ChargeResult(
                success=False,
                error_code=error_code or "processing_error",
                error_message="A processing error occurred. Please try again.",
            )

    async def capture(self, txn_id: str, amount: int) -> CaptureResult:
        await asyncio.sleep(0.1)
        return CaptureResult(
            success=True,
            gateway_txn_id=txn_id,
            rrn=f"RRN{uuid.uuid4().hex[:12].upper()}",
        )

    async def refund(self, txn_id: str, amount: int) -> RefundResult:
        await asyncio.sleep(0.1)
        return RefundResult(
            success=True,
            refund_id=f"mock_ref_{uuid.uuid4().hex[:16]}",
            rrn=f"RRN{uuid.uuid4().hex[:12].upper()}",
        )

    async def void(self, txn_id: str) -> VoidResult:
        await asyncio.sleep(0.1)
        return VoidResult(success=True)
