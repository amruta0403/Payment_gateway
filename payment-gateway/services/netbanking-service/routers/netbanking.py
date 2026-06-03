from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db_session, get_principal
from models.netbanking import NetbankingSession, NetbankingSessionStatus

log = structlog.get_logger()
router = APIRouter(prefix="/netbanking", tags=["netbanking"])


# ── Bank catalogue ────────────────────────────────────────────────────────────
SUPPORTED_BANKS = [
    {"code": "HDFC",  "name": "HDFC Bank",           "logo": "hdfc.png"},
    {"code": "ICICI", "name": "ICICI Bank",           "logo": "icici.png"},
    {"code": "SBI",   "name": "State Bank of India",  "logo": "sbi.png"},
    {"code": "AXIS",  "name": "Axis Bank",            "logo": "axis.png"},
    {"code": "KOTAK", "name": "Kotak Mahindra Bank",  "logo": "kotak.png"},
    {"code": "PNB",   "name": "Punjab National Bank", "logo": "pnb.png"},
    {"code": "BOB",   "name": "Bank of Baroda",       "logo": "bob.png"},
    {"code": "CANARA","name": "Canara Bank",           "logo": "canara.png"},
    {"code": "UNION", "name": "Union Bank of India",  "logo": "union.png"},
    {"code": "IDFC",  "name": "IDFC First Bank",      "logo": "idfc.png"},
    {"code": "YES",   "name": "Yes Bank",             "logo": "yes.png"},
    {"code": "INDUS", "name": "IndusInd Bank",        "logo": "indus.png"},
]
_BANK_MAP = {b["code"]: b for b in SUPPORTED_BANKS}


class InitiateRequest(BaseModel):
    transaction_id: uuid.UUID
    bank_code: str = Field(..., min_length=2, max_length=20)
    amount: int = Field(..., gt=0)
    return_url: str = Field(..., description="Merchant return URL after payment")
    description: str = Field(default="", max_length=200)


class InitiateResponse(BaseModel):
    session_id: uuid.UUID
    redirect_url: str
    bank_code: str
    bank_name: str
    expires_at: datetime


class SessionStatusResponse(BaseModel):
    session_id: uuid.UUID
    transaction_id: uuid.UUID
    status: NetbankingSessionStatus
    bank_code: str
    bank_txn_id: str | None
    completed_at: datetime | None
    model_config = {"from_attributes": True}


def _merchant_id(principal) -> uuid.UUID:
    mid = getattr(principal, "merchant_id", None)
    if not mid:
        raise HTTPException(403, "merchant_id required")
    return uuid.UUID(str(mid)) if not isinstance(mid, uuid.UUID) else mid


@router.get("/banks")
async def list_banks():
    """List all supported net banking banks."""
    return {"banks": SUPPORTED_BANKS, "count": len(SUPPORTED_BANKS)}


@router.post("/initiate", response_model=InitiateResponse, status_code=201)
async def initiate_netbanking(
    body: InitiateRequest,
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    mid = _merchant_id(principal)
    bank_code = body.bank_code.upper()
    if bank_code not in _BANK_MAP:
        raise HTTPException(400, f"Bank '{bank_code}' not supported. Use GET /v1/netbanking/banks.")

    session = NetbankingSession(
        transaction_id=body.transaction_id,
        merchant_id=mid,
        bank_code=bank_code,
        amount=body.amount,
        return_url=body.return_url,
        status=NetbankingSessionStatus.INITIATED,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db.add(session)
    await db.flush()

    base = str(request.base_url).rstrip("/")
    redirect_url = f"{base}/v1/netbanking/redirect/{session.id}"
    session.redirect_url = redirect_url

    await db.commit()
    await db.refresh(session)

    return InitiateResponse(
        session_id=session.id,
        redirect_url=redirect_url,
        bank_code=bank_code,
        bank_name=_BANK_MAP[bank_code]["name"],
        expires_at=session.expires_at,
    )


@router.get("/redirect/{session_id}")
async def bank_redirect(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Mock: simulate the bank redirect page.
    In production this would redirect to the actual bank URL with signed params.
    """
    sess = await db.get(NetbankingSession, session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    if sess.status not in (NetbankingSessionStatus.INITIATED, NetbankingSessionStatus.REDIRECTED):
        raise HTTPException(400, f"Session in terminal state: {sess.status}")

    sess.status = NetbankingSessionStatus.REDIRECTED
    await db.commit()

    # Return a mock bank HTML form
    return {
        "message": "Mock bank redirect. POST to /v1/netbanking/callback/{session_id} to simulate success/failure.",
        "session_id": str(session_id),
        "bank": sess.bank_code,
        "amount": sess.amount,
    }


@router.post("/callback/{session_id}")
async def bank_callback(
    session_id: uuid.UUID,
    success: bool = True,
    bank_txn_id: str | None = None,
    db: AsyncSession = Depends(get_db_session),
):
    """NPCI/bank callback handler. Called by bank after payment."""
    sess = await db.get(NetbankingSession, session_id)
    if not sess:
        raise HTTPException(404, "Session not found")

    now = datetime.now(timezone.utc)
    if success:
        sess.status = NetbankingSessionStatus.SUCCESS
        sess.bank_txn_id = bank_txn_id or f"MOCK{session_id.hex[:8].upper()}"
        sess.completed_at = now
    else:
        sess.status = NetbankingSessionStatus.FAILED
        sess.completed_at = now

    await db.commit()
    log.info("netbanking.callback", session_id=str(session_id), success=success)
    return {"status": sess.status.value, "session_id": str(session_id)}


@router.get("/status/{transaction_id}", response_model=SessionStatusResponse)
async def get_status(
    transaction_id: uuid.UUID,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    sess = (
        await db.execute(
            select(NetbankingSession)
            .where(NetbankingSession.transaction_id == transaction_id)
            .order_by(NetbankingSession.initiated_at.desc())
        )
    ).scalars().first()
    if not sess:
        raise HTTPException(404, "No netbanking session for this transaction")
    return SessionStatusResponse.model_validate(sess)
