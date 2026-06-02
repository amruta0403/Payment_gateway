from __future__ import annotations

import random
import string
from datetime import datetime

from payout_providers.base import PayoutProvider, PayoutResult

_FAIL_ACCOUNTS = {"00000000000000", "99999999999999"}


def _gen_utr() -> str:
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    suffix = "".join(random.choices(string.digits, k=6))
    return f"UTR{ts}{suffix}"


class MockPayoutProvider(PayoutProvider):
    """In-process mock payout provider — always succeeds except for test failure accounts."""

    def create_payout(
        self,
        account_number: str,
        ifsc: str,
        amount: int,
        reference: str,
        account_holder_name: str = "",
    ) -> PayoutResult:
        if account_number in _FAIL_ACCOUNTS:
            return PayoutResult(
                success=False,
                error=f"Mock: Simulated failure for account {account_number[-4:]}",
            )
        return PayoutResult(
            success=True,
            utr=_gen_utr(),
            provider_ref=f"MOCK-{reference[:20]}",
        )

    def check_status(self, provider_ref: str) -> PayoutResult:
        return PayoutResult(success=True, utr=provider_ref)
