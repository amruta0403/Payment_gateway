from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db_session, get_principal
from models.notification_log import NotificationChannel, NotificationLog, NotificationStatus
from schemas.notification import NotificationLogResponse

log = structlog.get_logger()
router = APIRouter(prefix="/notifications", tags=["notifications"])


def _require_admin(principal) -> None:
    from fastapi import HTTPException
    if "ADMIN" not in getattr(principal, "roles", []):
        raise HTTPException(403, "Admin role required")


@router.get("", response_model=list[NotificationLogResponse])
async def list_notification_logs(
    merchant_id: uuid.UUID | None = Query(None),
    status: NotificationStatus | None = Query(None),
    channel: NotificationChannel | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _require_admin(principal)
    q = select(NotificationLog).order_by(NotificationLog.created_at.desc())
    if merchant_id:
        q = q.where(NotificationLog.merchant_id == merchant_id)
    if status:
        q = q.where(NotificationLog.status == status)
    if channel:
        q = q.where(NotificationLog.channel == channel)
    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()
    return [NotificationLogResponse.model_validate(r) for r in rows]


@router.get("/{notification_id}", response_model=NotificationLogResponse)
async def get_notification_log(
    notification_id: uuid.UUID,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _require_admin(principal)
    from fastapi import HTTPException
    row = await db.get(NotificationLog, notification_id)
    if not row:
        raise HTTPException(404, "Notification log not found")
    return NotificationLogResponse.model_validate(row)
