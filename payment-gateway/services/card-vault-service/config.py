from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    SERVICE_NAME: str = "card-vault-service"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False

    # Vault DB — NEVER points to main payment DB
    VAULT_DATABASE_URL: str = (
        "postgresql+asyncpg://vault_user:vault_pass@postgres-vault:5432/vault_db"
    )
    DB_POOL_SIZE: int = 5

    # Redis — only for rate limiting (no sensitive data stored)
    REDIS_URL: str = "redis://redis:6379/0"

    # Auth
    INTERNAL_SERVICE_TOKEN: str = "internal-token-change-me"

    # CDE network — requests from outside this subnet are rejected
    CDE_NETWORK_SUBNET: str = "172.20.0.0/16"
    # In development, skip subnet check to allow host-machine testing
    SKIP_SUBNET_CHECK: bool = False

    # Encryption keys (base64-encoded 32-byte AES keys)
    CARD_ENCRYPTION_KEY_VERSION: int = 1
    CARD_ENCRYPTION_KEY_V1: str = ""
    CARD_ENCRYPTION_KEY_V2: str = ""
    CARD_ENCRYPTION_KEY_V3: str = ""

    # Infisical
    INFISICAL_TOKEN: str = ""
    INFISICAL_SITE_URL: str = "http://infisical:8080"
