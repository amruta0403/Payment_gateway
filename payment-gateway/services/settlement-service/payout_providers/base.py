from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PayoutResult:
    success: bool
    utr: str | None = None
    error: str | None = None
    provider_ref: str | None = None


class PayoutProvider(ABC):
    """Abstract payout provider interface."""

    @abstractmethod
    def create_payout(
        self,
        account_number: str,
        ifsc: str,
        amount: int,        # paise
        reference: str,
        account_holder_name: str = "",
    ) -> PayoutResult: ...

    @abstractmethod
    def check_status(self, provider_ref: str) -> PayoutResult: ...
