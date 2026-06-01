from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChargeResult:
    success: bool
    gateway_txn_id: str | None = None
    auth_code: str | None = None
    rrn: str | None = None
    acquirer_ref_no: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    action_required: dict[str, Any] | None = None  # populated for 3DS challenge


@dataclass
class CaptureResult:
    success: bool
    gateway_txn_id: str | None = None
    rrn: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class RefundResult:
    success: bool
    refund_id: str | None = None
    rrn: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class VoidResult:
    success: bool
    error_code: str | None = None
    error_message: str | None = None


class AcquirerAdapter(ABC):
    @abstractmethod
    async def charge(
        self,
        token: str,
        amount: int,
        currency: str,
        metadata: dict[str, Any],
    ) -> ChargeResult: ...

    @abstractmethod
    async def capture(self, txn_id: str, amount: int) -> CaptureResult: ...

    @abstractmethod
    async def refund(self, txn_id: str, amount: int) -> RefundResult: ...

    @abstractmethod
    async def void(self, txn_id: str) -> VoidResult: ...
