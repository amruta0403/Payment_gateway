from __future__ import annotations

from typing import Any

import httpx
import structlog

from adapters.base import AcquirerAdapter, CaptureResult, ChargeResult, RefundResult, VoidResult

log = structlog.get_logger()


class RazorpayAdapter(AcquirerAdapter):
    BASE_URL = "https://api.razorpay.com/v1"

    def __init__(self, key_id: str, key_secret: str) -> None:
        self._key_id = key_id
        self._key_secret = key_secret

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            auth=(self._key_id, self._key_secret),
            timeout=30.0,
            headers={"Content-Type": "application/json"},
        )

    async def charge(
        self,
        token: str,
        amount: int,
        currency: str,
        metadata: dict[str, Any],
    ) -> ChargeResult:
        async with self._client() as client:
            resp = await client.post(
                f"{self.BASE_URL}/payments/create/recurring",
                json={
                    "amount": amount,
                    "currency": currency,
                    "token": token,
                    "description": metadata.get("description", ""),
                    "notes": {k: str(v) for k, v in metadata.items()},
                },
            )
        if resp.status_code == 200:
            data = resp.json()
            acquirer = data.get("acquirer_data", {})
            return ChargeResult(
                success=True,
                gateway_txn_id=data.get("id"),
                auth_code=acquirer.get("auth_code"),
                rrn=acquirer.get("rrn"),
                acquirer_ref_no=acquirer.get("acquirer_reference"),
            )
        err = resp.json().get("error", {})
        log.warning("razorpay.charge.failed", code=err.get("code"), desc=err.get("description"))
        return ChargeResult(
            success=False,
            error_code=err.get("code"),
            error_message=err.get("description"),
        )

    async def capture(self, txn_id: str, amount: int) -> CaptureResult:
        async with self._client() as client:
            resp = await client.post(
                f"{self.BASE_URL}/payments/{txn_id}/capture",
                json={"amount": amount},
            )
        if resp.status_code == 200:
            data = resp.json()
            return CaptureResult(
                success=True,
                gateway_txn_id=data.get("id"),
                rrn=data.get("acquirer_data", {}).get("rrn"),
            )
        err = resp.json().get("error", {})
        return CaptureResult(
            success=False,
            error_code=err.get("code"),
            error_message=err.get("description"),
        )

    async def refund(self, txn_id: str, amount: int) -> RefundResult:
        async with self._client() as client:
            resp = await client.post(
                f"{self.BASE_URL}/payments/{txn_id}/refund",
                json={"amount": amount},
            )
        if resp.status_code == 200:
            data = resp.json()
            return RefundResult(success=True, refund_id=data.get("id"))
        err = resp.json().get("error", {})
        return RefundResult(
            success=False,
            error_code=err.get("code"),
            error_message=err.get("description"),
        )

    async def void(self, txn_id: str) -> VoidResult:
        # Razorpay: void = refund 100% of amount
        # We refund 0 here as a full-amount void via cancellation
        async with self._client() as client:
            resp = await client.post(
                f"{self.BASE_URL}/payments/{txn_id}/refund",
                json={},
            )
        if resp.status_code == 200:
            return VoidResult(success=True)
        err = resp.json().get("error", {})
        return VoidResult(
            success=False,
            error_code=err.get("code"),
            error_message=err.get("description"),
        )
