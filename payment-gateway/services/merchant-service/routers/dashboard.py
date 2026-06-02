from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db_session, get_principal
from schemas.merchant import DailyVolume, DashboardResponse

log = structlog.get_logger()
router = APIRouter(prefix="/merchants", tags=["dashboard"])


def _check_access(merchant_id: uuid.UUID, principal) -> None:
    roles = getattr(principal, "roles", [])
    if "ADMIN" in roles:
        return
    mid = getattr(principal, "merchant_id", None)
    if mid is None or str(mid) != str(merchant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@router.get("/{merchant_id}/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    merchant_id: uuid.UUID,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _check_access(merchant_id, principal)
    mid = str(merchant_id)

    # ── Today's stats ──────────────────────────────────────────────────────────
    today_row = (
        await db.execute(
            text("""
                SELECT
                    COALESCE(SUM(amount_paise), 0)            AS vol,
                    COUNT(*)                                   AS cnt,
                    COALESCE(
                        SUM(CASE WHEN status IN ('CAPTURED','SETTLED') THEN 1 ELSE 0 END),
                        0
                    )                                          AS success_cnt
                FROM transactions
                WHERE merchant_id = :mid
                  AND DATE(created_at) = CURRENT_DATE
                  AND is_deleted = FALSE
            """),
            {"mid": mid},
        )
    ).fetchone()

    total_vol = int(today_row.vol or 0)
    total_cnt = int(today_row.cnt or 0)
    success_cnt = int(today_row.success_cnt or 0)
    success_rate = round((success_cnt / total_cnt * 100) if total_cnt else 0.0, 2)

    # ── Last 7 days breakdown ─────────────────────────────────────────────────
    daily_rows = (
        await db.execute(
            text("""
                SELECT
                    DATE(created_at)                           AS day,
                    COALESCE(SUM(amount_paise), 0)             AS volume_paise,
                    COUNT(*)                                   AS cnt
                FROM transactions
                WHERE merchant_id = :mid
                  AND created_at >= NOW() - INTERVAL '7 days'
                  AND is_deleted = FALSE
                GROUP BY day
                ORDER BY day DESC
            """),
            {"mid": mid},
        )
    ).fetchall()

    last_7 = [
        DailyVolume(
            date=str(r.day),
            volume_paise=int(r.volume_paise),
            count=int(r.cnt),
        )
        for r in daily_rows
    ]

    # ── Pending settlements ────────────────────────────────────────────────────
    pending_row = (
        await db.execute(
            text("""
                SELECT COALESCE(SUM(amount_paise), 0) AS pending
                FROM transactions
                WHERE merchant_id = :mid
                  AND status = 'CAPTURED'
                  AND settled_at IS NULL
                  AND is_deleted = FALSE
            """),
            {"mid": mid},
        )
    ).fetchone()
    pending = int(pending_row.pending or 0)

    # ── Last 5 transactions ────────────────────────────────────────────────────
    txn_rows = (
        await db.execute(
            text("""
                SELECT
                    id, amount_paise, currency, status,
                    payment_method, created_at, updated_at
                FROM transactions
                WHERE merchant_id = :mid
                  AND is_deleted = FALSE
                ORDER BY created_at DESC
                LIMIT 5
            """),
            {"mid": mid},
        )
    ).fetchall()

    last_5 = [
        {
            "id": str(r.id),
            "amount_paise": r.amount_paise,
            "currency": r.currency,
            "status": r.status,
            "payment_method": r.payment_method,
            "created_at": str(r.created_at),
        }
        for r in txn_rows
    ]

    return DashboardResponse(
        merchant_id=merchant_id,
        today_volume_paise=total_vol,
        today_count=total_cnt,
        today_success_rate_pct=success_rate,
        last_7_days=last_7,
        pending_settlements_paise=pending,
        last_5_transactions=last_5,
    )
