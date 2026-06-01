from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import date, datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import DbSession, RedisDep, SettingsDep
from models.card_token import BinDatabase, CardToken, VaultAccessLog
from schemas.vault import (
    CardMetadataResponse,
    ChargeDataRequest,
    ChargeDataResponse,
    DeleteCardResponse,
    RotateKeyRequest,
    RotationStatusResponse,
    TokenizeRequest,
    TokenizeResponse,
)
from services.encryption import CardVaultEncryptor
from shared.models.enums import CardCategory, CardNetwork
from utils.card_utils import (
    detect_network,
    detect_category,
    get_bin_info,
    is_card_expired,
    luhn_check,
)

log = structlog.get_logger()
router = APIRouter(prefix="/vault", tags=["vault"])

# In-process job tracking (upgrade to Redis/DB for multi-instance)
_rotation_jobs: dict[str, dict] = {}


def _get_encryptor(request: Request) -> CardVaultEncryptor:
    return request.app.state.encryptor


def _get_current_key_version(request: Request) -> int:
    return request.app.state.settings.CARD_ENCRYPTION_KEY_VERSION


async def _log_access(
    db: AsyncSession,
    *,
    card_token: uuid.UUID | None,
    operation: str,
    requesting_service: str | None,
    requesting_ip: str | None,
    trace_id: str | None,
    outcome: str = "success",
    failure_reason: str | None = None,
) -> None:
    entry = VaultAccessLog(
        card_token=card_token,
        operation=operation,
        requesting_service=requesting_service,
        requesting_ip=requesting_ip,
        trace_id=trace_id,
        outcome=outcome,
        failure_reason=failure_reason,
    )
    db.add(entry)
    await db.flush()


# ── POST /vault/tokenize ──────────────────────────────────────────────────────

