from __future__ import annotations

import time
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers.dashboard import router as dashboard_router
from routers.proxy import router as proxy_router

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)
log = structlog.get_logger()
_start = time.time()

app = FastAPI(
    title="Payment Gateway — Dashboard BFF",
    version="1.0.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard_router)
app.include_router(proxy_router)


@app.get("/health")
async def health():
    return {"status": "ok", "uptime": round(time.time() - _start, 1)}
