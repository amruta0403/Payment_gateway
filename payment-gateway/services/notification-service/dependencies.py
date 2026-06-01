from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_db_session() -> AsyncSession:
    from main import app
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_redis() -> Redis:
    from main import app
    return app.state.redis


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
RedisDep  = Annotated[Redis, Depends(get_redis)]
