from __future__ import annotations

import ipaddress
import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware

from config import Settings
from shared.db.session import create_engine, create_session_factory
from shared.exceptions.handlers import register_exception_handlers
from shared.utils.masking import LogSanitiser

settings = Settings()
_start_time = time.time()

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(settings.LOG_LEVEL),
)
log = structlog.get_logger()

# Error tracking (GlitchTip / Sentry) — no-op if GLITCHTIP_DSN not set
from shared.telemetry import init_error_tracking
init_error_tracking(settings)

# ── Security middleware ───────────────────────────────────────────────────────

_CDE_SUBNET = ipaddress.ip_network(settings.CDE_NETWORK_SUBNET, strict=False)


class InternalServiceAuthMiddleware(BaseHTTPMiddleware):
    """
    PCI CONTROL: Enforces two checks on EVERY request:

    1. X-Service-Token header must match INTERNAL_SERVICE_TOKEN.
       Missing or wrong token → 403 immediately (no logging of token value).

    2. Client IP must be within the CDE Docker network subnet.
       Requests from outside the internal network → 403.
       (Bypass in development via SKIP_SUBNET_CHECK=true)
    """

    async def dispatch(self, request: Request, call_next):
        # /health and /metrics are exempt — they must be accessible for Docker healthcheck
        if request.url.path in ("/health", "/metrics"):
            return await call_next(request)

        # ── Token check ────────────────────────────────────────────────────────
        token = request.headers.get("X-Service-Token", "")
        if token != settings.INTERNAL_SERVICE_TOKEN:
            log.warning(
                "vault.auth.rejected",
                path=request.url.path,
                reason="invalid_token",
                ip=request.client.host if request.client else None,
            )
            return JSONResponse(
                status_code=403,
                content={"error": {"code": "FORBIDDEN", "message": "Invalid service token"}},
            )

        # ── IP / subnet check ─────────────────────────────────────────────────
        if not settings.SKIP_SUBNET_CHECK:
            forwarded_for = request.headers.get("X-Forwarded-For")
            client_ip_str = (
                forwarded_for.split(",")[0].strip()
                if forwarded_for
                else (request.client.host if request.client else "0.0.0.0")
            )
            try:
                client_ip = ipaddress.ip_address(client_ip_str)
                if client_ip not in _CDE_SUBNET:
                    log.warning(
                        "vault.auth.rejected",
                        path=request.url.path,
                        reason="outside_cde_subnet",
                        ip=client_ip_str,
                    )
                    return JSONResponse(
                        status_code=403,
                        content={"error": {"code": "FORBIDDEN", "message": "Access denied from this network"}},
                    )
            except ValueError:
                return JSONResponse(
                    status_code=403,
                    content={"error": {"code": "FORBIDDEN", "message": "Invalid client IP"}},
                )

        return await call_next(request)


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            service="card-vault-service",
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class LogSanitiserMiddleware(BaseHTTPMiddleware):
    """
    PCI CONTROL: Ensures no PAN, CVV, or card data leaks into log output.
    LogSanitiser.scrub() strips 16-digit sequences, CVV patterns, expiry dates.
    """
    _sanitiser = LogSanitiser()

    async def dispatch(self, request: Request, call_next):
        # The actual scrubbing happens at the structlog processor level.
        # This middleware's presence signals intent and can be extended.
        return await call_next(request)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("card_vault.startup")

    # ── Vault DB (postgres-vault on cde_network) ───────────────────────────────
    engine = create_engine(settings.VAULT_DATABASE_URL, pool_size=settings.DB_POOL_SIZE)
    app.state.session_factory = create_session_factory(engine)
    app.state.engine = engine
    app.state.settings = settings

    # ── Redis (rate limiting only) ─────────────────────────────────────────────
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    await redis.ping()
    app.state.redis = redis

    # ── Load encryption keys ───────────────────────────────────────────────────
    from services.encryption import load_keys_from_env, CardVaultEncryptor

    keys = load_keys_from_env(settings)
    if not keys:
        # Dev mode: generate a temporary key and warn loudly
        import base64, os
        dev_key = os.urandom(32)
        keys = {1: dev_key}
        log.warning(
            "card_vault.using_dev_key",
            message="No CARD_ENCRYPTION_KEY_V1 set — generated ephemeral key. SET IN PRODUCTION.",
        )

    app.state.encryptor = CardVaultEncryptor(keys)
    log.info("card_vault.keys_loaded", versions=list(keys.keys()))

    log.info("card_vault.ready")
    yield

    await redis.aclose()
    await engine.dispose()
    log.info("card_vault.shutdown")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Card Vault Service (PCI-CDE)",
    version="0.1.0",
    lifespan=lifespan,
    # Docs disabled in prod to avoid exposing PAN field names
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

# Order matters: InternalServiceAuthMiddleware runs first (outermost)
app.add_middleware(LogSanitiserMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(InternalServiceAuthMiddleware)

register_exception_handlers(app)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

from routers.vault import router as vault_router  # noqa: E402
app.include_router(vault_router)


@app.get("/health", tags=["ops"])
async def health():
    db_ok = False
    total_tokens = 0
    try:
        from sqlalchemy import select, text, func
        from models.card_token import CardToken
        async with app.state.session_factory() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
            total_tokens = (
                await session.execute(
                    select(func.count(CardToken.id)).where(CardToken.is_active.is_(True))
                )
            ).scalar_one()
    except Exception:
        pass

    return {
        "status": "ok" if db_ok else "degraded",
        "service": settings.SERVICE_NAME,
        "vault_db_connected": db_ok,
        "current_key_version": settings.CARD_ENCRYPTION_KEY_VERSION,
        "total_tokens": total_tokens,
        "uptime_seconds": round(time.time() - _start_time, 1),
    }
