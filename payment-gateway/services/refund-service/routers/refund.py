from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db_session, get_principal
from schemas.refund import RefundCreateRequest, RefundListResponse, RefundResponse
from services.refund_service import create_refund, get_refund, list_refunds_for_payment

log = structlog.get_logger()
router = APIRouter(tags=["refunds"])


def _merchant_id(principal) -> uuid.UUID:
    mid = getattr(principal, "merchant_id", None)
    if not mid:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No merchant_id in token")
    return uuid.UUID(str(mid)) if not isinstance(mid, uuid.UUID) else mid


@router.post("/refunds", response_model=RefundResponse, status_code=201)
async def initiate_refund(
    body: RefundCreateRequest,
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    merchant_id = _merchant_id(principal)
    initiated_by_str = getattr(principal, "sub", None)
    initiated_by = uuid.UUID(initiated_by_str) if initiated_by_str else None

    return await create_refund(
        request=body,
        merchant_id=merchant_id,
        initiated_by=initiated_by,
        db=db,
        settings=request.app.state.settings,
        kafka_producer=getattr(request.app.state, "kafka_producer", None),
    )


@router.get("/refunds/{refund_id}", response_model=RefundResponse)
async def get_refund_by_id(
    refund_id: uuid.UUID,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    merchant_id = _merchant_id(principal)
    return await get_refund(refund_id=refund_id, merchant_id=merchant_id, db=db)


@router.get("/payments/{payment_id}/refunds", response_model=list[RefundResponse])
async def list_payment_refunds(
    payment_id: uuid.UUID,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    merchant_id = _merchant_id(principal)
    return await list_refunds_for_payment(
        transaction_id=payment_id,
        merchant_id=merchant_id,
        db=db,
    )
