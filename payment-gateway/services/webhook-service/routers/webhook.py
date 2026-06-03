from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, HttpUrl, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db_session, get_principal
from models.webhook import WebhookDelivery, WebhookDeliveryStatus, WebhookEndpoint

log = structlog.get_logger()
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class EndpointCreate(BaseModel):
    url: HttpUrl
    events: list[str] = Field(..., min_length=1)

    @field_validator("url")
    @classmethod
    def must_https(cls, v):
        if not str(v).startswith("https://"):
            raise ValueError("Webhook URL must use HTTPS")
        return v


class EndpointResponse(BaseModel):
    id: uuid.UUID
    url: str
    events: list[str]
    is_active: bool
    failure_count: int
    created_at: datetime
    model_config = {"from_attributes": True}


class EndpointCreateResponse(EndpointResponse):
    webhook_secret: str = Field(..., description="Shown ONCE — store securely")
    warning: str = "This secret will not be shown again."


class DeliveryResponse(BaseModel):
    id: uuid.UUID
    endpoint_id: uuid.UUID
    event_type: str
    event_id: str
    status: str
    attempt_count: int
    response_status: int | None
    error_message: str | None
    duration_ms: int | None
    created_at: datetime
    delivered_at: datetime | None
    model_config = {"from_attributes": True}


def _merchant_id(principal) -> uuid.UUID:
    mid = getattr(principal, "merchant_id", None)
    if not mid:
        raise HTTPException(403, "No merchant_id in token")
    return uuid.UUID(str(mid)) if not isinstance(mid, uuid.UUID) else mid


@router.post("/endpoints", response_model=EndpointCreateResponse, status_code=201)
async def register_endpoint(
    body: EndpointCreate,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    mid = _merchant_id(principal)
    secret = secrets.token_hex(32)
    secret_hash = hashlib.sha256(secret.encode()).hexdigest()

    ep = WebhookEndpoint(
        merchant_id=mid,
        url=str(body.url),
        secret_hash=secret_hash,
        events=body.events,
        is_active=True,
    )
    db.add(ep)
    await db.commit()
    await db.refresh(ep)

    return EndpointCreateResponse(
        id=ep.id, url=ep.url, events=ep.events, is_active=ep.is_active,
        failure_count=ep.failure_count, created_at=ep.created_at,
        webhook_secret=secret,
    )


@router.get("/endpoints", response_model=list[EndpointResponse])
async def list_endpoints(
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    mid = _merchant_id(principal)
    rows = (
        await db.execute(
            select(WebhookEndpoint)
            .where(WebhookEndpoint.merchant_id == mid, WebhookEndpoint.is_active.is_(True))
            .order_by(WebhookEndpoint.created_at.desc())
        )
    ).scalars().all()
    return [EndpointResponse.model_validate(r) for r in rows]


@router.delete("/endpoints/{endpoint_id}", status_code=204)
async def delete_endpoint(
    endpoint_id: uuid.UUID,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    mid = _merchant_id(principal)
    ep = await db.get(WebhookEndpoint, endpoint_id)
    if not ep or ep.merchant_id != mid:
        raise HTTPException(404, "Endpoint not found")
    ep.is_active = False
    await db.commit()


@router.get("/deliveries", response_model=list[DeliveryResponse])
async def list_deliveries(
    endpoint_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 50,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    mid = _merchant_id(principal)
    q = select(WebhookDelivery).where(WebhookDelivery.merchant_id == mid)
    if endpoint_id:
        q = q.where(WebhookDelivery.endpoint_id == endpoint_id)
    q = q.order_by(WebhookDelivery.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()
    return [DeliveryResponse.model_validate(r) for r in rows]


@router.post("/endpoints/{endpoint_id}/test")
async def test_endpoint(
    endpoint_id: uuid.UUID,
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    mid = _merchant_id(principal)
    ep = await db.get(WebhookEndpoint, endpoint_id)
    if not ep or ep.merchant_id != mid:
        raise HTTPException(404, "Endpoint not found")

    delivery = WebhookDelivery(
        endpoint_id=ep.id,
        merchant_id=mid,
        event_type="test",
        event_id=str(uuid.uuid4()),
        payload={"event": "test", "message": "Webhook test from Payment Gateway"},
        status=WebhookDeliveryStatus.PENDING,
    )
    db.add(delivery)
    await db.flush()

    from services.webhook_delivery import deliver_now
    success = await deliver_now(delivery, ep, db)
    return {"status": "delivered" if success else "failed", "delivery_id": str(delivery.id)}
