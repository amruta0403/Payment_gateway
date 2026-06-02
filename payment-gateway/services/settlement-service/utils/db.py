"""
Synchronous SQLAlchemy session for Celery tasks.
Celery runs in a regular (non-async) context, so we use psycopg2.
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

log = logging.getLogger(__name__)

_sync_engine = None
_sync_session_factory = None


def init_sync_db(database_url: str) -> None:
    global _sync_engine, _sync_session_factory

    # Convert asyncpg URL to sync (psycopg2) URL
    sync_url = database_url.replace("+asyncpg", "")

    _sync_engine = create_engine(
        sync_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        echo=False,
    )
    _sync_session_factory = sessionmaker(
        bind=_sync_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    log.info("sync_db.initialized", extra={"url": sync_url.split("@")[-1]})


@contextmanager
def get_sync_db() -> Generator[Session, None, None]:
    if _sync_session_factory is None:
        raise RuntimeError(
            "Sync DB not initialized — call init_sync_db() first "
            "(happens automatically on Celery worker startup)"
        )
    session: Session = _sync_session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
