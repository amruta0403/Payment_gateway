"""Aggregated dashboard stats — combines data from multiple services."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import httpx
import structlog
from fastapi import APIRouter, Header, HTTPException

from client import proxy_get
from config import settings

log = structlog.get_logger()
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_dashboard_stats(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")

    # Fetch from multiple services concurrently
    results = await asyncio.gather(
        _safe_get(settings.PAYMENT_SERVICE_URL,    "/v1/payments?page_size=5&page=1", token),
        _safe_get(settings.TRANSACTION_SERVICE_URL, "/v1/transactions/stats?period=today", token),
        _safe_get(settings.TRANSACTION_SERVICE_URL, "/v1/transactions/stats?period=7d", token),
        _safe_get(settings.SETTLEMENT_SERVICE_URL,  "/v1/settlements?page_size=1", token),
        return_exceptions=True,
    )

    recent_payments = results[0] if not isinstance(results[0], Exception) else {"items": []}
    today_stats     = results[1] if not isinstance(results[1], Exception) else {}
    week_stats      = results[2] if not isinstance(results[2], Exception) else {}
    settlements     = results[3] if not isinstance(results[3], Exception) else {"items": []}

    return {
        "today": {
            "transaction_count":   today_stats.get("total_count", 0),
            "success_count":       today_stats.get("success_count", 0),
            "failed_count":        today_stats.get("failed_count", 0),
            "volume_paise":        today_stats.get("total_amount_paise", 0),
            "success_rate_pct":    today_stats.get("success_rate_pct", 0),
            "avg_ticket_paise":    today_stats.get("avg_ticket_paise", 0),
            "by_method":           today_stats.get("by_method", {}),
        },
        "week": {
            "transaction_count":   week_stats.get("total_count", 0),
            "volume_paise":        week_stats.get("total_amount_paise", 0),
            "success_rate_pct":    week_stats.get("success_rate_pct", 0),
            "by_method":           week_stats.get("by_method", {}),
            "by_status":           week_stats.get("by_status", {}),
        },
        "recent_transactions": recent_payments.get("items", [])[:5],
        "pending_settlements": len([
            s for s in settlements.get("items", [])
            if s.get("status") in ("PENDING", "PROCESSING")
        ]),
    }


@router.get("/volume")
async def get_volume_chart(
    days: int = 30,
    authorization: str = Header(...),
):
    token = authorization.replace("Bearer ", "")
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days)

    try:
        data = await proxy_get(
            settings.REPORTING_SERVICE_URL,
            "/v1/reports/daily",
            token,
            params={"start_date": str(start_date), "end_date": str(end_date)},
        )
        return data
    except Exception as exc:
        log.warning("volume_chart.failed", error=str(exc))
        return {"data": [], "start_date": str(start_date), "end_date": str(end_date)}


async def _safe_get(base_url: str, path: str, token: str) -> dict:
    try:
        return await proxy_get(base_url, path, token)
    except httpx.HTTPStatusError as e:
        log.warning("dashboard.service_error", url=f"{base_url}{path}", status=e.response.status_code)
        return {}
    except Exception as e:
        log.warning("dashboard.service_unreachable", url=f"{base_url}{path}", error=str(e))
        return {}
