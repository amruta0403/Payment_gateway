from __future__ import annotations

import re
import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware

from config import Settings
from shared.db.session import create_engine, create_session_factory
from shared.exceptions.handlers import register_exception_handlers
from shared.kafka.producer import PaymentEventProducer
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


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            service="fraud-service",
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


_PAN_PAT = re.compile(r"\b\d{16}\b")


class LogSanitiserMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("service.startup", service="fraud-service")

    engine = create_engine(settings.DATABASE_URL, pool_size=settings.DB_POOL_SIZE)
    app.state.session_factory = create_session_factory(engine)
    app.state.engine = engine

    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    await redis.ping()
    app.state.redis = redis

    producer = PaymentEventProducer(settings.KAFKA_BOOTSTRAP_SERVERS, "fraud-service")
    try:
        await producer.start()
        app.state.kafka_producer = producer
    except Exception as exc:
        log.warning("kafka.producer.start_failed", error=str(exc))
        app.state.kafka_producer = None

    # ── Fraud-specific state ───────────────────────────────────────────────
    from rules.engine import RulesEngine, ALL_RULE_NAMES
    from model.scorer import FraudMLScorer

    app.state.rules_engine = RulesEngine(redis=redis)
    app.state.ml_scorer = FraudMLScorer()
    app.state.settings = settings

    # Seed fraud_rules table (upsert by rule_name)
    try:
        from models.fraud import FraudRule
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        async with app.state.session_factory() as seed_db:
            for rule_def in ALL_RULE_NAMES:
                stmt = pg_insert(FraudRule).values(**rule_def).on_conflict_do_nothing(
                    index_elements=["rule_name"]
                )
                await seed_db.execute(stmt)
            await seed_db.commit()
    except Exception as exc:
        log.warning("fraud_rules.seed.failed", error=str(exc))

    log.info("service.ready", service="fraud-service")
    yield

    if app.state.kafka_producer:
        await app.state.kafka_producer.stop()
    await redis.aclose()
    await engine.dispose()
    log.info("service.shutdown", service="fraud-service")


app = FastAPI(
    title="fraud-service",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
)

app.add_middleware(LogSanitiserMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else [],
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Include service-specific routers
from routers import __all__ as router_modules  # noqa: E402  (populated by each service)
for router in router_modules:
    app.include_router(router, prefix="/v1")


@app.get("/health", tags=["ops"])
async def health():
    return {
        "status": "ok",
        "service": settings.SERVICE_NAME,
        "version": "0.1.0",
        "uptime_seconds": round(time.time() - _start_time, 1),
    }
