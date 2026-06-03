from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db_session, get_principal
from models.transaction_ref import Transaction
from schemas.transaction import (
    DailyVolume,
    TransactionListResponse,
    TransactionResponse,
    TransactionStats,
)

log = structlog.get_logger()
router = APIRouter(prefix="/transactions", tags=["transactions"])


def _merchant_id(principal) -> uuid.UUID | None:
    mid = getattr(principal, "merchant_id", None)
    if mid:
        return uuid.UUID(str(mid)) if not isinstance(mid, uuid.UUID) else mid
    return None


def _is_admin(principal) -> bool:
    return any(r in getattr(principal, "roles", []) for r in ("ADMIN", "FINANCE_OPS", "COMPLIANCE_OFFICER"))


@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status_filter: Optional[str] = Query(None, alias="status"),
    payment_method: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    order_id: Optional[str] = Query(None),
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    mid = _merchant_id(principal)

    q = select(Transaction).where(Transaction.is_deleted.is_(False))
    count_q = select(func.count(Transaction.id)).where(Transaction.is_deleted.is_(False))

    if not _is_admin(principal):
        if not mid:
            raise HTTPException(403, "No merchant_id in token")
        q = q.where(Transaction.merchant_id == mid)
        count_q = count_q.where(Transaction.merchant_id == mid)

    if status_filter:
        q = q.where(Transaction.status == status_filter)
        count_q = count_q.where(Transaction.status == status_filter)
    if payment_method:
        q = q.where(Transaction.payment_method == payment_method.upper())
        count_q = count_q.where(Transaction.payment_method == payment_method.upper())
    if order_id:
        q = q.where(Transaction.order_id == order_id)
        count_q = count_q.where(Transaction.order_id == order_id)
    if start_date:
        q = q.where(Transaction.created_at >= datetime.combine(start_date, datetime.min.time()))
        count_q = count_q.where(Transaction.created_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        end = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        q = q.where(Transaction.created_at < end)
        count_q = count_q.where(Transaction.created_at < end)

    total = (await db.execute(count_q)).scalar_one()
    q = q.order_by(Transaction.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    return TransactionListResponse(
        items=[TransactionResponse.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


@router.get("/stats", response_model=TransactionStats)
async def transaction_stats(
    period: str = Query("today", pattern="^(today|7d|30d)$"),
    merchant_id_param: Optional[uuid.UUID] = Query(None, alias="merchant_id"),
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    mid = merchant_id_param or _merchant_id(principal)
    if not mid and not _is_admin(principal):
        raise HTTPException(403, "merchant_id required")

    cutoff = {
        "today": datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
        "7d": datetime.utcnow() - timedelta(days=7),
        "30d": datetime.utcnow() - timedelta(days=30),
    }[period]

    q = select(Transaction).where(
        Transaction.is_deleted.is_(False),
        Transaction.created_at >= cutoff,
    )
    if mid:
        q = q.where(Transaction.merchant_id == mid)

    rows = (await db.execute(q)).scalars().all()
    total = len(rows)
    success = sum(1 for r in rows if r.status in ("CAPTURED", "SETTLED"))
    failed = sum(1 for r in rows if r.status in ("FAILED", "CANCELLED"))
    total_amt = sum(r.amount for r in rows)
    captured_amt = sum(r.captured_amount or 0 for r in rows)
    refunded_amt = sum(r.refunded_amount for r in rows)

    by_method: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for r in rows:
        by_method[r.payment_method] = by_method.get(r.payment_method, 0) + 1
        by_status[r.status] = by_status.get(r.status, 0) + 1

    return TransactionStats(
        merchant_id=mid or uuid.UUID(int=0),
        period=period,
        total_count=total,
        success_count=success,
        failed_count=failed,
        total_amount_paise=total_amt,
        captured_amount_paise=captured_amt,
        refunded_amount_paise=refunded_amt,
        success_rate_pct=round(success / total * 100, 2) if total else 0.0,
        avg_ticket_paise=total_amt // total if total else 0,
        by_method=by_method,
        by_status=by_status,
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: uuid.UUID,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    txn = await db.get(Transaction, transaction_id)
    if not txn or txn.is_deleted:
        raise HTTPException(404, "Transaction not found")

    if not _is_admin(principal):
        mid = _merchant_id(principal)
        if not mid or txn.merchant_id != mid:
            raise HTTPException(403, "Access denied")

    return TransactionResponse.model_validate(txn)
