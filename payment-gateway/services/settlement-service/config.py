from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    SERVICE_NAME: str = "settlement-service"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql+asyncpg://pguser:pgpass@postgres-main:5432/payment_db"
    DB_POOL_SIZE: int = 10
    REDIS_URL: str = "redis://redis:6379/0"
    KAFKA_BOOTSTRAP_SERVERS: str = "redpanda:9092"

    KEYCLOAK_URL: str = "http://keycloak:8080"
    KEYCLOAK_REALM: str = "payment-gateway"
    KEYCLOAK_CLIENT_ID: str = "payment-backend"
    KEYCLOAK_CLIENT_SECRET: str = "change-me"

    INFISICAL_TOKEN: str = ""
    INTERNAL_SERVICE_TOKEN: str = "internal-token-change-me"
    CARD_ENCRYPTION_KEY_VERSION: int = 1
    CARD_ENCRYPTION_KEY_V1: str = ""

    AWS_REGION: str = "ap-south-1"
    S3_KYC_BUCKET: str = "payment-kyc-docs"

    PAYMENT_SERVICE_URL: str = "http://payment-service:8010"
    CARD_VAULT_SERVICE_URL: str = "http://card-vault-service:8011"
    MERCHANT_SERVICE_URL: str = "http://merchant-service:8012"
    FRAUD_SERVICE_URL: str = "http://fraud-service:8013"
    UPI_SERVICE_URL: str = "http://upi-service:8014"

    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"
