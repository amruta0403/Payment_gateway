from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import structlog

from shared.exceptions.handlers import ServiceUnavailableError

log = structlog.get_logger()

_RETRY_DELAYS = (0.5, 1.0)
_RETRYABLE_STATUS = frozenset({500, 502, 503, 504})


class CircuitBreaker:
    """Per-service circuit breaker: open after N consecutive failures, half-open after timeout."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0) -> None:
        self._threshold = failure_threshold
        self._recovery = recovery_timeout
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self._recovery:
            # Half-open: allow the next request through as a probe
            return False
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            if self._opened_at is None:
                log.warning("circuit_breaker.opened", failures=self._failures)
            self._opened_at = time.monotonic()


_breakers: dict[str, CircuitBreaker] = {}


def _breaker_for(base_url: str) -> CircuitBreaker:
    if base_url not in _breakers:
        _breakers[base_url] = CircuitBreaker()
    return _breakers[base_url]


class ServiceClient:
    """
    Async HTTP client for inter-service calls.

    Features:
    - Shared httpx.AsyncClient per request (connection reuse via keep-alive)
    - Automatic retry on 5xx: up to 2 retries with 0.5 s, 1.0 s backoff
    - Per-service circuit breaker: trips after 5 consecutive failures, recovers after 30 s
    - X-Service-Token and X-Trace-ID injected on every request
    """

    def __init__(
        self,
        base_url: str,
        service_token: str,
        trace_id: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._headers: dict[str, str] = {
            "X-Service-Token": service_token,
            "Content-Type": "application/json",
        }
        if trace_id:
            self._headers["X-Trace-ID"] = trace_id
        self._breaker = _breaker_for(self._base_url)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self._breaker.is_open:
            raise ServiceUnavailableError(
                f"Circuit open for {self._base_url} — downstream unavailable"
            )

        url = f"{self._base_url}{path}"
        last_exc: Exception = ServiceUnavailableError(f"Request to {url} failed")

        for attempt, delay in enumerate([0.0, *_RETRY_DELAYS]):
            if attempt > 0:
                log.info("http_client.retry", url=url, attempt=attempt, delay=delay)
                await asyncio.sleep(delay)

            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout,
                    headers=self._headers,
                    follow_redirects=False,
                ) as client:
                    resp = await client.request(method, url, **kwargs)

                if resp.status_code in _RETRYABLE_STATUS:
                    self._breaker.record_failure()
                    last_exc = ServiceUnavailableError(
                        f"{self._base_url} returned {resp.status_code}"
                    )
                    continue

                self._breaker.record_success()

                if resp.status_code >= 400:
                    # 4xx: don't retry, propagate the parsed body
                    try:
                        return resp.json()
                    except Exception:
                        return {"status_code": resp.status_code, "detail": resp.text}

                return resp.json()

            except httpx.TimeoutException as exc:
                self._breaker.record_failure()
                last_exc = ServiceUnavailableError(f"Timeout calling {url}")
                log.warning("http_client.timeout", url=url, attempt=attempt)

            except httpx.RequestError as exc:
                self._breaker.record_failure()
                last_exc = ServiceUnavailableError(str(exc))
                log.warning("http_client.request_error", url=url, error=str(exc))

        raise last_exc

    async def get(self, path: str, **kwargs: Any) -> Any:
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> Any:
        return await self._request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> Any:
        return await self._request("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> Any:
        return await self._request("DELETE", path, **kwargs)
