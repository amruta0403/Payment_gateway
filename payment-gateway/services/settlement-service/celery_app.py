from __future__ import annotations

from celery import Celery
from celery.signals import worker_init, worker_ready

celery_app = Celery("settlement-service")
celery_app.config_from_object("celeryconfig")
celery_app.autodiscover_tasks(["tasks"])


@worker_init.connect
def _on_worker_init(**kwargs):
    """Initialize sync DB connection pool before the first task runs."""
    from config import Settings
    from utils.db import init_sync_db
    settings = Settings()
    init_sync_db(settings.DATABASE_URL)


@worker_ready.connect
def _on_worker_ready(sender, **kwargs):
    import logging
    logging.getLogger(__name__).info("settlement-celery-worker.ready")
