from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dependencies import get_db_session, get_principal
from models.settlement_batch import SettlementBatch, SettlementStatus
from models.settlement_payout import PayoutStatus, SettlementPayout
from models.settlement_transaction import SettlementTransaction
from schemas.settlement import (
    MonthlySummaryItem,
    RbiReportRow,
    SettlementBatchDetail,
    SettlementBatchResponse,
    TriggerSettlementRequest,
)

log = structlog.get_logger()
router = APIRouter(tags=["settlements"])


def _require_role(principal, *roles: str) -> None:
    proles = getattr(principal, "roles", [])
    if not any(r in proles for r in roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")


def _merchant_id(principal) -> uuid.UUID | None:
    mid = getattr(principal, "merchant_id", None)
    return uuid.UUID(str(mid)) if mid else None


# ── GET /settlements ──────────────────────────────────────────────────────────

@router.get("/settlements", response_model=list[SettlementBatchResponse])
async def list_settlements(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    status_filter: Optional[SettlementStatus] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    mid = _merchant_id(principal)
    roles = getattr(principal, "roles", [])
    is_admin = "ADMIN" in roles or "FINANCE_OPS" in roles

    q = select(SettlementBatch).order_by(SettlementBatch.settlement_date.desc())

    if not is_admin:
        if not mid:
            return []
        q = q.where(SettlementBatch.merchant_id == mid)

    if start_date:
        q = q.where(SettlementBatch.settlement_date >= start_date)
    if end_date:
        q = q.where(SettlementBatch.settlement_date <= end_date)
    if status_filter:
        q = q.where(SettlementBatch.status == status_filter)

    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()
    return [SettlementBatchResponse.model_validate(r) for r in rows]


# ── GET /settlements/summary ──────────────────────────────────────────────────

@router.get("/settlements/summary", response_model=list[MonthlySummaryItem])
async def monthly_summary(
    year: int = Query(..., ge=2020, le=2099),
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    mid = _merchant_id(principal)
    roles = getattr(principal, "roles", [])
    is_admin = "ADMIN" in roles or "FINANCE_OPS" in roles

    q = (
        select(
            func.to_char(SettlementBatch.settlement_date, "YYYY-MM").label("month"),
            func.count(SettlementBatch.id).label("batch_count"),
            func.sum(SettlementBatch.gross_amount).label("total_gross"),
            func.sum(SettlementBatch.fee_amount).label("total_fee"),
            func.sum(SettlementBatch.gst_on_fee).label("total_gst"),
            func.sum(SettlementBatch.net_amount).label("total_net"),
            func.sum(SettlementBatch.transaction_count).label("transaction_count"),
        )
        .where(func.extract("year", SettlementBatch.settlement_date) == year)
        .group_by("month")
        .order_by("month")
    )

    if not is_admin and mid:
        q = q.where(SettlementBatch.merchant_id == mid)

    rows = (await db.execute(q)).all()
    return [
        MonthlySummaryItem(
            month=r.month,
            batch_count=r.batch_count,
            total_gross=r.total_gross or 0,
            total_fee=r.total_fee or 0,
            total_gst=r.total_gst or 0,
            total_net=r.total_net or 0,
            transaction_count=r.transaction_count or 0,
        )
        for r in rows
    ]


# ── GET /settlements/{id} ─────────────────────────────────────────────────────

@router.get("/settlements/{batch_id}", response_model=SettlementBatchDetail)
async def get_settlement(
    batch_id: uuid.UUID,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    q = (
        select(SettlementBatch)
        .where(SettlementBatch.id == batch_id)
        .options(
            selectinload(SettlementBatch.settlement_transactions),
            selectinload(SettlementBatch.payouts),
        )
    )
    batch = (await db.execute(q)).scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Settlement batch not found")

    mid = _merchant_id(principal)
    roles = getattr(principal, "roles", [])
    if "ADMIN" not in roles and "FINANCE_OPS" not in roles:
        if mid != batch.merchant_id:
            raise HTTPException(status_code=403, detail="Access denied")

    return SettlementBatchDetail(
        **SettlementBatchResponse.model_validate(batch).model_dump(),
        transactions=[
            {"id": t.id, "batch_id": t.batch_id, "transaction_id": t.transaction_id,
             "amount": t.amount, "fee": t.fee, "gst": t.gst, "net": t.net}
            for t in batch.settlement_transactions
        ],
        payouts=[
            {"id": p.id, "batch_id": p.batch_id, "amount": p.amount,
             "payout_method": p.payout_method, "status": p.status,
             "utr_number": p.utr_number, "failure_reason": p.failure_reason,
             "initiated_at": p.initiated_at, "completed_at": p.completed_at}
            for p in batch.payouts
        ],
    )


# ── POST /admin/settlements/trigger ───────────────────────────────────────────

@router.post("/admin/settlements/trigger", status_code=202)
async def trigger_settlement(
    body: TriggerSettlementRequest,
    principal=Depends(get_principal),
):
    _require_role(principal, "ADMIN", "FINANCE_OPS")
    from tasks.settlement import create_daily_batch
    create_daily_batch.delay(str(body.settlement_date))
    log.info("settlement.manual_trigger", date=str(body.settlement_date))
    return {"status": "queued", "settlement_date": str(body.settlement_date)}


# ── POST /admin/settlements/{id}/retry-payout ─────────────────────────────────

@router.post("/admin/settlements/{batch_id}/retry-payout", status_code=202)
async def retry_payout(
    batch_id: uuid.UUID,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _require_role(principal, "ADMIN", "FINANCE_OPS")

    batch = await db.get(SettlementBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.status not in (SettlementStatus.FAILED, SettlementStatus.PENDING):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry batch in status {batch.status.value}",
        )

    from tasks.settlement import initiate_payout
    initiate_payout.delay(str(batch_id))
    return {"status": "queued", "batch_id": str(batch_id)}


# ── GET /admin/reports/rbi ────────────────────────────────────────────────────

@router.get("/admin/reports/rbi")
async def rbi_report(
    start_date: date = Query(...),
    end_date: date = Query(...),
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _require_role(principal, "ADMIN", "COMPLIANCE_OFFICER", "FINANCE_OPS")

    batches = (
        await db.execute(
            select(SettlementBatch)
            .where(
                SettlementBatch.settlement_date >= start_date,
                SettlementBatch.settlement_date <= end_date,
            )
            .options(selectinload(SettlementBatch.payouts))
            .order_by(SettlementBatch.settlement_date, SettlementBatch.merchant_id)
        )
    ).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Batch ID", "Merchant ID", "Settlement Date",
        "Gross Amount (paise)", "Fee (paise)", "GST (paise)", "Net Amount (paise)",
        "Transaction Count", "UTR Number", "Status",
    ])

    for b in batches:
        utr = next(
            (p.utr_number for p in b.payouts if p.status == PayoutStatus.SUCCESS),
            "",
        )
        writer.writerow([
            str(b.id), str(b.merchant_id), str(b.settlement_date),
            b.gross_amount, b.fee_amount, b.gst_on_fee, b.net_amount,
            b.transaction_count, utr or "", b.status.value,
        ])

    buf.seek(0)
    filename = f"rbi_settlement_{start_date}_{end_date}.csv"
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
