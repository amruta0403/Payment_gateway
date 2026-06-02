from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db_session, get_principal
from schemas.merchant import ApiKeyCreateRequest, ApiKeyCreateResponse, ApiKeyListItem
from services.api_key_service import create_api_key, list_api_keys, revoke_api_key

log = structlog.get_logger()
router = APIRouter(prefix="/merchants", tags=["api-keys"])


def _check_access(merchant_id: uuid.UUID, principal) -> None:
    roles = getattr(principal, "roles", [])
    if "ADMIN" in roles:
        return
    mid = getattr(principal, "merchant_id", None)
    if mid is None or str(mid) != str(merchant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@router.post(
    "/{merchant_id}/api-keys",
    response_model=ApiKeyCreateResponse,
    status_code=201,
)
async def create_merchant_api_key(
    merchant_id: uuid.UUID,
    body: ApiKeyCreateRequest,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _check_access(merchant_id, principal)
    return await create_api_key(merchant_id=merchant_id, request=body, db=db)


@router.get("/{merchant_id}/api-keys", response_model=list[ApiKeyListItem])
async def list_merchant_api_keys(
    merchant_id: uuid.UUID,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _check_access(merchant_id, principal)
    return await list_api_keys(merchant_id=merchant_id, db=db)


@router.delete(
    "/{merchant_id}/api-keys/{key_id}",
    status_code=204,
)
async def revoke_merchant_api_key(
    merchant_id: uuid.UUID,
    key_id: uuid.UUID,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _check_access(merchant_id, principal)
    await revoke_api_key(key_id=key_id, merchant_id=merchant_id, db=db)
