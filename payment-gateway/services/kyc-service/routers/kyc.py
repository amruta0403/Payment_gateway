from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db_session, get_principal
from models.kyc_session import KycProviderEnum, KycSession, KycSessionStatus

log = structlog.get_logger()
router = APIRouter(prefix="/kyc", tags=["kyc"])


class KycVerifyRequest(BaseModel):
    session_type: str = Field(..., pattern="^(PAN|GSTIN|BANK_ACCOUNT|AADHAAR)$")
    data: dict = Field(..., description="The document data to verify (PAN, GSTIN, etc.)")
    provider: KycProviderEnum = KycProviderEnum.MOCK


class KycSessionResponse(BaseModel):
    id: uuid.UUID
    merchant_id: uuid.UUID
    session_type: str
    status: KycSessionStatus
    provider: KycProviderEnum
    provider_session_id: str | None
    rejection_reason: str | None
    verified_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


def _merchant_id(principal) -> uuid.UUID:
    mid = getattr(principal, "merchant_id", None)
    if not mid:
        raise HTTPException(403, "merchant_id required")
    return uuid.UUID(str(mid)) if not isinstance(mid, uuid.UUID) else mid


def _is_admin(principal) -> bool:
    return any(r in getattr(principal, "roles", []) for r in ("ADMIN", "COMPLIANCE_OFFICER"))


@router.post("/verify", response_model=KycSessionResponse, status_code=201)
async def initiate_kyc(
    body: KycVerifyRequest,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    mid = _merchant_id(principal)
    session = KycSession(
        merchant_id=mid,
        session_type=body.session_type,
        status=KycSessionStatus.PENDING,
        provider=body.provider,
        submitted_data=body.data,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(session)

    # Mock auto-verification
    if body.provider == KycProviderEnum.MOCK:
        session.status = KycSessionStatus.VERIFIED
        session.verified_at = datetime.now(timezone.utc)
        session.provider_response = {"mock": True, "verified": True}
        log.info("kyc.mock_verified", session_type=body.session_type, merchant_id=str(mid))

    await db.commit()
    await db.refresh(session)
    return KycSessionResponse.model_validate(session)


@router.get("/verify/{session_id}", response_model=KycSessionResponse)
async def get_kyc_status(
    session_id: uuid.UUID,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    sess = await db.get(KycSession, session_id)
    if not sess:
        raise HTTPException(404, "KYC session not found")
    if not _is_admin(principal) and sess.merchant_id != _merchant_id(principal):
        raise HTTPException(403, "Access denied")
    return KycSessionResponse.model_validate(sess)


@router.get("/sessions", response_model=list[KycSessionResponse])
async def list_kyc_sessions(
    merchant_id: Optional[uuid.UUID] = None,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    if _is_admin(principal):
        mid = merchant_id
    else:
        mid = _merchant_id(principal)

    q = select(KycSession).order_by(KycSession.created_at.desc())
    if mid:
        q = q.where(KycSession.merchant_id == mid)
    rows = (await db.execute(q)).scalars().all()
    return [KycSessionResponse.model_validate(r) for r in rows]


@router.post("/admin/{session_id}/approve", response_model=KycSessionResponse)
async def approve_kyc(
    session_id: uuid.UUID,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    if not _is_admin(principal):
        raise HTTPException(403, "Admin or Compliance role required")
    sess = await db.get(KycSession, session_id)
    if not sess:
        raise HTTPException(404, "KYC session not found")
    sess.status = KycSessionStatus.VERIFIED
    sess.verified_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(sess)
    return KycSessionResponse.model_validate(sess)


@router.post("/admin/{session_id}/reject")
async def reject_kyc(
    session_id: uuid.UUID,
    reason: str,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    if not _is_admin(principal):
        raise HTTPException(403, "Admin role required")
    sess = await db.get(KycSession, session_id)
    if not sess:
        raise HTTPException(404, "KYC session not found")
    sess.status = KycSessionStatus.REJECTED
    sess.rejection_reason = reason
    await db.commit()
    return {"status": "rejected", "session_id": str(session_id)}
