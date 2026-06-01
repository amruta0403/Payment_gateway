from __future__ import annotations

import json
import traceback
from collections.abc import Awaitable, Callable

import structlog
from aiokafka import AIOKafkaConsumer

from shared.kafka.producer import BaseEvent, PaymentEventProducer

log = structlog.get_logger()


class PaymentEventConsumer:
    def __init__(
        self,
        topics: list[str],
        group_id: str,
        bootstrap_servers: str,
        dlq_topic: str,
    ) -> None:
        self._topics = topics
        self._group_id = group_id
        self._bootstrap_servers = bootstrap_servers
        self._dlq_topic = dlq_topic
        self._consumer: AIOKafkaConsumer | None = None
        self._dlq_producer: PaymentEventProducer | None = None

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=lambda v: json.loads(v.decode()),
        )
        await self._consumer.start()
        self._dlq_producer = PaymentEventProducer(
            self._bootstrap_servers, f"{self._group_id}-dlq-writer"
        )
        await self._dlq_producer.start()
        log.info("kafka.consumer.started", topics=self._topics, group=self._group_id)

    async def stop(self) -> None:
        if self._consumer:
            await self._consumer.stop()
        if self._dlq_producer:
            await self._dlq_producer.stop()
        log.info("kafka.consumer.stopped")

    async def consume(
        self,
        handler: Callable[[str, BaseEvent], Awaitable[None]],
    ) -> None:
        if not self._consumer:
            raise RuntimeError("Consumer not started")
        async for msg in self._consumer:
            try:
                raw = msg.value
                event = BaseEvent(
                    event_type=raw.get("event_type", "unknown"),
                    source_service=raw.get("source_service", "unknown"),
                    payload=raw.get("payload", {}),
                    event_id=raw.get("event_id", ""),
                    trace_id=raw.get("trace_id"),
                    timestamp=raw.get("timestamp", ""),
                    schema_version=raw.get("schema_version", "1.0"),
                )
                await handler(msg.topic, event)
                await self._consumer.commit()
            except Exception as exc:
                error_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                log.error(
                    "kafka.consumer.handler_error",
                    topic=msg.topic,
                    error=str(exc),
                    traceback=error_str,
                )
                await self._route_to_dlq(msg, error_str)
                await self._consumer.commit()

    async def _route_to_dlq(self, original_msg, error_str: str) -> None:
        if not self._dlq_producer:
            return
        try:
            await self._dlq_producer.publish(
                topic=self._dlq_topic,
                event_type="dlq.failed_event",
                payload={
                    "original_topic": original_msg.topic,
                    "original_value": original_msg.value,
                    "error": error_str,
                },
            )
        except Exception as exc:
            log.error("kafka.dlq.write_error", error=str(exc))
