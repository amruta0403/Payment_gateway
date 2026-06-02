from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError
from sqlalchemy.ext.asyncio import AsyncSession

from models.audit_log import AuditLog
from services.sanitizer import sanitise_for_audit
from shared.kafka.topics import Topics

log = structlog.get_logger()

# Subscribe to ALL topics — audit service is a universal observer
_ALL_TOPICS = Topics.all_topics()


def _infer_entity_info(topic: str, data: dict) -> tuple[str, str, str | None]:
    """Returns (service, entity_type, entity_id | None)."""
    mapping = {
        "payment.":     ("payment-service",      "transaction"),
        "refund.":      ("refund-service",        "refund"),
        "upi.":         ("upi-service",           "upi_transaction"),
        "merchant.kyc": ("merchant-service",      "kyc_document"),
        "merchant.":    ("merchant-service",      "merchant"),
        "settlement.":  ("settlement-service",    "settlement_batch"),
        "audit.":       ("audit-service",         "audit_event"),
        "dlq.":         ("dlq",                   "dlq_message"),
    }
    service = "unknown"
    entity_type = "event"
    for prefix, (svc, etype) in mapping.items():
        if topic.startswith(prefix):
            service = svc
            entity_type = etype
            break

    # Best-effort entity ID extraction
    entity_id = (
        data.get("transaction_id")
        or data.get("refund_id")
        or data.get("merchant_id")
        or data.get("batch_id")
        or data.get("id")
    )
    return service, entity_type, str(entity_id) if entity_id else None


async def _write_audit_log(
    session_factory,
    topic: str,
    partition: int,
    offset: int,
    data: dict,
) -> None:
    service, entity_type, entity_id = _infer_entity_info(topic, data)
    clean = sanitise_for_audit(data)

    import uuid
    log_entry = AuditLog(
        service=service,
        entity_type=entity_type,
        entity_id=uuid.UUID(entity_id) if entity_id else None,
        action=topic,
        merchant_id=(
            uuid.UUID(str(data.get("merchant_id"))) if data.get("merchant_id") else None
        ),
        new_state=clean,
        metadata_={"topic": topic, "partition": partition},
        kafka_topic=topic,
        kafka_offset=str(offset),
    )

    async with session_factory() as session:
        session.add(log_entry)
        await session.commit()


async def run_audit_consumer(session_factory, settings) -> None:
    """
    Consumes ALL Kafka topics and writes sanitised records to audit_logs.
    Append-only: never updates or deletes. Runs as asyncio task in lifespan.
    """
    consumer = AIOKafkaConsumer(
        *_ALL_TOPICS,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id="audit-consumers",
        value_deserializer=lambda m: json.loads(m.decode("utf-8", errors="replace")),
        auto_offset_reset="earliest",   # audit should not miss events
        enable_auto_commit=True,
        session_timeout_ms=30_000,
        heartbeat_interval_ms=10_000,
    )

    while True:
        try:
            await consumer.start()
            log.info("audit.kafka.consumer.started", topic_count=len(_ALL_TOPICS))
            async for msg in consumer:
                try:
                    payload = msg.value if isinstance(msg.value, dict) else {"raw": str(msg.value)}
                    await _write_audit_log(
                        session_factory=session_factory,
                        topic=msg.topic,
                        partition=msg.partition,
                        offset=msg.offset,
                        data=payload,
                    )
                except Exception as exc:
                    log.warning("audit.kafka.write_error", topic=msg.topic, error=str(exc))
        except KafkaError as exc:
            log.warning("audit.kafka.consumer_error", error=str(exc))
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            log.info("audit.kafka.consumer.stopping")
            break
        finally:
            try:
                await consumer.stop()
            except Exception:
                pass
