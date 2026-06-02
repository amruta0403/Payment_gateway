"""Synchronous SQLAlchemy session for Celery tasks."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

log = logging.getLogger(__name__)

_sync_factory = None


def init_sync_db(database_url: str) -> None:
    global _sync_factory
    sync_url = database_url.replace("+asyncpg", "")
    engine = create_engine(sync_url, pool_size=3, max_overflow=5, pool_pre_ping=True)
    _sync_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    log.info("notification_sync_db.ready")


@contextmanager
def get_sync_db() -> Generator[Session, None, None]:
    if _sync_factory is None:
        raise RuntimeError("Sync DB not initialized — call init_sync_db() first")
    session: Session = _sync_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
