from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel
from models.notification_log import NotificationChannel, NotificationStatus, NotificationType


class NotificationLogResponse(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID | None
    notification_type: NotificationType
    channel: NotificationChannel
    status: NotificationStatus
    template_id: str | None
    attempts: int
    provider_message_id: str | None
    error_message: str | None
    created_at: datetime
    delivered_at: datetime | None

    model_config = {"from_attributes": True}


class SendEmailRequest(BaseModel):
    """Internal — used by tasks."""
    to: str
    subject: str
    html: str
    idempotency_key: str | None = None
