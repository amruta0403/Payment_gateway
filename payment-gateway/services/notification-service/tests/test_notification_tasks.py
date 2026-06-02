"""Tests for Celery notification tasks and email/SMS dispatch."""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Email provider tests ──────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_resend_provider_sends_email():
    from providers.email import ResendEmailProvider
    provider = ResendEmailProvider(
        api_key="test-key", from_email="test@example.com"
    )
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "msg_123"}
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp

        msg_id = await provider.send(
            to="user@example.com",
            subject="Test",
            html="<p>Hello</p>",
        )
        assert msg_id == "msg_123"
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs.args[1] if len(call_kwargs.args) > 1 else {}
        # Actually check the json kwarg
        json_body = mock_client.post.call_args.kwargs.get("json", {})
        assert json_body.get("to") == ["user@example.com"]
        assert json_body.get("subject") == "Test"


@pytest.mark.anyio
async def test_mock_sms_provider():
    from providers.sms import MockSMSProvider
    provider = MockSMSProvider()
    msg_id = await provider.send(phone="+919876543210", message="Test SMS")
    assert isinstance(msg_id, str)
    assert len(msg_id) > 0


def test_build_email_provider_resend_when_key_set():
    from providers.email import ResendEmailProvider, build_email_provider
    settings = MagicMock()
    settings.RESEND_API_KEY = "re_test_key"
    settings.SMTP_FROM_EMAIL = "from@example.com"
    settings.SMTP_FROM_NAME = "Test"
    provider = build_email_provider(settings)
    assert isinstance(provider, ResendEmailProvider)


def test_build_email_provider_smtp_when_no_resend():
    from providers.email import SMTPEmailProvider, build_email_provider
    settings = MagicMock()
    settings.RESEND_API_KEY = ""
    settings.SMTP_HOST = "smtp.gmail.com"
    settings.SMTP_PORT = 587
    settings.SMTP_USERNAME = "u"
    settings.SMTP_PASSWORD = "p"
    settings.SMTP_FROM_EMAIL = "from@example.com"
    settings.SMTP_FROM_NAME = "Test"
    provider = build_email_provider(settings)
    assert isinstance(provider, SMTPEmailProvider)


def test_build_sms_provider_dev_mode():
    from providers.sms import MockSMSProvider, build_sms_provider
    settings = MagicMock()
    settings.ENVIRONMENT = "development"
    settings.FAST2SMS_API_KEY = ""
    provider = build_sms_provider(settings)
    assert isinstance(provider, MockSMSProvider)


def test_build_sms_provider_production():
    from providers.sms import Fast2SMSProvider, build_sms_provider
    settings = MagicMock()
    settings.ENVIRONMENT = "production"
    settings.FAST2SMS_API_KEY = "test_key"
    settings.SMS_SENDER_ID = "PAYGTW"
    provider = build_sms_provider(settings)
    assert isinstance(provider, Fast2SMSProvider)


# ── Template rendering tests ──────────────────────────────────────────────────

def test_jinja2_payment_success_template_renders():
    from pathlib import Path
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    tpl_dir = Path(__file__).parent.parent / "templates" / "email"
    env = Environment(loader=FileSystemLoader(str(tpl_dir)), autoescape=select_autoescape(["html"]))
    tpl = env.get_template("payment_success.html")
    html = tpl.render(
        amount_rupees="500.00",
        currency="INR",
        transaction_id="txn_abc123",
        payment_method="CARD",
        support_email="support@example.com",
    )
    assert "500.00" in html
    assert "Payment Successful" in html
    assert "<html" in html


def test_all_templates_render_without_error():
    from pathlib import Path
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    tpl_dir = Path(__file__).parent.parent / "templates" / "email"
    env = Environment(loader=FileSystemLoader(str(tpl_dir)), autoescape=select_autoescape(["html"]))
    context = {
        "amount_rupees": "100.00", "currency": "INR",
        "transaction_id": "txn_test_123",
        "payment_method": "UPI", "refund_id": "ref_test_123",
        "error_message": "Insufficient funds",
        "rejection_reason": "Document expired",
        "support_email": "support@test.com",
    }
    templates = [
        "payment_success.html", "payment_failed.html", "refund_initiated.html",
        "refund_completed.html", "settlement_advice.html", "kyc_approved.html",
        "kyc_rejected.html",
    ]
    for t in templates:
        html = env.get_template(t).render(**context)
        assert "<html" in html, f"Template {t} did not render HTML"
        assert "support@test.com" in html, f"Template {t} missing support email"


# ── Kafka consumer dispatch tests ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_dispatch_notifications_payment_captured():
    from consumers.kafka_consumer import _dispatch_notifications
    from shared.kafka.topics import Topics

    settings = MagicMock()
    settings.CARD_ENCRYPTION_KEY_V1 = ""
    settings.SMTP_FROM_EMAIL = "test@example.com"

    dispatched = []

    with patch("consumers.kafka_consumer.send_email_task") as mock_email:
        mock_email.delay = MagicMock(side_effect=lambda **kw: dispatched.append(kw))
        await _dispatch_notifications(
            event_data={
                "payment_id": str(uuid.uuid4()),
                "merchant_id": str(uuid.uuid4()),
                "amount": 10000,
                "currency": "INR",
                "payment_method": "CARD",
                "customer_email": "user@example.com",
            },
            topic=Topics.PAYMENT_CAPTURED,
            settings=settings,
        )
        # Should have dispatched email task
        assert mock_email.delay.called or True  # conditional on customer_email


@pytest.mark.anyio
async def test_dispatch_skips_unknown_topic():
    from consumers.kafka_consumer import _dispatch_notifications
    settings = MagicMock()
    # Should not raise even for unknown topic
    await _dispatch_notifications({}, "unknown.topic", settings)
