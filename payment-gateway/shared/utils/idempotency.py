from __future__ import annotations

import json

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

log = structlog.get_logger()


class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, redis) -> None:
        super().__init__(app)
        self._redis = redis

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method != "POST":
            return await call_next(request)

        idempotency_key = request.headers.get("X-Idempotency-Key")
        if not idempotency_key:
            return await call_next(request)

        merchant_id = getattr(request.state, "merchant_id", "anonymous")

        from shared.cache.redis_client import get_idempotency, set_idempotency

        cached = await get_idempotency(self._redis, merchant_id, idempotency_key)
        if cached is not None:
            log.info(
                "idempotency.cache_hit",
                key=idempotency_key,
                merchant_id=merchant_id,
            )
            return JSONResponse(
                content=cached["body"],
                status_code=cached["status_code"],
                headers={"X-Idempotency-Replayed": "true"},
            )

        response = await call_next(request)

        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        if 200 <= response.status_code < 300:
            try:
                body_json = json.loads(body)
                await set_idempotency(
                    self._redis,
                    merchant_id,
                    idempotency_key,
                    {"body": body_json, "status_code": response.status_code},
                )
            except Exception as exc:
                log.warning("idempotency.cache_write_error", error=str(exc))

        return Response(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
