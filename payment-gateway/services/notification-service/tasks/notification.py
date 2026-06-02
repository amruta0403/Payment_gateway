from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from celery import shared_task
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select, update

from celery_app import celery_app
from models.notification_log import (
    NotificationChannel, NotificationLog, NotificationStatus, NotificationType,
)
from utils.db import get_sync_db

log = logging.getLogger(__name__)

# ── Jinja2 template env ───────────────────────────────────────────────────────
_TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "email"
_jinja_env: Environment | None = None


def _get_jinja() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=select_autoescape(["html"]),
        )
    return _jinja_env


# Map notification_type → (template_filename, default_subject)
_TYPE_TEMPLATE: dict[str, tuple[str, str]] = {
    NotificationType.PAYMENT_SUCCESS:   ("payment_success.html",   "Payment Successful — ₹{amount}"),
    NotificationType.PAYMENT_FAILED:    ("payment_failed.html",    "Payment Failed"),
    NotificationType.REFUND_INITIATED:  ("refund_initiated.html",  "Refund Initiated — ₹{amount}"),
    NotificationType.REFUND_COMPLETED:  ("refund_completed.html",  "Refund Completed — ₹{amount}"),
    NotificationType.SETTLEMENT_ADVICE: ("settlement_advice.html", "Settlement Advice"),
    NotificationType.KYC_APPROVED:      ("kyc_approved.html",      "Your KYC is Approved!"),
    NotificationType.KYC_REJECTED:      ("kyc_rejected.html",      "KYC Verification Update"),
}


# ── send_email_task ───────────────────────────────────────────────────────────

