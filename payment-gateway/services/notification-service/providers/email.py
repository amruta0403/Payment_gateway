from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx
import structlog

log = structlog.get_logger()


class EmailProvider(ABC):
    @abstractmethod
    async def send(self, to: str, subject: str, html: str, from_name: str = "") -> str:
        """Returns a provider message ID."""
        ...


# ── Resend (primary) ──────────────────────────────────────────────────────────

class ResendEmailProvider(EmailProvider):
    _BASE = "https://api.resend.com/emails"

    def __init__(self, api_key: str, from_email: str, from_name: str = "Payment Gateway") -> None:
        self._api_key = api_key
        self._from_email = from_email
        self._from_name = from_name

    async def send(self, to: str, subject: str, html: str, from_name: str = "") -> str:
        sender = f"{from_name or self._from_name} <{self._from_email}>"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                self._BASE,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"from": sender, "to": [to], "subject": subject, "html": html},
            )
            resp.raise_for_status()
            data = resp.json()
            msg_id = data.get("id", str(uuid.uuid4()))
            log.info("email.resend.sent", to=to[:4] + "***", message_id=msg_id)
            return msg_id


# ── SMTP fallback (aiosmtplib) ────────────────────────────────────────────────

class SMTPEmailProvider(EmailProvider):
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_email: str,
        from_name: str = "Payment Gateway",
        use_tls: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_email = from_email
        self._from_name = from_name
        self._use_tls = use_tls

    async def send(self, to: str, subject: str, html: str, from_name: str = "") -> str:
        try:
            import aiosmtplib  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError("aiosmtplib is required for SMTP fallback") from exc

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{from_name or self._from_name} <{self._from_email}>"
        msg["To"] = to
        msg.attach(MIMEText(html, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=self._host,
            port=self._port,
            username=self._username,
            password=self._password,
            use_tls=self._use_tls,
        )
        msg_id = str(uuid.uuid4())
        log.info("email.smtp.sent", to=to[:4] + "***", message_id=msg_id)
        return msg_id


# ── Factory ───────────────────────────────────────────────────────────────────

def build_email_provider(settings) -> EmailProvider:
    if settings.RESEND_API_KEY:
        return ResendEmailProvider(
            api_key=settings.RESEND_API_KEY,
            from_email=settings.SMTP_FROM_EMAIL,
            from_name=settings.SMTP_FROM_NAME,
        )
    return SMTPEmailProvider(
        host=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USERNAME,
        password=settings.SMTP_PASSWORD,
        from_email=settings.SMTP_FROM_EMAIL,
        from_name=settings.SMTP_FROM_NAME,
    )
