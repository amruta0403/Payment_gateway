from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import Depends, Header, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.exceptions.handlers import UnauthorizedError

log = structlog.get_logger()


class ApiKeyContext(BaseModel):
    merchant_id: str
    permissions: list[str] = []
    environment: str = "SANDBOX"


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def validate_api_key(key: str, db: AsyncSession) -> ApiKeyContext:
    key_hash = hash_api_key(key)
    result = await db.execute(
        text(
            """
            SELECT merchant_id, permissions, environment, is_active, expires_at
            FROM api_keys
            WHERE key_hash = :key_hash
            LIMIT 1
            """
        ),
        {"key_hash": key_hash},
    )
    row = result.mappings().first()
    if not row:
        raise UnauthorizedError("Invalid API key")

    if not row["is_active"]:
        raise UnauthorizedError("API key has been revoked")

    if row["expires_at"] and row["expires_at"] < datetime.now(timezone.utc):
        raise UnauthorizedError("API key has expired")

    # Fire-and-forget usage tracking — do not await result
    await db.execute(
        text(
            """
            UPDATE api_keys
            SET last_used_at = NOW(), usage_count = usage_count + 1
            WHERE key_hash = :key_hash
            """
        ),
        {"key_hash": key_hash},
    )

    return ApiKeyContext(
        merchant_id=str(row["merchant_id"]),
        permissions=row["permissions"] or [],
        environment=row["environment"] or "SANDBOX",
    )


async def _get_db_from_request(request: Request) -> AsyncSession:
    """Pull the session factory wired up in app.state by main.py lifespan."""
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


def get_api_key_dependency():
    """
    Returns a FastAPI dependency that:
    - Reads x-api-key header
    - Validates against DB
    - Returns ApiKeyContext | None (None = no key provided)
    """
    async def _get_api_key(
        request: Request,
        x_api_key: Annotated[str | None, Header(alias="x-api-key")] = None,
    ) -> ApiKeyContext | None:
        if not x_api_key:
            return None
        factory = request.app.state.session_factory
        async with factory() as session:
            return await validate_api_key(x_api_key, session)

    return _get_api_key