@celery_app.task(
    name="notification.send_email",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def send_email_task(
    self,
    event_id: str,
    notification_type: str,
    recipient_encrypted: str,
    context: dict,
    merchant_id: str | None = None,
    transaction_id: str | None = None,
) -> dict:
    """
    1. Check idempotency — skip if already SENT/DELIVERED for this event_id + channel.
    2. Create/upsert NotificationLog.
    3. Render Jinja2 template.
    4. Send via configured email provider.
    5. Update log status.
    """
    from config import Settings
    settings = Settings()

    n_type = NotificationType(notification_type)
    template_file, subject_tpl = _TYPE_TEMPLATE.get(n_type, ("payment_success.html", "Payment Gateway"))
    subject = subject_tpl.format(**context)

    with get_sync_db() as db:
        # ── Idempotency check ─────────────────────────────────────────────────
        existing = db.execute(
            select(NotificationLog).where(
                NotificationLog.event_id == uuid.UUID(event_id),
                NotificationLog.channel == NotificationChannel.EMAIL,
            )
        ).scalar_one_or_none()

        if existing and existing.status in (NotificationStatus.SENT, NotificationStatus.DELIVERED):
            log.info("notification.email.already_sent", event_id=event_id)
            return {"status": "skipped", "id": str(existing.id)}

        # ── Create or update log record ───────────────────────────────────────
        if existing:
            notif_id = existing.id
        else:
            log_row = NotificationLog(
                event_id=uuid.UUID(event_id),
                merchant_id=uuid.UUID(merchant_id) if merchant_id else None,
                transaction_id=uuid.UUID(transaction_id) if transaction_id else None,
                notification_type=n_type,
                channel=NotificationChannel.EMAIL,
                recipient=recipient_encrypted,
                template_id=template_file,
                subject=subject,
                status=NotificationStatus.QUEUED,
                payload=context,
            )
            db.add(log_row)
            db.flush()
            notif_id = log_row.id

        db.execute(
            update(NotificationLog)
            .where(NotificationLog.id == notif_id)
            .values(
                status=NotificationStatus.QUEUED,
                attempts=NotificationLog.attempts + 1,
                last_attempt_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    # ── Render template ───────────────────────────────────────────────────────
    try:
        template = _get_jinja().get_template(template_file)
        html = template.render(**context, support_email=settings.SMTP_FROM_EMAIL)
    except Exception as exc:
        log.error("notification.email.template_error", template=template_file, error=str(exc))
        html = f"<p>Transaction update from Payment Gateway. Details: {context.get('transaction_id','')}</p>"

    # ── Decrypt recipient ─────────────────────────────────────────────────────
    try:
        from shared.utils.encryption import FieldEncryptor
        enc_key = settings.CARD_ENCRYPTION_KEY_V1
        if enc_key:
            recipient = FieldEncryptor(enc_key).decrypt(recipient_encrypted)
        else:
            recipient = recipient_encrypted
    except Exception:
        recipient = recipient_encrypted

    # ── Send ──────────────────────────────────────────────────────────────────
    try:
        import asyncio
        from providers.email import build_email_provider
        provider = build_email_provider(settings)
        msg_id = asyncio.get_event_loop().run_until_complete(
            provider.send(to=recipient, subject=subject, html=html)
        )
        new_status = NotificationStatus.SENT
        error_msg = None
    except Exception as exc:
        log.warning("notification.email.send_failed", error=str(exc))
        new_status = NotificationStatus.FAILED
        msg_id = None
        error_msg = str(exc)[:500]
        raise self.retry(exc=exc)

    # ── Update log ────────────────────────────────────────────────────────────
    with get_sync_db() as db:
        db.execute(
            update(NotificationLog)
            .where(NotificationLog.id == notif_id)
            .values(
                status=new_status,
                provider=type(provider).__name__,
                provider_message_id=msg_id,
                error_message=error_msg,
                delivered_at=datetime.now(timezone.utc) if new_status == NotificationStatus.SENT else None,
            )
        )

    log.info("notification.email.result", status=new_status.value, event_id=event_id)
    return {"status": new_status.value, "message_id": msg_id}


# ── send_sms_task ─────────────────────────────────────────────────────────────

_SMS_TEMPLATES: dict[str, str] = {
    NotificationType.PAYMENT_SUCCESS:   "Payment of Rs.{amount_rupees} successful. Txn: {transaction_id[:8]}. -PayGateway",
    NotificationType.PAYMENT_FAILED:    "Payment of Rs.{amount_rupees} failed. Please retry. -PayGateway",
    NotificationType.REFUND_INITIATED:  "Refund of Rs.{amount_rupees} initiated. 3-5 business days. -PayGateway",
    NotificationType.REFUND_COMPLETED:  "Refund of Rs.{amount_rupees} credited. Ref: {refund_id[:8]}. -PayGateway",
    NotificationType.KYC_APPROVED:      "Your KYC is approved. Your account is now active. -PayGateway",
    NotificationType.KYC_REJECTED:      "KYC verification failed. Please re-submit documents. -PayGateway",
}


@celery_app.task(
    name="notification.send_sms",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    acks_late=True,
)
def send_sms_task(
    self,
    event_id: str,
    notification_type: str,
    recipient_phone_encrypted: str,
    context: dict,
    merchant_id: str | None = None,
) -> dict:
    from config import Settings
    settings = Settings()

    n_type = NotificationType(notification_type)
    msg_template = _SMS_TEMPLATES.get(n_type, "Payment Gateway notification.")
    try:
        message = msg_template.format(**context)
    except (KeyError, IndexError):
        message = msg_template.split("{")[0].strip()

    # Idempotency
    with get_sync_db() as db:
        existing = db.execute(
            select(NotificationLog).where(
                NotificationLog.event_id == uuid.UUID(event_id),
                NotificationLog.channel == NotificationChannel.SMS,
            )
        ).scalar_one_or_none()
        if existing and existing.status in (NotificationStatus.SENT, NotificationStatus.DELIVERED):
            return {"status": "skipped"}

        log_row = NotificationLog(
            event_id=uuid.UUID(event_id),
            merchant_id=uuid.UUID(merchant_id) if merchant_id else None,
            notification_type=n_type,
            channel=NotificationChannel.SMS,
            recipient=recipient_phone_encrypted,
            template_id=f"sms_{n_type.value.lower()}",
            status=NotificationStatus.QUEUED,
            payload=context,
        )
        db.add(log_row)
        db.flush()
        notif_id = log_row.id
        db.commit()

    try:
        from shared.utils.encryption import FieldEncryptor
        enc_key = settings.CARD_ENCRYPTION_KEY_V1
        phone = FieldEncryptor(enc_key).decrypt(recipient_phone_encrypted) if enc_key else recipient_phone_encrypted
    except Exception:
        phone = recipient_phone_encrypted

    try:
        import asyncio
        from providers.sms import build_sms_provider
        provider = build_sms_provider(settings)
        msg_id = asyncio.get_event_loop().run_until_complete(provider.send(phone=phone, message=message))
        new_status = NotificationStatus.SENT
        error_msg = None
    except Exception as exc:
        new_status = NotificationStatus.FAILED
        msg_id = None
        error_msg = str(exc)[:500]
        raise self.retry(exc=exc)

    with get_sync_db() as db:
        db.execute(
            update(NotificationLog)
            .where(NotificationLog.id == notif_id)
            .values(status=new_status, provider_message_id=msg_id, error_message=error_msg)
        )

    return {"status": new_status.value}
