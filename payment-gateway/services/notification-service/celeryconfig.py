import os

broker_url        = os.environ.get("CELERY_BROKER_URL",    "redis://redis:6379/1")
result_backend    = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/2")
task_serializer   = "json"
result_serializer = "json"
accept_content    = ["json"]
timezone          = "UTC"
enable_utc        = True
task_acks_late    = True
worker_prefetch_multiplier = 2
task_routes       = {
    "notification.send_email": {"queue": "email"},
    "notification.send_sms":   {"queue": "sms"},
}
