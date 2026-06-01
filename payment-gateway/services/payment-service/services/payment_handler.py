from __future__ import annotations

import uuid
from typing import Any

import structlog

from adapters.base import AcquirerAdapter, ChargeResult
from models.payment import Transaction
from services.http_client import ServiceClient
from shared.exceptions.handlers import CardDeclinedError, ServiceUnavailableError
from shared.models.enums import PaymentMethod

log = structlog.get_logger()


class PaymentMethodHandler:
    """
    Routes a payment to the correct downstream service based on payment method.
    All network calls use ServiceClient (retry + circuit breaker).
    """

    def __init__(
        self,
        card_vault_url: str,
        upi_url: str,
        netbanking_url: str,
        service_token: str,
        acquirer: AcquirerAdapter,
        gateway_vpa: str = "merchant@hdfc",
        trace_id: str | None = None,
    ) -> None:
        self._vault_client = ServiceClient(card_vault_url, service_token, trace_id)
        self._upi_client = ServiceClient(upi_url, service_token, trace_id)
        self._nb_client = ServiceClient(netbanking_url, service_token, trace_id)
        self._acquirer = acquirer
        self._gateway_vpa = gateway_vpa

    async def handle_card(
        self,
        payment: Transaction,
        card: dict[str, Any],
        merchant_id: uuid.UUID,
    ) -> dict[str, Any]:
        # Step 1: Tokenize PAN in card vault (PCI-isolated)
        tokenize_resp = await self._vault_client.post(
            "/vault/tokenize",
            json={
                "pan": card["number"],
                "expiry_month": card["expiry_month"],
                "expiry_year": card["expiry_year"],
                "cvv": card["cvv"],
                "cardholder_name": card.get("cardholder_name"),
                "merchant_id": str(merchant_id),
            },
        )

        if "error" in tokenize_resp:
            err = tokenize_resp["error"]
            raise CardDeclinedError(
                err.get("message", "Card tokenization failed"), param="card"
            )

        token: str = tokenize_resp["token"]
        payment.card_token = uuid.UUID(token)
        payment.card_last4 = tokenize_resp.get("last4")
        payment.card_network = tokenize_resp.get("card_network")

        # Step 2: Charge via acquirer
        result: ChargeResult = await self._acquirer.charge(
            token=token,
            amount=payment.amount,
            currency=payment.currency,
            metadata={
                "card_number": card["number"],  # used by MockAcquirerAdapter only
                "merchant_id": str(merchant_id),
                "order_id": payment.order_id or "",
                "description": payment.description or "",
            },
        )

        if not result.success:
            payment.error_code = result.error_code
            payment.error_message = result.error_message
            raise CardDeclinedError(
                result.error_message or "Card declined by acquirer",
                param="card",
            )

        payment.gateway_txn_id = result.gateway_txn_id
        payment.auth_code = result.auth_code
        payment.rrn = result.rrn
        payment.acquirer_ref_no = result.acquirer_ref_no

        return {"gateway_txn_id": result.gateway_txn_id, "action_required": result.action_required}

    async def handle_upi(
        self,
        payment: Transaction,
        upi_vpa: str | None,
        merchant_id: uuid.UUID,
    ) -> dict[str, Any]:
        if upi_vpa:
            # Collect flow: push notification to payer's UPI app
            resp = await self._upi_client.post(
                "/v1/upi/collect",
                json={
                    "payment_id": str(payment.id),
                    "payer_vpa": upi_vpa,
                    "amount": payment.amount,
                    "description": payment.description or "",
                    "merchant_vpa": self._gateway_vpa,
                    "expiry_seconds": 300,
                },
            )
            payment.upi_txn_id = resp.get("our_ref_id")
            return {
                "action_required": {
                    "type": "upi_collect",
                    "our_ref_id": resp.get("our_ref_id"),
                    "expires_at": resp.get("expires_at"),
                    "message": "Check your UPI app to approve the payment",
                }
            }
        else:
            # Intent flow: generate deep-link + QR
            resp = await self._upi_client.post(
                "/v1/upi/intent",
                json={
                    "payment_id": str(payment.id),
                    "amount": payment.amount,
                    "merchant_vpa": self._gateway_vpa,
                    "description": payment.description or "",
                },
            )
            return {
                "action_required": {
                    "type": "upi_intent",
                    "upi_deep_link": resp.get("upi_deep_link"),
                    "qr_code_base64": resp.get("qr_code_base64"),
                    "expires_at": resp.get("expires_at"),
                }
            }

    async def handle_netbanking(
        self,
        payment: Transaction,
        bank_code: str,
        merchant_id: uuid.UUID,
    ) -> dict[str, Any]:
        resp = await self._nb_client.post(
            "/netbanking/initiate",
            json={
                "payment_id": str(payment.id),
                "bank_code": bank_code,
                "amount": payment.amount,
                "currency": payment.currency,
                "return_url": str(payment.callback_url) if payment.callback_url else "",
                "description": payment.description or "",
            },
        )
        payment.bank_txn_id = resp.get("bank_txn_id")
        payment.redirect_url = resp.get("redirect_url")
        return {
            "action_required": {
                "type": "redirect",
                "redirect_url": resp.get("redirect_url"),
                "bank_txn_id": resp.get("bank_txn_id"),
            }
        }
