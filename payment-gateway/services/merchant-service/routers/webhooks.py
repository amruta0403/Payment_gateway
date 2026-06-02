from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db_session, get_principal
from schemas.merchant import WebhookCreateRequest, WebhookCreateResponse, WebhookListItem
from services.webhook_service import (
    create_webhook,
    delete_webhook,
    list_webhooks,
    send_test_webhook,
)

log = structlog.get_logger()
router = APIRouter(prefix="/merchants", tags=["webhooks"])


def _check_access(merchant_id: uuid.UUID, principal) -> None:
    roles = getattr(principal, "roles", [])
    if "ADMIN" in roles:
        return
    mid = getattr(principal, "merchant_id", None)
    if mid is None or str(mid) != str(merchant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@router.post(
    "/{merchant_id}/webhooks",
    response_model=WebhookCreateResponse,
    status_code=201,
)
async def register_webhook(
    merchant_id: uuid.UUID,
    body: WebhookCreateRequest,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _check_access(merchant_id, principal)
    return await create_webhook(merchant_id=merchant_id, request=body, db=db)


@router.get("/{merchant_id}/webhooks", response_model=list[WebhookListItem])
async def list_merchant_webhooks(
    merchant_id: uuid.UUID,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _check_access(merchant_id, principal)
    return await list_webhooks(merchant_id=merchant_id, db=db)


@router.delete("/{merchant_id}/webhooks/{webhook_id}", status_code=204)
async def remove_webhook(
    merchant_id: uuid.UUID,
    webhook_id: uuid.UUID,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _check_access(merchant_id, principal)
    await delete_webhook(webhook_id=webhook_id, merchant_id=merchant_id, db=db)


@router.post("/{merchant_id}/webhooks/{webhook_id}/test")
async def test_webhook(
    merchant_id: uuid.UUID,
    webhook_id: uuid.UUID,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _check_access(merchant_id, principal)
    result = await send_test_webhook(
        webhook_id=webhook_id,
        merchant_id=merchant_id,
        db=db,
    )
    return result