@router.post("/tokenize", response_model=TokenizeResponse, status_code=201)
async def tokenize_card(
    request: Request,
    body: TokenizeRequest,
    db: DbSession,
    settings: SettingsDep,
) -> TokenizeResponse:
    trace_id = getattr(request.state, "request_id", None)
    requesting_service = request.headers.get("X-Service-Name", "unknown")
    client_ip = request.client.host if request.client else None

    # ── 1. Validate Luhn ───────────────────────────────────────────────────────
    pan: str = body.pan
    if not luhn_check(pan):
        await _log_access(
            db, card_token=None, operation="TOKENIZE",
            requesting_service=requesting_service, requesting_ip=client_ip,
            trace_id=trace_id, outcome="failed", failure_reason="luhn_invalid",
        )
        raise HTTPException(status_code=400, detail="Invalid card number")

    # ── 2. Check expiry ────────────────────────────────────────────────────────
    if is_card_expired(body.expiry_month, body.expiry_year):
        await _log_access(
            db, card_token=None, operation="TOKENIZE",
            requesting_service=requesting_service, requesting_ip=client_ip,
            trace_id=trace_id, outcome="failed", failure_reason="card_expired",
        )
        raise HTTPException(status_code=400, detail="Card has expired")

    # ── 3. Detect network + BIN info ───────────────────────────────────────────
    card_network: CardNetwork = detect_network(pan)
    first6 = pan[:6]
    bin_info = await get_bin_info(first6, db)
    card_category_str = bin_info.get("card_category") or CardCategory.UNKNOWN.value
    try:
        card_category = CardCategory(card_category_str)
    except ValueError:
        card_category = CardCategory.UNKNOWN

    # ── 4. Compute fingerprint ─────────────────────────────────────────────────
    fingerprint = hashlib.sha256(pan.encode()).hexdigest()

    # ── 5. Deduplication check ─────────────────────────────────────────────────
    existing = (
        await db.execute(
            select(CardToken).where(
                CardToken.pan_fingerprint == fingerprint,
                CardToken.merchant_id == body.merchant_id,
                CardToken.is_active.is_(True),
            ).limit(1)
        )
    ).scalar_one_or_none()

    if existing:
        # ── discard CVV immediately — it was never used ────────────────────────
        cvv = body.cvv
        del cvv

        await _log_access(
            db, card_token=existing.token, operation="TOKENIZE",
            requesting_service=requesting_service, requesting_ip=client_ip,
            trace_id=trace_id, outcome="dedup",
        )
        await db.commit()

        import calendar
        expires_at = (
            date(existing.expiry_year, existing.expiry_month,
                 calendar.monthrange(existing.expiry_year, existing.expiry_month)[1])
            if existing.expiry_year and existing.expiry_month
            else None
        )
        return TokenizeResponse(
            token=existing.token,
            last4=existing.pan_last4 or pan[-4:],
            first6=existing.pan_first6 or first6,
            card_network=CardNetwork(existing.card_network) if existing.card_network else card_network,
            card_category=CardCategory(existing.card_category) if existing.card_category else card_category,
            issuer_bank=existing.issuer_bank,
            is_domestic=existing.is_domestic,
            expires_at=expires_at,
        )

    # ── 6. Encrypt PAN ────────────────────────────────────────────────────────
    encryptor: CardVaultEncryptor = _get_encryptor(request)
    key_version: int = _get_current_key_version(request)
    pan_encrypted = encryptor.encrypt_pan(pan, key_version)

    # ── 7. Encrypt cardholder name (if provided) ───────────────────────────────
    cardholder_name_enc: str | None = None
    if body.cardholder_name:
        cardholder_name_enc = encryptor.encrypt_field(body.cardholder_name, key_version)

    # ── 7b. DISCARD CVV — this is the only place it ever exists ───────────────
    cvv = body.cvv
    del cvv
    # pan is still needed for last4/first6, will be cleared after INSERT

    # ── 8. Insert card_tokens record ──────────────────────────────────────────
    import calendar
    expiry_end = date(body.expiry_year, body.expiry_month,
                      calendar.monthrange(body.expiry_year, body.expiry_month)[1])

    card_token_row = CardToken(
        pan_encrypted=pan_encrypted,
        key_version=key_version,
        pan_fingerprint=fingerprint,
        pan_last4=pan[-4:],
        pan_first6=first6,
        pan_length=len(pan),
        expiry_month=body.expiry_month,
        expiry_year=body.expiry_year,
        cardholder_name=cardholder_name_enc,
        card_network=card_network.value,
        card_category=card_category.value,
        issuer_bank=bin_info.get("issuer_bank"),
        issuer_country=bin_info.get("issuer_country"),
        is_domestic=bin_info.get("is_domestic", True),
        merchant_id=body.merchant_id,
        customer_id=body.customer_id,
        expires_at=expiry_end,
    )
    db.add(card_token_row)
    await db.flush()

    # ── Clear PAN from local scope ─────────────────────────────────────────────
    last4 = pan[-4:]
    del pan
    del fingerprint

    # ── 9. Audit log ──────────────────────────────────────────────────────────
    await _log_access(
        db, card_token=card_token_row.token, operation="TOKENIZE",
        requesting_service=requesting_service, requesting_ip=client_ip,
        trace_id=trace_id, outcome="success",
    )
    await db.commit()

    return TokenizeResponse(
        token=card_token_row.token,
        last4=last4,
        first6=first6,
        card_network=card_network,
        card_category=card_category,
        issuer_bank=card_token_row.issuer_bank,
        is_domestic=card_token_row.is_domestic,
        expires_at=expiry_end,
    )


# ── POST /vault/charge-data ───────────────────────────────────────────────────

