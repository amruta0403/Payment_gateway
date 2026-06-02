"""
Razorpay X payout provider stub.
In production, use Razorpay X Fund Accounts + Payouts API.
https://razorpay.com/docs/razorpayx/api/payouts/
"""
from __future__ import annotations

import logging

import requests

from payout_providers.base import PayoutProvider, PayoutResult

log = logging.getLogger(__name__)

_RAZORPAY_X_BASE = "https://api.razorpay.com/v1"


class RazorpayXProvider(PayoutProvider):
    def __init__(self, key_id: str, key_secret: str, account_number: str) -> None:
        self._auth = (key_id, key_secret)
        self._account_number = account_number   # Razorpay X source account

    def create_payout(
        self,
        account_number: str,
        ifsc: str,
        amount: int,
        reference: str,
        account_holder_name: str = "",
    ) -> PayoutResult:
        try:
            # Step 1: Create / fetch fund account
            fa_resp = requests.post(
                f"{_RAZORPAY_X_BASE}/fund_accounts",
                auth=self._auth,
                json={
                    "contact_id": f"cont_{reference[:20]}",
                    "account_type": "bank_account",
                    "bank_account": {
                        "name": account_holder_name or "Merchant",
                        "ifsc": ifsc,
                        "account_number": account_number,
                    },
                },
                timeout=30,
            )
            fa_resp.raise_for_status()
            fund_account_id = fa_resp.json()["id"]

            # Step 2: Create payout
            payout_resp = requests.post(
                f"{_RAZORPAY_X_BASE}/payouts",
                auth=self._auth,
                json={
                    "account_number": self._account_number,
                    "fund_account_id": fund_account_id,
                    "amount": amount,          # paise
                    "currency": "INR",
                    "mode": "IMPS",
                    "purpose": "settlement",
                    "reference_id": reference,
                    "narration": f"Settlement {reference[:15]}",
                },
                timeout=30,
            )
            payout_resp.raise_for_status()
            data = payout_resp.json()
            return PayoutResult(
                success=data.get("status") not in ("failed", "reversed"),
                utr=data.get("utr"),
                provider_ref=data.get("id"),
            )
        except Exception as exc:
            log.error("razorpay_x.payout.error", exc_info=True)
            return PayoutResult(success=False, error=str(exc))

    def check_status(self, provider_ref: str) -> PayoutResult:
        try:
            resp = requests.get(
                f"{_RAZORPAY_X_BASE}/payouts/{provider_ref}",
                auth=self._auth,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return PayoutResult(
                success=data.get("status") == "processed",
                utr=data.get("utr"),
                provider_ref=provider_ref,
            )
        except Exception as exc:
            return PayoutResult(success=False, error=str(exc))
