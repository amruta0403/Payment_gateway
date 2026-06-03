from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PAYMENT_SERVICE_URL: str = "http://localhost:8010"
    MERCHANT_SERVICE_URL: str = "http://localhost:8012"
    SETTLEMENT_SERVICE_URL: str = "http://localhost:8015"
    REFUND_SERVICE_URL: str = "http://localhost:8016"
    TRANSACTION_SERVICE_URL: str = "http://localhost:8020"
    WEBHOOK_SERVICE_URL: str = "http://localhost:8021"
    FRAUD_SERVICE_URL: str = "http://localhost:8013"
    REPORTING_SERVICE_URL: str = "http://localhost:8022"
    KEYCLOAK_URL: str = "http://localhost:8080"
    KEYCLOAK_REALM: str = "payment-gateway"
    ALLOWED_ORIGINS: str = "http://localhost:3001"


settings = Settings()