@router.post("/charge-data")
async def get_charge_data(
    request: Request,
    body: ChargeDataRequest,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
) -> ChargeDataResponse:
    """
    INTERNAL ONLY.
    Rate-limited: 1 call per token per 30 seconds.
    Response MUST NOT be cached — headers enforced below.
    NO CVV is ever returned — it was never stored.
    """
    trace_id = getattr(request.state, "request_id", None)
    requesting_service = request.headers.get("X-Service-Name", "payment-service")
    client_ip = request.client.host if request.client else None

    # ── Rate limit: 1 per token per 30s ───────────────────────────────────────
    from shared.cache.redis_client import record_velocity
    rate_exceeded = await record_velocity(
        redis,
        f"vault:charge:{body.token}",
        window_seconds=30,
        max_count=1,
        member=str(uuid.uuid4()),
    )
    if rate_exceeded:
        await _log_access(
            db, card_token=body.token, operation="CHARGE",
            requesting_service=requesting_service, requesting_ip=client_ip,
            trace_id=trace_id, outcome="rate_limited",
        )
        raise HTTPException(status_code=429, detail="Rate limit: max 1 charge-data call per token per 30s")

    # ── Lookup token ───────────────────────────────────────────────────────────
    row = (
        await db.execute(
            select(CardToken).where(
                CardToken.token == body.token,
                CardToken.is_active.is_(True),
            ).limit(1)
        )
    ).scalar_one_or_none()

    if not row:
        await _log_access(
            db, card_token=body.token, operation="CHARGE",
            requesting_service=requesting_service, requesting_ip=client_ip,
            trace_id=trace_id, outcome="failed", failure_reason="token_not_found",
        )
        raise HTTPException(status_code=404, detail="Token not found or inactive")

    # ── Decrypt PAN ───────────────────────────────────────────────────────────
    encryptor: CardVaultEncryptor = _get_encryptor(request)
    try:
        pan = encryptor.decrypt_pan(row.pan_encrypted)
    except Exception as exc:
        await _log_access(
            db, card_token=body.token, operation="CHARGE",
            requesting_service=requesting_service, requesting_ip=client_ip,
            trace_id=trace_id, outcome="failed", failure_reason="decryption_error",
        )
        log.error("vault.decrypt_pan.failed", token=str(body.token), error=str(exc))
        raise HTTPException(status_code=500, detail="Decryption error")

    # ── Update usage stats ────────────────────────────────────────────────────
    await db.execute(
        update(CardToken)
        .where(CardToken.id == row.id)
        .values(
            last_used_at=datetime.now(timezone.utc),
            usage_count=CardToken.usage_count + 1,
        )
    )

    await _log_access(
        db, card_token=body.token, operation="CHARGE",
        requesting_service=requesting_service, requesting_ip=client_ip,
        trace_id=trace_id, outcome="success",
    )
    await db.commit()

    # ── Build response with strict no-cache headers ────────────────────────────
    response_data = ChargeDataResponse(
        pan=pan,
        expiry_month=row.expiry_month,
        expiry_year=row.expiry_year,
    )
    del pan  # clear from local scope immediately

    return JSONResponse(
        content=response_data.model_dump(),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, private",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ── GET /vault/card/{token}/metadata ─────────────────────────────────────────

@router.get("/card/{token}/metadata", response_model=CardMetadataResponse)
async def get_card_metadata(
    request: Request,
    token: uuid.UUID,
    db: DbSession,
) -> CardMetadataResponse:
    row = (
        await db.execute(
            select(CardToken).where(
                CardToken.token == token,
                CardToken.is_active.is_(True),
            ).limit(1)
        )
    ).scalar_one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Token not found")

    return CardMetadataResponse(
        token=row.token,
        last4=row.pan_last4 or "????",
        first6=row.pan_first6 or "??????",
        card_network=CardNetwork(row.card_network) if row.card_network else CardNetwork.UNKNOWN,
        card_category=CardCategory(row.card_category) if row.card_category else CardCategory.UNKNOWN,
        issuer_bank=row.issuer_bank,
        expiry_month=row.expiry_month,
        expiry_year=row.expiry_year,
        is_domestic=row.is_domestic,
        is_active=row.is_active,
        usage_count=row.usage_count,
        created_at=row.created_at,
    )


# ── DELETE /vault/card/{token} ────────────────────────────────────────────────

@router.delete("/card/{token}", response_model=DeleteCardResponse)
async def delete_card(
    request: Request,
    token: uuid.UUID,
    db: DbSession,
) -> DeleteCardResponse:
    trace_id = getattr(request.state, "request_id", None)
    requesting_service = request.headers.get("X-Service-Name", "unknown")
    client_ip = request.client.host if request.client else None

    result = await db.execute(
        update(CardToken)
        .where(CardToken.token == token, CardToken.is_active.is_(True))
        .values(is_active=False)
        .returning(CardToken.id)
    )
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Token not found or already deleted")

    await _log_access(
        db, card_token=token, operation="DELETE",
        requesting_service=requesting_service, requesting_ip=client_ip,
        trace_id=trace_id, outcome="success",
    )
    await db.commit()
    return DeleteCardResponse(token=token)


# ── POST /vault/admin/rotate-key ──────────────────────────────────────────────

@router.post("/admin/rotate-key", response_model=RotationStatusResponse)
async def rotate_key(
    request: Request,
    body: RotateKeyRequest,
    background_tasks: BackgroundTasks,
    db: DbSession,
    settings: SettingsDep,
) -> RotationStatusResponse:
    encryptor: CardVaultEncryptor = _get_encryptor(request)
    current_version = settings.CARD_ENCRYPTION_KEY_VERSION

    if body.new_key_version not in encryptor.available_versions:
        raise HTTPException(
            status_code=400,
            detail=f"Key version {body.new_key_version} not loaded. Available: {encryptor.available_versions}",
        )

    job_id = str(uuid.uuid4())
    _rotation_jobs[job_id] = {
        "job_id": job_id,
        "status": "started",
        "old_version": current_version,
        "new_version": body.new_key_version,
        "total_tokens": 0,
        "processed": 0,
        "failed_count": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "error": None,
    }

    background_tasks.add_task(
        _run_key_rotation,
        job_id=job_id,
        encryptor=encryptor,
        new_version=body.new_key_version,
        old_version=current_version,
        db_url=settings.VAULT_DATABASE_URL,
    )

    return RotationStatusResponse(**_rotation_jobs[job_id])


async def _run_key_rotation(
    job_id: str,
    encryptor: CardVaultEncryptor,
    new_version: int,
    old_version: int,
    db_url: str,
) -> None:
    from shared.db.session import create_engine, create_session_factory

    engine = create_engine(db_url, pool_size=3)
    factory = create_session_factory(engine)

    _rotation_jobs[job_id]["status"] = "in_progress"

    try:
        async with factory() as session:
            total = (
                await session.execute(
                    select(func.count(CardToken.id)).where(
                        CardToken.is_active.is_(True),
                        CardToken.key_version == old_version,
                    )
                )
            ).scalar_one()
            _rotation_jobs[job_id]["total_tokens"] = total

            offset = 0
            batch_size = 50

            while True:
                rows = (
                    await session.execute(
                        select(CardToken)
                        .where(
                            CardToken.is_active.is_(True),
                            CardToken.key_version == old_version,
                        )
                        .limit(batch_size)
                        .offset(offset)
                    )
                ).scalars().all()

                if not rows:
                    break

                for row in rows:
                    try:
                        new_encrypted = encryptor.re_encrypt(row.pan_encrypted, new_version)
                        await session.execute(
                            update(CardToken)
                            .where(CardToken.id == row.id)
                            .values(pan_encrypted=new_encrypted, key_version=new_version)
                        )
                        _rotation_jobs[job_id]["processed"] += 1
                    except Exception as exc:
                        log.error("rotation.row_failed", id=str(row.id), error=str(exc))
                        _rotation_jobs[job_id]["failed_count"] += 1

                await session.commit()
                offset += batch_size
                await asyncio.sleep(0)  # yield to event loop

        _rotation_jobs[job_id]["status"] = "completed"
        _rotation_jobs[job_id]["completed_at"] = datetime.now(timezone.utc).isoformat()

    except Exception as exc:
        log.error("rotation.job_failed", job_id=job_id, error=str(exc))
        _rotation_jobs[job_id]["status"] = "failed"
        _rotation_jobs[job_id]["error"] = str(exc)
    finally:
        await engine.dispose()


# ── GET /vault/admin/rotation-status/{job_id} ────────────────────────────────

@router.get("/admin/rotation-status/{job_id}", response_model=RotationStatusResponse)
async def rotation_status(job_id: str) -> RotationStatusResponse:
    job = _rotation_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Rotation job not found")
    return RotationStatusResponse(**job)
