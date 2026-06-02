from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class AuditLogResponse(BaseModel):
    id: uuid.UUID
    service: str
    entity_type: str
    entity_id: uuid.UUID | None
    action: str
    actor_id: uuid.UUID | None
    actor_type: str | None
    merchant_id: uuid.UUID | None
    metadata_: dict = Field(alias="metadata")
    kafka_topic: str | None
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class AuditLogPage(BaseModel):
    items: list[AuditLogResponse]
    next_cursor: str | None
    has_more: bool


class KongAccessLog(BaseModel):
    """Payload posted by Kong/Traefik access log plugin."""
    service: str
    request_id: str | None = None
    method: str
    path: str
    status_code: int
    latency_ms: int | None = None
    client_ip: str | None = None
    consumer_id: str | None = None
    extra: dict = Field(default_factory=dict)
