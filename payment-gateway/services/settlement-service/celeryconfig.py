from __future__ import annotations

import os

from celery.schedules import crontab

broker_url = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/1")
result_backend = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/2")

task_serializer = "json"
result_serializer = "json"
accept_content = ["json"]
timezone = "UTC"
enable_utc = True

task_acks_late = True            # re-queue on worker crash
worker_prefetch_multiplier = 1   # one task at a time — settlement tasks are heavy
task_track_started = True

beat_schedule = {
    "daily-settlement-batch": {
        "task": "settlement.create_daily_batch",
        # 23:00 IST = 17:30 UTC
        "schedule": crontab(hour=17, minute=30),
        "args": [None],          # None = use yesterday's date (computed inside task)
    },
    "daily-reconciliation": {
        "task": "settlement.reconcile",
        # 06:00 IST = 00:30 UTC
        "schedule": crontab(hour=0, minute=30),
    },
}

# Retry limits
task_max_retries = 5
