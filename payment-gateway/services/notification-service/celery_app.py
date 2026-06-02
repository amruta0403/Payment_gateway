from __future__ import annotations

from celery import Celery
from celery.signals import worker_init

celery_app = Celery("notification-service")
celery_app.config_from_object("celeryconfig")
celery_app.autodiscover_tasks(["tasks"])


@worker_init.connect
def _on_worker_init(**kwargs):
    from config import Settings
    from utils.db import init_sync_db
    settings = Settings()
    init_sync_db(settings.DATABASE_URL)
