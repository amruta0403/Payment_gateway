from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from models.merchant_bank_account import MerchantBankAccount
from shared.exceptions.handlers import PaymentGatewayError
from shared.utils.encryption import FieldEncryptor

log = structlog.get_logger()


async def initiate_penny_drop(
    bank_account_id: uuid.UUID,
    db: AsyncSession,
    encryptor: FieldEncryptor,
    razorpay_key_id: str,
    razorpay_key_secret: str,
    environment: str = "development",
) -> dict:
    account = await db.get(MerchantBankAccount, bank_account_id)
    if not account:
        raise PaymentGatewayError("Bank account not found")

    if account.is_verified:
        return {"status": "already_verified", "message": "Bank account is already verified"}

    # Generate random 1–2 paise amount
    amount_paise = random.randint(1, 2)

    if environment == "development":
        # Mock: store amount and return immediately
        account.penny_drop_ref = f"mock_pd_{uuid.uuid4().hex[:12]}"
        account.penny_drop_amount = amount_paise
        account.penny_drop_initiated_at = datetime.now(timezone.utc)
        await db.commit()
        log.info("penny_drop.mock_initiated", account_id=str(bank_account_id), amount=amount_paise)
        return {"status": "initiated", "expected_amount_paise": amount_paise, "message": "Penny drop initiated (mock)"}

    # Decrypt account number for Razorpay call
    account_number = encryptor.decrypt(account.account_number)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Create fund account on Razorpay X
            resp = await client.post(
                "https://api.razorpay.com/v1/fund_accounts",
                auth=(razorpay_key_id, razorpay_key_secret),
                json={
                    "contact_id": f"cont_{account.merchant_id}",
                    "account_type": "bank_account",
                    "bank_account": {
                        "name": account.account_holder_name,
                        "ifsc": account.ifsc_code,
                        "account_number": account_number,
                    },
                },
            )
            data = resp.json()
            fund_account_id = data.get("id", "")

            # Validate via penny drop
            validate_resp = await client.post(
                "https://api.razorpay.com/v1/fund_accounts/validations",
                auth=(razorpay_key_id, razorpay_key_secret),
                json={
                    "account_number": "REPLACE_WITH_RAZORPAY_X_ACCOUNT",
                    "fund_account": {"id": fund_account_id},
                    "amount": amount_paise,
                    "currency": "INR",
                    "notes": {"merchant_id": str(account.merchant_id)},
                },
            )
            ref = validate_resp.json().get("id", "")

            account.penny_drop_ref = ref
            account.penny_drop_amount = amount_paise
            account.penny_drop_initiated_at = datetime.now(timezone.utc)
            await db.commit()

    except Exception as exc:
        log.error("penny_drop.initiate.failed", error=str(exc))
        raise PaymentGatewayError("Failed to initiate penny drop") from exc

    return {"status": "initiated", "expected_amount_paise": amount_paise, "message": "Penny drop initiated"}


async def verify_penny_drop(
    bank_account_id: uuid.UUID,
    stated_amount_paise: int,
    db: AsyncSession,
) -> dict:
    account = await db.get(MerchantBankAccount, bank_account_id)
    if not account:
        raise PaymentGatewayError("Bank account not found")

    if not account.penny_drop_amount:
        return {"verified": False, "message": "No penny drop initiated for this account"}

    if account.penny_drop_amount == stated_amount_paise:
        account.is_verified = True
        account.verified_at = datetime.now(timezone.utc)
        # Set as primary if it's the first verified account
        await db.commit()
        log.info("penny_drop.verified", account_id=str(bank_account_id))
        return {"verified": True, "message": "Bank account verified successfully"}

    log.warning("penny_drop.mismatch", account_id=str(bank_account_id), stated=stated_amount_paise, actual=account.penny_drop_amount)
    return {"verified": False, "message": "Amount mismatch — check your bank statement and try again"}
