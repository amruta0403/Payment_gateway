from __future__ import annotations

from collections.abc import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

log = structlog.get_logger()


def create_engine(database_url: str, pool_size: int = 10, use_null_pool: bool = False):
    kwargs = {
        "pool_pre_ping": True,
        "echo": False,
    }
    if use_null_pool:
        kwargs["poolclass"] = NullPool
    else:
        kwargs.update(
            {
                "pool_size": pool_size,
                "max_overflow": 10,
                "pool_timeout": 30,
            }
        )
    return create_async_engine(database_url, **kwargs)


def create_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
