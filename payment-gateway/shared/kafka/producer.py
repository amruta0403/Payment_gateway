from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

import structlog
from aiokafka import AIOKafkaProducer

log = structlog.get_logger()


@dataclass
class BaseEvent:
    event_type: str
    source_service: str
    payload: dict
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    schema_version: str = "1.0"


class PaymentEventProducer:
    def __init__(self, bootstrap_servers: str, source_service: str) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._source_service = source_service
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            acks="all",
            enable_idempotence=True,
            compression_type="gzip",
            value_serializer=lambda v: json.dumps(v).encode(),
            key_serializer=lambda k: k.encode() if k else None,
        )
        await self._producer.start()
        log.info("kafka.producer.started", bootstrap_servers=self._bootstrap_servers)

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
            log.info("kafka.producer.stopped")

    async def publish(
        self,
        topic: str,
        event_type: str,
        payload: dict,
        key: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        if not self._producer:
            raise RuntimeError("Producer not started")
        event = BaseEvent(
            event_type=event_type,
            source_service=self._source_service,
            payload=payload,
            trace_id=trace_id,
        )
        data = asdict(event)
        await self._producer.send_and_wait(topic, value=data, key=key)
        log.debug(
            "kafka.published",
            topic=topic,
            event_type=event_type,
            event_id=event.event_id,
        )

    async def publish_batch(
        self, events: list[tuple[str, str, dict, str | None]]
    ) -> None:
        for topic, event_type, payload, key in events:
            await self.publish(topic, event_type, payload, key)
