from __future__ import annotations

import re


def mask_pan(pan: str) -> str:
    pan = pan.replace(" ", "")
    if len(pan) < 8:
        return "••••••••"
    return pan[:6] + "•" * (len(pan) - 10) + pan[-4:]


def mask_phone(phone: str) -> str:
    phone = phone.strip()
    if len(phone) < 6:
        return "••••••"
    prefix = phone[:3]
    suffix = phone[-5:]
    masked = "•" * (len(phone) - 8)
    return f"{prefix}{masked}{suffix}"


def mask_email(email: str) -> str:
    if "@" not in email:
        return "•••@•••"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "•"
    else:
        masked_local = local[0] + "•" * (len(local) - 2) + local[-1]
    return f"{masked_local}@{domain}"


def mask_vpa(vpa: str) -> str:
    if "@" not in vpa:
        return "•••@•••"
    local, handle = vpa.split("@", 1)
    if len(local) <= 2:
        masked = local[0] + "•"
    else:
        masked = local[0] + "•" * (len(local) - 2) + local[-1]
    return f"{masked}@{handle}"


_PAN_RE = re.compile(r"\b(\d{4})[\s-]?(\d{4})[\s-]?(\d{4})[\s-]?(\d{4})\b")
_CVV_RE = re.compile(r"(?i)(cvv|cvc)[\"':\s=]*(\d{3,4})")
_API_KEY_RE = re.compile(r"(sk_(?:live|sandbox|test)_)\S+")
_EXPIRY_RE = re.compile(r"\b(0[1-9]|1[0-2])/(2\d{1,3})\b")


class LogSanitiser:
    @staticmethod
    def scrub(text: str) -> str:
        text = _PAN_RE.sub(lambda m: mask_pan(m.group(0).replace(" ", "").replace("-", "")), text)
        text = _CVV_RE.sub(r"\1=[REDACTED]", text)
        text = _API_KEY_RE.sub(r"\1[REDACTED]", text)
        text = _EXPIRY_RE.sub("[REDACTED]", text)
        return text

    @staticmethod
    def scrub_dict(data: dict) -> dict:
        sensitive_keys = {
            "pan", "cvv", "cvc", "card_number", "card_cvv", "password",
            "secret", "api_key", "three_ds_cavv", "cavv",
        }
        result: dict = {}
        for k, v in data.items():
            if k.lower() in sensitive_keys:
                result[k] = "[REDACTED]"
            elif isinstance(v, dict):
                result[k] = LogSanitiser.scrub_dict(v)
            elif isinstance(v, str):
                result[k] = LogSanitiser.scrub(v)
            else:
                result[k] = v
        return result
