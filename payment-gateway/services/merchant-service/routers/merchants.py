from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db_session, get_principal
from models.merchant import Merchant
from schemas.merchant import (
    MerchantRegisterRequest,
    MerchantResponse,
    MerchantUpdateRequest,
    OnboardingChecklist,
)
from services.merchant_service import (
    _merchant_to_response,
    build_checklist,
    create_merchant,
)

log = structlog.get_logger()
router = APIRouter(prefix="/merchants", tags=["merchants"])


def _check_access(merchant_id: uuid.UUID, principal) -> None:
    roles = getattr(principal, "roles", [])
    if "ADMIN" in roles or "COMPLIANCE_OFFICER" in roles:
        return
    mid = getattr(principal, "merchant_id", None)
    if mid is None or str(mid) != str(merchant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@router.post("/register", response_model=MerchantResponse, status_code=201)
async def register_merchant(
    body: MerchantRegisterRequest,
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    state = request.app.state
    return await create_merchant(
        request=body,
        registering_user_id=str(getattr(principal, "sub", "unknown")),
        db=db,
        encryptor=state.encryptor,
        keycloak_url=state.settings.KEYCLOAK_URL,
        keycloak_realm=state.settings.KEYCLOAK_REALM,
        keycloak_admin_token=getattr(state, "keycloak_admin_token", ""),
        kafka_producer=getattr(state, "kafka_producer", None),
        environment=state.settings.ENVIRONMENT,
    )


@router.get("/{merchant_id}", response_model=MerchantResponse)
async def get_merchant(
    merchant_id: uuid.UUID,
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _check_access(merchant_id, principal)
    merchant = await db.get(Merchant, merchant_id)
    if not merchant or merchant.is_deleted:
        raise HTTPException(status_code=404, detail="Merchant not found")
    checklist = await build_checklist(merchant_id, db)
    return _merchant_to_response(merchant, checklist, request.app.state.encryptor)


@router.put("/{merchant_id}", response_model=MerchantResponse)
async def update_merchant(
    merchant_id: uuid.UUID,
    body: MerchantUpdateRequest,
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _check_access(merchant_id, principal)
    merchant = await db.get(Merchant, merchant_id)
    if not merchant or merchant.is_deleted:
        raise HTTPException(status_code=404, detail="Merchant not found")

    enc = request.app.state.encryptor
    if body.website_url is not None:
        merchant.website_url = body.website_url
    if body.support_email is not None:
        merchant.support_email = enc.encrypt(str(body.support_email))
    if body.support_phone is not None:
        merchant.support_phone = enc.encrypt(body.support_phone)
    if body.display_name is not None:
        merchant.display_name = body.display_name
    if body.logo_url is not None:
        merchant.logo_url = body.logo_url
    if body.business_category is not None:
        merchant.business_category = body.business_category

    await db.commit()
    await db.refresh(merchant)
    checklist = await build_checklist(merchant_id, db)
    return _merchant_to_response(merchant, checklist, enc)


@router.get("/{merchant_id}/checklist", response_model=OnboardingChecklist)
async def get_checklist(
    merchant_id: uuid.UUID,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _check_access(merchant_id, principal)
    return await build_checklist(merchant_id, db)
