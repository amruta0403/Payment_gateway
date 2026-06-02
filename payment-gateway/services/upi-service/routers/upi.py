from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db_session, get_principal
from models.upi_transaction import UpiTransaction
from schemas.upi import (
    CollectRequest,
    CollectResponse,
    IntentRequest,
    IntentResponse,
    MandateCreateRequest,
    MandateExecuteRequest,
    MandateResponse,
    UpiCallbackPayload,
    UpiStatusResponse,
    VpaValidateResponse,
)

log = structlog.get_logger()

# Main UPI router — included with /v1 prefix by main.py
router = APIRouter(prefix="/upi", tags=["upi"])

# Callback router — included WITHOUT /v1 prefix (NPCI-facing)
callback_router = APIRouter(tags=["upi-callback"])


def _upi_service(request: Request):
    return request.app.state.upi_service


# ── Collect ───────────────────────────────────────────────────────────────────

@router.post("/collect", response_model=CollectResponse, status_code=201)
async def initiate_collect(
    body: CollectRequest,
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    merchant_id = _merchant_id(principal)
    svc = _upi_service(request)
    return await svc.initiate_collect(
        payment_id=body.payment_id,
        request=body,
        merchant_id=merchant_id,
        db=db,
    )


# ── Intent ────────────────────────────────────────────────────────────────────

@router.post("/intent", response_model=IntentResponse, status_code=201)
async def generate_intent(
    body: IntentRequest,
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    merchant_id = _merchant_id(principal)
    svc = _upi_service(request)
    return await svc.generate_intent(
        payment_id=body.payment_id,
        request=body,
        merchant_id=merchant_id,
        db=db,
    )


# ── VPA validate ──────────────────────────────────────────────────────────────

@router.get("/vpa/{vpa}/validate", response_model=VpaValidateResponse)
async def validate_vpa(
    vpa: str,
    request: Request,
    principal=Depends(get_principal),
):
    svc = _upi_service(request)
    result = await svc.validate_vpa(vpa)
    return VpaValidateResponse(**result)


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/transaction/{payment_id}/status", response_model=UpiStatusResponse)
async def get_transaction_status(
    payment_id: uuid.UUID,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    txn = (
        await db.execute(
            select(UpiTransaction).where(
                UpiTransaction.transaction_id == payment_id
            ).order_by(UpiTransaction.initiated_at.desc())
        )
    ).scalars().first()

    if not txn:
        raise HTTPException(status_code=404, detail="UPI transaction not found")

    return UpiStatusResponse(
        our_ref_id=txn.our_ref_id,
        npci_txn_id=txn.npci_txn_id,
        status=txn.status,
        completed_at=txn.completed_at,
        decline_code=txn.decline_code,
        decline_reason=txn.decline_reason,
    )


# ── Mandates ──────────────────────────────────────────────────────────────────

@router.post("/mandates", response_model=MandateResponse, status_code=201)
async def create_mandate(
    body: MandateCreateRequest,
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    svc = _upi_service(request)
    return await svc.create_mandate(
        merchant_id=_merchant_id(principal),
        request=body,
        db=db,
    )


@router.get("/mandates/{mandate_id}", response_model=MandateResponse)
async def get_mandate(
    mandate_id: uuid.UUID,
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    svc = _upi_service(request)
    return await svc.get_mandate(mandate_id=mandate_id, db=db)


@router.post("/mandates/{mandate_id}/execute")
async def execute_mandate(
    mandate_id: uuid.UUID,
    body: MandateExecuteRequest,
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    svc = _upi_service(request)
    return await svc.execute_mandate(
        mandate_id=mandate_id,
        amount=body.amount,
        db=db,
    )


@router.delete("/mandates/{mandate_id}", status_code=204)
async def revoke_mandate(
    mandate_id: uuid.UUID,
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    svc = _upi_service(request)
    await svc.revoke_mandate(mandate_id=mandate_id, db=db)


# ── NPCI Callback — no /v1 prefix, HMAC-validated internally ─────────────────

@callback_router.post("/upi/callback")
async def npci_callback(
    body: UpiCallbackPayload,
    request: Request,
    x_upi_signature: str = Header(default=""),
    db: AsyncSession = Depends(get_db_session),
):
    raw_body = await request.body()
    svc = _upi_service(request)
    ok = await svc.handle_callback(
        payload=body,
        signature_header=x_upi_signature,
        raw_body=raw_body,
        db=db,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid callback signature")
    return {"status": "accepted"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _merchant_id(principal) -> uuid.UUID:
    mid = getattr(principal, "merchant_id", None)
    if mid is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No merchant_id in token",
        )
    return uuid.UUID(str(mid)) if not isinstance(mid, uuid.UUID) else mid
