from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.api_key import ApiKey
from schemas.merchant import ApiKeyCreateRequest, ApiKeyCreateResponse, ApiKeyListItem
from shared.exceptions.handlers import PaymentGatewayError

log = structlog.get_logger()


async def create_api_key(
    merchant_id: uuid.UUID,
    request: ApiKeyCreateRequest,
    db: AsyncSession,
) -> ApiKeyCreateResponse:
    env = request.environment.lower()
    prefix = f"sk_{env}_{secrets.token_urlsafe(8)}"
    secret = f"{prefix}_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(secret.encode()).hexdigest()

    key_row = ApiKey(
        merchant_id=merchant_id,
        name=request.name,
        key_prefix=prefix,
        key_hash=key_hash,
        environment=request.environment,
        permissions=request.permissions,
        is_active=True,
    )
    db.add(key_row)
    await db.commit()

    log.info("api_key.created", merchant_id=str(merchant_id), prefix=prefix, env=request.environment)

    return ApiKeyCreateResponse(
        id=key_row.id,
        name=key_row.name,
        key_prefix=prefix,
        full_key=secret,  # shown only here — never stored, only the hash is
        environment=key_row.environment,
        permissions=key_row.permissions,
        created_at=key_row.created_at,
    )


async def list_api_keys(
    merchant_id: uuid.UUID,
    db: AsyncSession,
) -> list[ApiKeyListItem]:
    rows = (
        await db.execute(
            select(ApiKey).where(
                ApiKey.merchant_id == merchant_id,
                ApiKey.is_deleted.is_(False),
            ).order_by(ApiKey.created_at.desc())
        )
    ).scalars().all()

    return [
        ApiKeyListItem(
            id=r.id,
            name=r.name,
            key_prefix=r.key_prefix,
            environment=r.environment,
            permissions=r.permissions,
            is_active=r.is_active,
            last_used_at=r.last_used_at,
            usage_count=r.usage_count,
            expires_at=r.expires_at,
            created_at=r.created_at,
        )
        for r in rows
    ]


async def revoke_api_key(
    key_id: uuid.UUID,
    merchant_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    result = await db.execute(
        update(ApiKey)
        .where(ApiKey.id == key_id, ApiKey.merchant_id == merchant_id)
        .values(is_active=False)
        .returning(ApiKey.id)
    )
    if not result.fetchone():
        raise PaymentGatewayError("API key not found")
    await db.commit()
    log.info("api_key.revoked", key_id=str(key_id), merchant_id=str(merchant_id))
