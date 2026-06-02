from __future__ import annotations

import base64
import csv
import io
import uuid
from datetime import date, datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db_session, get_principal
from models.audit_log import AuditLog
from schemas.audit import AuditLogPage, AuditLogResponse, KongAccessLog
from services.sanitizer import sanitise_for_audit

log = structlog.get_logger()
router = APIRouter(tags=["audit"])

_MAX_EXPORT_DAYS = 31


def _require_compliance(principal) -> None:
    roles = getattr(principal, "roles", [])
    if not any(r in roles for r in ("ADMIN", "COMPLIANCE_OFFICER", "SUPER_ADMIN")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Compliance role required")


def _encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts_str, id_str = raw.split("|", 1)
    return datetime.fromisoformat(ts_str), uuid.UUID(id_str)


# ── GET /audit/logs ───────────────────────────────────────────────────────────

@router.get("/audit/logs", response_model=AuditLogPage)
async def list_audit_logs(
    cursor: Optional[str] = Query(None, description="Opaque pagination cursor"),
    limit: int = Query(50, ge=1, le=200),
    service: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[uuid.UUID] = Query(None),
    merchant_id: Optional[uuid.UUID] = Query(None),
    action: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _require_compliance(principal)

    q = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())

    if cursor:
        try:
            cur_ts, cur_id = _decode_cursor(cursor)
            q = q.where(
                (AuditLog.created_at < cur_ts)
                | ((AuditLog.created_at == cur_ts) & (AuditLog.id < cur_id))
            )
        except Exception:
            raise HTTPException(400, "Invalid cursor")

    if service:
        q = q.where(AuditLog.service == service)
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    if merchant_id:
        q = q.where(AuditLog.merchant_id == merchant_id)
    if action:
        q = q.where(AuditLog.action.ilike(f"%{action}%"))
    if start_date:
        q = q.where(AuditLog.created_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        from datetime import timedelta
        q = q.where(AuditLog.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time()))

    q = q.limit(limit + 1)
    rows = (await db.execute(q)).scalars().all()

    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = _encode_cursor(items[-1].created_at, items[-1].id) if has_more and items else None

    return AuditLogPage(
        items=[AuditLogResponse.model_validate(r) for r in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )


# ── GET /audit/logs/export ────────────────────────────────────────────────────

@router.get("/audit/logs/export")
async def export_audit_logs(
    start_date: date = Query(...),
    end_date: date = Query(...),
    service: Optional[str] = Query(None),
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _require_compliance(principal)

    if (end_date - start_date).days > _MAX_EXPORT_DAYS:
        raise HTTPException(400, f"Max {_MAX_EXPORT_DAYS}-day range for export")

    from datetime import timedelta
    q = (
        select(AuditLog)
        .where(
            AuditLog.created_at >= datetime.combine(start_date, datetime.min.time()),
            AuditLog.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time()),
        )
        .order_by(AuditLog.created_at)
    )
    if service:
        q = q.where(AuditLog.service == service)

    rows = (await db.execute(q)).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "created_at", "service", "entity_type", "entity_id",
        "action", "actor_id", "merchant_id", "kafka_topic",
    ])
    for r in rows:
        writer.writerow([
            str(r.id), r.created_at.isoformat(), r.service, r.entity_type,
            str(r.entity_id or ""), r.action, str(r.actor_id or ""),
            str(r.merchant_id or ""), r.kafka_topic or "",
        ])
    buf.seek(0)

    filename = f"audit_{start_date}_{end_date}.csv"
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── POST /internal/kong-access-log ───────────────────────────────────────────

@router.post("/internal/kong-access-log", status_code=202)
async def ingest_kong_access_log(
    body: KongAccessLog,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """HTTP access log ingestion from Kong or Traefik plugin — no auth required."""
    clean = sanitise_for_audit(body.model_dump())
    entry = AuditLog(
        service=body.service or "gateway",
        entity_type="http_request",
        action=f"{body.method} {body.status_code}",
        metadata_={
            "path": body.path,
            "latency_ms": body.latency_ms,
            "status_code": body.status_code,
            "client_ip": body.client_ip,
        },
        kafka_topic="http_access_log",
    )
    db.add(entry)
    await db.commit()
    return {"accepted": True}
