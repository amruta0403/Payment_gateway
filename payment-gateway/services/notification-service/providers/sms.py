from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

import httpx
import structlog

log = structlog.get_logger()


class SMSProvider(ABC):
    @abstractmethod
    async def send(self, phone: str, message: str) -> str:
        """Returns a provider message ID."""
        ...


# ── Fast2SMS (primary — India) ────────────────────────────────────────────────

class Fast2SMSProvider(SMSProvider):
    _URL = "https://www.fast2sms.com/dev/bulkV2"

    def __init__(self, api_key: str, sender_id: str = "PAYGTW") -> None:
        self._api_key = api_key
        self._sender_id = sender_id

    async def send(self, phone: str, message: str) -> str:
        # Fast2SMS expects numbers without country code
        number = phone.lstrip("+").removeprefix("91")
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                self._URL,
                headers={"authorization": self._api_key},
                json={
                    "route": "q",          # quick transactional
                    "message": message[:160],
                    "language": "english",
                    "flash": "0",
                    "numbers": number,
                    "sender_id": self._sender_id,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            msg_id = data.get("request_id", str(uuid.uuid4()))
            log.info("sms.fast2sms.sent", phone=phone[-4:], msg_id=msg_id)
            return msg_id


# ── Mock SMS (development) ────────────────────────────────────────────────────

class MockSMSProvider(SMSProvider):
    async def send(self, phone: str, message: str) -> str:
        msg_id = str(uuid.uuid4())
        log.info("sms.mock.sent", phone=phone[-4:], message=message[:30], msg_id=msg_id)
        return msg_id


# ── Factory ───────────────────────────────────────────────────────────────────

def build_sms_provider(settings) -> SMSProvider:
    if settings.ENVIRONMENT == "development" or not settings.FAST2SMS_API_KEY:
        return MockSMSProvider()
    return Fast2SMSProvider(
        api_key=settings.FAST2SMS_API_KEY,
        sender_id=getattr(settings, "SMS_SENDER_ID", "PAYGTW"),
    )
