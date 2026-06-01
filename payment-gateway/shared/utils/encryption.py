from __future__ import annotations

import base64
import hashlib
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class FieldEncryptor:
    def __init__(self, key_b64: str) -> None:
        key = base64.b64decode(key_b64)
        if len(key) != 32:
            raise ValueError(f"Key must be 32 bytes, got {len(key)}")
        self._key = key
        self._aes = AESGCM(key)

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(12)
        ciphertext = self._aes.encrypt(nonce, plaintext.encode(), None)
        return base64.b64encode(nonce + ciphertext).decode()

    def decrypt(self, ciphertext_b64: str) -> str:
        raw = base64.b64decode(ciphertext_b64)
        nonce = raw[:12]
        ciphertext = raw[12:]
        plaintext = self._aes.decrypt(nonce, ciphertext, None)
        return plaintext.decode()

    def encrypt_fields(self, obj: dict[str, Any], fields: list[str]) -> dict[str, Any]:
        result = dict(obj)
        for field in fields:
            if field in result and result[field] is not None:
                result[field] = self.encrypt(str(result[field]))
        return result

    def decrypt_fields(self, obj: dict[str, Any], fields: list[str]) -> dict[str, Any]:
        result = dict(obj)
        for field in fields:
            if field in result and result[field] is not None:
                try:
                    result[field] = self.decrypt(str(result[field]))
                except Exception:
                    pass
        return result

    @staticmethod
    def hash_field(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()


def generate_key_b64() -> str:
    return base64.b64encode(os.urandom(32)).decode()
