from __future__ import annotations

import base64
import os
from typing import Any

import structlog
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

log = structlog.get_logger()


class CardVaultEncryptor:
    """
    AES-256-GCM field encryptor with key versioning.

    Ciphertext format: "v{version}:{base64url(12-byte-nonce || ciphertext)}"

    Key rotation keeps old keys available for decryption until all records
    are migrated; new encryptions always use the current active version.
    """

    def __init__(self, key_store: dict[int, bytes]) -> None:
        if not key_store:
            raise ValueError("key_store must contain at least one key")
        for version, key in key_store.items():
            if len(key) != 32:
                raise ValueError(f"Key v{version} must be 32 bytes, got {len(key)}")
        self._raw_store = key_store
        self._aes_store: dict[int, AESGCM] = {
            v: AESGCM(k) for v, k in key_store.items()
        }

    def encrypt_pan(self, pan: str, key_version: int) -> str:
        if key_version not in self._aes_store:
            raise ValueError(f"Unknown key version: {key_version}")
        nonce = os.urandom(12)
        ct = self._aes_store[key_version].encrypt(nonce, pan.encode(), None)
        encoded = base64.b64encode(nonce + ct).decode()
        return f"v{key_version}:{encoded}"

    def decrypt_pan(self, encrypted: str) -> str:
        if ":" not in encrypted:
            raise ValueError("Invalid encrypted PAN format — missing version prefix")
        version_str, encoded = encrypted.split(":", 1)
        if not version_str.startswith("v"):
            raise ValueError(f"Invalid version prefix: {version_str!r}")
        try:
            version = int(version_str[1:])
        except ValueError as exc:
            raise ValueError(f"Non-numeric version: {version_str!r}") from exc
        if version not in self._aes_store:
            raise ValueError(f"No key loaded for version {version}")
        raw = base64.b64decode(encoded)
        if len(raw) < 13:
            raise ValueError("Ciphertext too short")
        nonce, ct = raw[:12], raw[12:]
        return self._aes_store[version].decrypt(nonce, ct, None).decode()

    def re_encrypt(self, old_encrypted: str, new_version: int) -> str:
        """Decrypt with whatever key version is embedded, re-encrypt with new_version."""
        pan = self.decrypt_pan(old_encrypted)
        return self.encrypt_pan(pan, new_version)

    def encrypt_field(self, value: str, key_version: int) -> str:
        """Encrypt any string field (e.g. cardholder_name) with the same scheme."""
        return self.encrypt_pan(value, key_version)

    def decrypt_field(self, encrypted: str) -> str:
        return self.decrypt_pan(encrypted)

    @property
    def available_versions(self) -> list[int]:
        return sorted(self._aes_store.keys())


def load_keys_from_env(settings: Any) -> dict[int, bytes]:
    """
    Load AES keys from environment / pydantic settings.
    Looks for CARD_ENCRYPTION_KEY_V1, V2, V3 ...
    Skips versions with empty/missing values.
    """
    keys: dict[int, bytes] = {}
    for version in range(1, 10):
        raw = getattr(settings, f"CARD_ENCRYPTION_KEY_V{version}", "") or ""
        if raw:
            decoded = base64.b64decode(raw)
            if len(decoded) != 32:
                raise ValueError(
                    f"CARD_ENCRYPTION_KEY_V{version} must decode to 32 bytes"
                )
            keys[version] = decoded
    return keys


async def load_keys_from_infisical(
    infisical_token: str,
    infisical_url: str,
) -> dict[int, bytes]:
    """
    Fetch encryption keys from Infisical secrets manager.
    Looks for secrets named CARD_ENCRYPTION_KEY_V1, V2, etc.
    Falls back gracefully if Infisical is unreachable.
    """
    import httpx

    keys: dict[int, bytes] = {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{infisical_url}/api/v3/secrets",
                headers={"Authorization": f"Bearer {infisical_token}"},
                params={"environment": "dev", "workspaceSlug": "payment-gateway"},
            )
            if resp.status_code == 200:
                secrets = {s["secretKey"]: s["secretValue"] for s in resp.json().get("secrets", [])}
                for version in range(1, 10):
                    key_name = f"CARD_ENCRYPTION_KEY_V{version}"
                    if key_name in secrets and secrets[key_name]:
                        decoded = base64.b64decode(secrets[key_name])
                        if len(decoded) == 32:
                            keys[version] = decoded
    except Exception as exc:
        log.warning("infisical.fetch_keys_failed", error=str(exc))
    return keys


def generate_dev_key() -> str:
    """Generate a random base64-encoded 32-byte key for local dev."""
    return base64.b64encode(os.urandom(32)).decode()
