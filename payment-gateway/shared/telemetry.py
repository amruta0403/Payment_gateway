"""
Sentry / GlitchTip error tracking initialisation.

Call init_error_tracking(settings) once at process startup (in main.py lifespan
or at module level before the app is created).  No-ops if GLITCHTIP_DSN is empty.

GlitchTip is a self-hosted, open-source Sentry-compatible server.
The sentry_sdk package works with both sentry.io and GlitchTip.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def init_error_tracking(settings) -> None:
    dsn = getattr(settings, "GLITCHTIP_DSN", "") or ""
    if not dsn:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.asyncio import AsyncioIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=getattr(settings, "ENVIRONMENT", "development"),
            release=getattr(settings, "SERVICE_NAME", "unknown") + "@" +
                    getattr(settings, "SERVICE_VERSION", "0.1.0"),
            # Capture 5 % of transactions for performance monitoring
            traces_sample_rate=0.05,
            # Redact sensitive headers before sending to GlitchTip
            before_send=_scrub_event,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
                AsyncioIntegration(),
                LoggingIntegration(level=logging.WARNING, event_level=logging.ERROR),
            ],
            # Never send raw SQL queries (they may contain PII)
            send_default_pii=False,
        )
        log.info("error_tracking.initialised", dsn=dsn[:30] + "…")
    except ImportError:
        log.warning("error_tracking.sentry_sdk_not_installed — pip install sentry-sdk")
    except Exception as exc:
        log.warning("error_tracking.init_failed", error=str(exc))


# ── Event scrubber ────────────────────────────────────────────────────────────

_SCRUB_HEADERS = frozenset({
    "authorization", "cookie", "x-api-key", "x-service-token",
    "x-upi-signature", "x-webhook-signature",
})
_SCRUB_BODY_KEYS = frozenset({
    "pan", "cvv", "card_number", "password", "otp", "secret",
    "access_token", "refresh_token", "api_key",
})


def _scrub_event(event: dict, hint: dict) -> dict | None:
    """Strip PII from the Sentry event before transmission."""
    try:
        req = event.get("request", {})
        if "headers" in req:
            req["headers"] = {
                k: "[Filtered]" if k.lower() in _SCRUB_HEADERS else v
                for k, v in req.get("headers", {}).items()
            }
        if "data" in req and isinstance(req["data"], dict):
            req["data"] = {
                k: "[Filtered]" if k.lower() in _SCRUB_BODY_KEYS else v
                for k, v in req["data"].items()
            }
    except Exception:
        pass
    return event
