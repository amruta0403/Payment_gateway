from __future__ import annotations

import asyncio
import json
import uuid

import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from models.notification_log import NotificationType
from shared.kafka.topics import Topics

log = structlog.get_logger()

# Maps Kafka topic → notification_type
_TOPIC_NOTIFICATION_MAP: dict[str, str] = {
    Topics.PAYMENT_CAPTURED:       NotificationType.PAYMENT_SUCCESS.value,
    Topics.PAYMENT_FAILED:         NotificationType.PAYMENT_FAILED.value,
    Topics.REFUND_INITIATED:       NotificationType.REFUND_INITIATED.value,
    Topics.REFUND_COMPLETED:       NotificationType.REFUND_COMPLETED.value,
    Topics.SETTLEMENT_COMPLETED:   NotificationType.SETTLEMENT_ADVICE.value,
    Topics.MERCHANT_KYC_COMPLETED: NotificationType.KYC_APPROVED.value,
    Topics.MERCHANT_KYC_REJECTED:  NotificationType.KYC_REJECTED.value,
}

_SUBSCRIBED_TOPICS = list(_TOPIC_NOTIFICATION_MAP.keys())


async def _dispatch_notifications(event_data: dict, topic: str, settings) -> None:
    """Extract recipient info and dispatch Celery tasks."""
    from tasks.notification import send_email_task, send_sms_task
    from shared.utils.encryption import FieldEncryptor

    notification_type = _TOPIC_NOTIFICATION_MAP.get(topic)
    if not notification_type:
        return

    event_id = event_data.get("event_id") or event_data.get("payment_id") or str(uuid.uuid4())
    merchant_id = event_data.get("merchant_id")
    transaction_id = event_data.get("transaction_id") or event_data.get("payment_id")

    # Build template context (never include raw PII — use masked values if present)
    context = {
        "transaction_id":   str(transaction_id or ""),
        "merchant_id":      str(merchant_id or ""),
        "amount_rupees":    str((event_data.get("amount", 0) or 0) / 100),
        "currency":         event_data.get("currency", "INR"),
        "payment_method":   event_data.get("payment_method", ""),
        "refund_id":        str(event_data.get("refund_id", "")),
        "error_message":    event_data.get("error_message", ""),
        "rejection_reason": event_data.get("rejection_reason", ""),
    }

    enc_key = settings.CARD_ENCRYPTION_KEY_V1
    encryptor = FieldEncryptor(enc_key) if enc_key else None

    def _encrypt(value: str) -> str:
        return encryptor.encrypt(value) if encryptor and value else value

    # Email — customer email (must be in event payload, already masked/hashed for most events)
    customer_email = event_data.get("customer_email") or event_data.get("support_email")
    if customer_email and "@" in customer_email:
        send_email_task.delay(
            event_id=event_id,
            notification_type=notification_type,
            recipient_encrypted=_encrypt(customer_email),
            context=context,
            merchant_id=str(merchant_id) if merchant_id else None,
            transaction_id=str(transaction_id) if transaction_id else None,
        )

    # SMS — merchant support phone (only for KYC events)
    if notification_type in (NotificationType.KYC_APPROVED.value, NotificationType.KYC_REJECTED.value):
        support_phone = event_data.get("support_phone")
        if support_phone:
            send_sms_task.delay(
                event_id=event_id + "_sms",
                notification_type=notification_type,
                recipient_phone_encrypted=_encrypt(support_phone),
                context=context,
                merchant_id=str(merchant_id) if merchant_id else None,
            )


async def run_notification_consumer(settings) -> None:
    """
    Async Kafka consumer loop. Started as asyncio.create_task in lifespan.
    Subscribes to payment/refund/KYC events → dispatches Celery email/SMS tasks.
    """
    consumer = AIOKafkaConsumer(
        *_SUBSCRIBED_TOPICS,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id="notification-consumers",
        value_deserializer=lambda m: json.loads(m.decode("utf-8", errors="replace")),
        auto_offset_reset="latest",
        enable_auto_commit=True,
        session_timeout_ms=30_000,
        heartbeat_interval_ms=10_000,
    )

    while True:
        try:
            await consumer.start()
            log.info("notification.kafka.consumer.started", topics=_SUBSCRIBED_TOPICS)
            async for msg in consumer:
                try:
                    await _dispatch_notifications(
                        event_data=msg.value if isinstance(msg.value, dict) else {},
                        topic=msg.topic,
                        settings=settings,
                    )
                except Exception as exc:
                    log.warning("notification.kafka.dispatch_error", topic=msg.topic, error=str(exc))
        except KafkaError as exc:
            log.warning("notification.kafka.error", error=str(exc))
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            log.info("notification.kafka.consumer.stopping")
            break
        finally:
            try:
                await consumer.stop()
            except Exception:
                pass
