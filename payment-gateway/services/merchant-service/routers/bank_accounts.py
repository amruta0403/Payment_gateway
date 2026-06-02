from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db_session, get_principal
from models.merchant_bank_account import MerchantBankAccount
from schemas.merchant import (
    BankAccountRequest,
    BankAccountResponse,
    PennyDropResponse,
    PennyDropVerifyRequest,
    PennyDropVerifyResponse,
)
from services.penny_drop_service import initiate_penny_drop, verify_penny_drop
from shared.utils.encryption import FieldEncryptor

log = structlog.get_logger()
router = APIRouter(tags=["bank-accounts"])


def _check_access(merchant_id: uuid.UUID, principal) -> None:
    roles = getattr(principal, "roles", [])
    if "ADMIN" in roles:
        return
    mid = getattr(principal, "merchant_id", None)
    if mid is None or str(mid) != str(merchant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def _to_response(account: MerchantBankAccount, encryptor: FieldEncryptor) -> BankAccountResponse:
    try:
        last4 = encryptor.decrypt(account.account_number)[-4:]
    except Exception:
        last4 = "****"
    return BankAccountResponse(
        id=account.id,
        merchant_id=account.merchant_id,
        account_holder_name=account.account_holder_name,
        account_number_last4=last4,
        ifsc_code=account.ifsc_code,
        account_type=account.account_type,
        is_primary=account.is_primary,
        is_verified=account.is_verified,
        verified_at=account.verified_at,
        penny_drop_initiated_at=account.penny_drop_initiated_at,
        created_at=account.created_at,
    )


@router.post(
    "/merchants/{merchant_id}/bank-accounts",
    response_model=BankAccountResponse,
    status_code=201,
)
async def add_bank_account(
    merchant_id: uuid.UUID,
    body: BankAccountRequest,
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _check_access(merchant_id, principal)
    enc = request.app.state.encryptor
    acc_enc = enc.encrypt(body.account_number)
    acc_hash = FieldEncryptor.hash_field(body.account_number)

    acct = MerchantBankAccount(
        merchant_id=merchant_id,
        account_holder_name=body.account_holder_name,
        account_number=acc_enc,
        account_number_hash=acc_hash,
        ifsc_code=body.ifsc_code.upper(),
        account_type=body.account_type,
    )
    db.add(acct)
    await db.commit()
    await db.refresh(acct)
    log.info("bank_account.added", merchant_id=str(merchant_id), account_id=str(acct.id))
    return _to_response(acct, enc)


@router.get(
    "/merchants/{merchant_id}/bank-accounts",
    response_model=list[BankAccountResponse],
)
async def list_bank_accounts(
    merchant_id: uuid.UUID,
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _check_access(merchant_id, principal)
    rows = (
        await db.execute(
            select(MerchantBankAccount).where(
                MerchantBankAccount.merchant_id == merchant_id,
                MerchantBankAccount.is_deleted.is_(False),
            )
        )
    ).scalars().all()
    enc = request.app.state.encryptor
    return [_to_response(r, enc) for r in rows]


@router.post(
    "/merchants/{merchant_id}/bank-accounts/{ba_id}/penny-drop",
    response_model=PennyDropResponse,
)
async def start_penny_drop(
    merchant_id: uuid.UUID,
    ba_id: uuid.UUID,
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _check_access(merchant_id, principal)
    state = request.app.state
    result = await initiate_penny_drop(
        bank_account_id=ba_id,
        db=db,
        encryptor=state.encryptor,
        razorpay_key_id=getattr(state.settings, "RAZORPAY_KEY_ID", ""),
        razorpay_key_secret=getattr(state.settings, "RAZORPAY_KEY_SECRET", ""),
        environment=state.settings.ENVIRONMENT,
    )
    return PennyDropResponse(**result)


@router.post(
    "/merchants/{merchant_id}/bank-accounts/{ba_id}/verify",
    response_model=PennyDropVerifyResponse,
)
async def verify_bank_account(
    merchant_id: uuid.UUID,
    ba_id: uuid.UUID,
    body: PennyDropVerifyRequest,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _check_access(merchant_id, principal)
    result = await verify_penny_drop(
        bank_account_id=ba_id,
        stated_amount_paise=body.stated_amount_paise,
        db=db,
    )
    return PennyDropVerifyResponse(**result)
