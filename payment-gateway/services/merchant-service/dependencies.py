from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_db_session(request: Request) -> AsyncSession:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
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


# ── Unified auth dependency ─────────────────────────────────────────────────
# All routers use Depends(get_principal). Override this one function in tests.

def _make_auth_dep():
    from shared.auth.keycloak import get_combined_auth_dependency
    return get_combined_auth_dependency()


_auth_callable = _make_auth_dep()


async def get_principal(principal=Depends(_auth_callable)):
    """Unified auth — override with app.dependency_overrides[get_principal] in tests."""
    return principal


# ── Convenience accessors ───────────────────────────────────────────────────

async def get_encryptor(request: Request):
    return request.app.state.encryptor


async def get_kafka(request: Request):
    return getattr(request.app.state, "kafka_producer", None)


async def get_s3(request: Request):
    return getattr(request.app.state, "s3_client", None)


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
RedisDep  = Annotated[Redis, Depends(get_redis)]
