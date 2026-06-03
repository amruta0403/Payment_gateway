from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db_session, get_principal

log = structlog.get_logger()
router = APIRouter(prefix="/reports", tags=["reports"])

_MAX_EXPORT_DAYS = 92   # 3 months


def _require_role(principal, *roles: str) -> None:
    r = getattr(principal, "roles", [])
    if not any(x in r for x in roles):
        raise HTTPException(403, "Insufficient role")


def _merchant_id(principal) -> uuid.UUID | None:
    mid = getattr(principal, "merchant_id", None)
    return uuid.UUID(str(mid)) if mid else None


def _is_admin(principal) -> bool:
    return any(x in getattr(principal, "roles", []) for x in ("ADMIN", "FINANCE_OPS"))


@router.get("/dashboard")
async def merchant_dashboard(
    merchant_id: Optional[uuid.UUID] = Query(None),
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    """Real-time merchant dashboard — last 24h metrics."""
    mid = merchant_id or _merchant_id(principal)
    if not mid:
        raise HTTPException(400, "merchant_id required")
    if not _is_admin(principal) and _merchant_id(principal) != mid:
        raise HTTPException(403, "Access denied")

    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)

    result = await db.execute(
        text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status IN ('CAPTURED','SETTLED') THEN 1 ELSE 0 END) AS success,
                SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS failed,
                COALESCE(SUM(amount), 0) AS gross_paise,
                COALESCE(SUM(CASE WHEN status IN ('CAPTURED','SETTLED') THEN captured_amount ELSE 0 END), 0) AS captured_paise
            FROM transactions
            WHERE merchant_id = :mid
              AND created_at >= :since
              AND is_deleted = false
        """),
        {"mid": str(mid), "since": day_ago},
    )
    row = result.fetchone()

    total = row.total or 0
    success = row.success or 0

    return {
        "merchant_id": str(mid),
        "period": "24h",
        "total_transactions": total,
        "successful": success,
        "failed": row.failed or 0,
        "success_rate_pct": round(success / total * 100, 2) if total else 0.0,
        "gross_volume_paise": row.gross_paise or 0,
        "captured_volume_paise": row.captured_paise or 0,
        "gross_volume_rupees": round((row.gross_paise or 0) / 100, 2),
    }


@router.get("/daily")
async def daily_summary(
    start_date: date = Query(...),
    end_date: date = Query(...),
    merchant_id: Optional[uuid.UUID] = Query(None),
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    """Day-by-day transaction summary."""
    if (end_date - start_date).days > _MAX_EXPORT_DAYS:
        raise HTTPException(400, f"Max {_MAX_EXPORT_DAYS}-day range")

    mid = merchant_id or _merchant_id(principal)
    if not mid and not _is_admin(principal):
        raise HTTPException(400, "merchant_id required")

    result = await db.execute(
        text("""
            SELECT
                DATE(created_at) as day,
                COUNT(*) as count,
                SUM(CASE WHEN status IN ('CAPTURED','SETTLED') THEN 1 ELSE 0 END) as success,
                COALESCE(SUM(amount), 0) as gross,
                payment_method
            FROM transactions
            WHERE (:mid IS NULL OR merchant_id = :mid::uuid)
              AND DATE(created_at) BETWEEN :start AND :end
              AND is_deleted = false
            GROUP BY day, payment_method
            ORDER BY day DESC, payment_method
        """),
        {
            "mid": str(mid) if mid else None,
            "start": start_date,
            "end": end_date,
        },
    )
    rows = result.fetchall()

    # Group by date
    by_day: dict = {}
    for r in rows:
        d = str(r.day)
        if d not in by_day:
            by_day[d] = {"date": d, "total_count": 0, "success_count": 0, "gross_paise": 0, "by_method": {}}
        by_day[d]["total_count"] += r.count
        by_day[d]["success_count"] += r.success
        by_day[d]["gross_paise"] += r.gross
        by_day[d]["by_method"][r.payment_method] = r.count

    return {"data": list(by_day.values()), "start_date": str(start_date), "end_date": str(end_date)}


@router.get("/settlements")
async def settlements_report(
    start_date: date = Query(...),
    end_date: date = Query(...),
    merchant_id: Optional[uuid.UUID] = Query(None),
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _require_role(principal, "ADMIN", "FINANCE_OPS", "MERCHANT_OWNER")
    mid = merchant_id or _merchant_id(principal)

    result = await db.execute(
        text("""
            SELECT
                sb.id, sb.merchant_id, sb.settlement_date,
                sb.gross_amount, sb.fee_amount, sb.gst_on_fee, sb.net_amount,
                sb.transaction_count, sb.status,
                sp.utr_number, sp.payout_method,
                sp.status as payout_status
            FROM settlement_batches sb
            LEFT JOIN settlement_payouts sp ON sp.batch_id = sb.id
            WHERE (:mid IS NULL OR sb.merchant_id = :mid::uuid)
              AND sb.settlement_date BETWEEN :start AND :end
            ORDER BY sb.settlement_date DESC
        """),
        {"mid": str(mid) if mid else None, "start": start_date, "end": end_date},
    )
    rows = result.fetchall()
    return {
        "data": [dict(r._mapping) for r in rows],
        "start_date": str(start_date),
        "end_date": str(end_date),
        "total_net_paise": sum(r.net_amount for r in rows),
    }


@router.get("/export")
async def export_transactions(
    start_date: date = Query(...),
    end_date: date = Query(...),
    merchant_id: Optional[uuid.UUID] = Query(None),
    format_: str = Query("csv", alias="format", pattern="^(csv)$"),
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    """Download transaction CSV — max 92 days."""
    if (end_date - start_date).days > _MAX_EXPORT_DAYS:
        raise HTTPException(400, f"Max {_MAX_EXPORT_DAYS}-day range for export")

    mid = merchant_id or _merchant_id(principal)
    end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time())

    result = await db.execute(
        text("""
            SELECT id, merchant_id, amount, currency, status, payment_method,
                   card_last4, card_network, upi_vpa, bank_code, gateway_txn_id,
                   rrn, order_id, description, error_code, captured_at, created_at
            FROM transactions
            WHERE (:mid IS NULL OR merchant_id = :mid::uuid)
              AND created_at >= :start
              AND created_at < :end
              AND is_deleted = false
            ORDER BY created_at
        """),
        {
            "mid": str(mid) if mid else None,
            "start": datetime.combine(start_date, datetime.min.time()),
            "end": end_dt,
        },
    )
    rows = result.fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Transaction ID", "Merchant ID", "Amount (paise)", "Currency", "Status",
        "Payment Method", "Card Last4", "Card Network", "UPI VPA", "Bank Code",
        "Gateway TxnID", "RRN", "Order ID", "Description", "Error Code",
        "Captured At", "Created At",
    ])
    for r in rows:
        writer.writerow([
            r.id, r.merchant_id, r.amount, r.currency, r.status,
            r.payment_method, r.card_last4 or "", r.card_network or "",
            r.upi_vpa or "", r.bank_code or "", r.gateway_txn_id or "",
            r.rrn or "", r.order_id or "", r.description or "",
            r.error_code or "", r.captured_at or "", r.created_at,
        ])

    buf.seek(0)
    fname = f"transactions_{start_date}_{end_date}.csv"
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/gst")
async def gst_report(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
    merchant_id: Optional[uuid.UUID] = Query(None),
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    """GST report — fee collected (18%) for a calendar month."""
    _require_role(principal, "ADMIN", "FINANCE_OPS", "COMPLIANCE_OFFICER", "MERCHANT_OWNER")
    mid = merchant_id or _merchant_id(principal)
    year, mon = map(int, month.split("-"))

    result = await db.execute(
        text("""
            SELECT
                sb.merchant_id,
                SUM(sb.fee_amount) AS total_fee,
                SUM(sb.gst_on_fee) AS total_gst,
                SUM(sb.gross_amount) AS total_gross,
                SUM(sb.net_amount) AS total_net,
                COUNT(*) AS batch_count
            FROM settlement_batches sb
            WHERE (:mid IS NULL OR sb.merchant_id = :mid::uuid)
              AND EXTRACT(YEAR FROM sb.settlement_date) = :year
              AND EXTRACT(MONTH FROM sb.settlement_date) = :mon
              AND sb.status IN ('COMPLETED', 'RECONCILED')
            GROUP BY sb.merchant_id
        """),
        {"mid": str(mid) if mid else None, "year": year, "mon": mon},
    )
    rows = result.fetchall()
    return {
        "month": month,
        "data": [dict(r._mapping) for r in rows],
    }
