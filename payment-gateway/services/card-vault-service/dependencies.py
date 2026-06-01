from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_vault_db(request: Request) -> AsyncSession:
    """Pull the vault session factory from app.state (points to postgres-vault)."""
    factory = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_redis(request: Request) -> Redis:
    return request.app.state.redis


DbSession = Annotated[AsyncSession, Depends(get_vault_db)]
RedisDep = Annotated[Redis, Depends(get_redis)]
