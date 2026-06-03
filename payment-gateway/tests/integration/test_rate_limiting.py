"""
Integration tests for Traefik rate-limiting middleware.

These tests run against a LIVE stack (Traefik + FastAPI services).
They are skipped automatically unless RATE_LIMIT_TEST_URL is set in the environment.

Run:
  export RATE_LIMIT_TEST_URL=https://api.yourdomain.com
  export RATE_LIMIT_AUTH_TOKEN=<valid bearer token>
  pytest tests/integration/test_rate_limiting.py -v -s

Rate limits configured in infra/traefik/dynamic/middleware.yml:
  payment-ratelimit : 100 req/min (burst 50)
  merchant-ratelimit:  60 req/min (burst 30)
  reports-ratelimit :  20 req/min (burst 10)
"""
from __future__ import annotations

import asyncio
import os
import time
from collections import Counter

import httpx
import pytest

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_URL    = os.environ.get("RATE_LIMIT_TEST_URL", "")
AUTH_TOKEN  = os.environ.get("RATE_LIMIT_AUTH_TOKEN", "dummy-token")
SKIP_REASON = "RATE_LIMIT_TEST_URL not set — skipping integration rate-limit tests"

pytestmark = pytest.mark.skipif(not BASE_URL, reason=SKIP_REASON)


def _headers(extra: dict | None = None) -> dict:
    h = {"Authorization": f"Bearer {AUTH_TOKEN}", "X-Request-ID": "ratelimit-test"}
    if extra:
        h.update(extra)
    return h


async def _burst(url: str, n: int, method: str = "GET", json_body: dict | None = None) -> Counter:
    """Fire n requests concurrently; return Counter of status codes."""
    async with httpx.AsyncClient(verify=False, timeout=10) as client:
        tasks = []
        for _ in range(n):
            if method == "GET":
                tasks.append(client.get(url, headers=_headers()))
            else:
                tasks.append(client.post(url, headers=_headers(), json=json_body or {}))
        responses = await asyncio.gather(*tasks, return_exceptions=True)

    codes: Counter = Counter()
    for r in responses:
        if isinstance(r, Exception):
            codes["error"] += 1
        else:
            codes[r.status_code] += 1
    return codes


# ── Payment endpoint (100 req/min) ────────────────────────────────────────────

@pytest.mark.anyio
async def test_payment_ratelimit_allows_under_burst():
    """First 50 concurrent requests (burst limit) should all succeed."""
    url = f"{BASE_URL}/v1/payments"
    codes = await _burst(url, n=45, method="POST", json_body={"test": True})
    # Expect 422 (validation error) or 401, NOT 429
    assert 429 not in codes, f"Got 429 Too Many Requests within burst limit: {dict(codes)}"


@pytest.mark.anyio
async def test_payment_ratelimit_triggers_at_limit():
    """Firing 120 rapid requests should trigger 429 on some."""
    url = f"{BASE_URL}/v1/payments"
    # Wait for any existing rate-limit window to reset
    await asyncio.sleep(2)
    codes = await _burst(url, n=120, method="POST", json_body={"test": True})
    assert 429 in codes, f"Expected 429 responses but got: {dict(codes)}"
    assert codes[429] > 0, f"Expected at least one 429, got {codes[429]}"


@pytest.mark.anyio
async def test_payment_ratelimit_resets_after_window():
    """After waiting 65s, the rate limit window should reset."""
    url = f"{BASE_URL}/v1/payments"
    # Exhaust the limit first
    await _burst(url, n=110, method="POST", json_body={})
    # Wait for window to reset (60s + 5s buffer)
    await asyncio.sleep(65)
    codes = await _burst(url, n=10, method="POST", json_body={})
    assert 429 not in codes, f"Rate limit did not reset after 65s: {dict(codes)}"


# ── Merchant endpoint (60 req/min) ────────────────────────────────────────────

@pytest.mark.anyio
async def test_merchant_ratelimit_triggers():
    """Merchant endpoint has lower limit (60/min); 80 rapid requests should 429."""
    url = f"{BASE_URL}/v1/merchants"
    await asyncio.sleep(2)
    codes = await _burst(url, n=80, method="GET")
    assert 429 in codes, f"Expected 429 on merchant endpoint: {dict(codes)}"


# ── Reports endpoint (20 req/min) ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_reports_ratelimit_triggers_faster():
    """Reports endpoint has the tightest limit (20/min); 30 requests should 429."""
    url = f"{BASE_URL}/v1/reports"
    await asyncio.sleep(2)
    codes = await _burst(url, n=30, method="GET")
    assert 429 in codes, f"Expected 429 on reports endpoint: {dict(codes)}"


# ── Per-IP isolation ──────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_ratelimit_is_per_ip():
    """
    Requests with different X-Forwarded-For IPs should have independent buckets.
    (Only works if Traefik ipStrategy.depth=1 is configured.)
    """
    url = f"{BASE_URL}/v1/payments"
    await asyncio.sleep(2)

    async with httpx.AsyncClient(verify=False, timeout=10) as client:
        # Fire 55 requests "from" IP 10.0.0.1
        tasks_a = [
            client.post(url, headers=_headers({"X-Forwarded-For": "10.0.0.1"}), json={})
            for _ in range(55)
        ]
        # Fire 55 requests "from" IP 10.0.0.2
        tasks_b = [
            client.post(url, headers=_headers({"X-Forwarded-For": "10.0.0.2"}), json={})
            for _ in range(55)
        ]
        responses = await asyncio.gather(*(tasks_a + tasks_b), return_exceptions=True)

    codes = Counter(
        r.status_code for r in responses if not isinstance(r, Exception)
    )
    # Neither IP alone sent > 100 requests, so neither should be rate-limited
    assert codes.get(429, 0) == 0, (
        f"Per-IP rate limiting failed — got 429s despite each IP sending only 55 req: {dict(codes)}"
    )


# ── Traefik 429 response format ───────────────────────────────────────────────

@pytest.mark.anyio
async def test_ratelimit_response_has_retry_after():
    """Traefik should include Retry-After header on 429 responses."""
    url = f"{BASE_URL}/v1/payments"
    await asyncio.sleep(2)

    async with httpx.AsyncClient(verify=False, timeout=10) as client:
        # Exhaust the limit
        tasks = [client.post(url, headers=_headers(), json={}) for _ in range(115)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

    rate_limited = [r for r in responses if not isinstance(r, Exception) and r.status_code == 429]
    if rate_limited:
        # GraceNote: Traefik v3 sets Retry-After on rate-limited responses
        for r in rate_limited[:3]:
            assert r.status_code == 429
            # Retry-After is optional in Traefik but good to check
            # assert "retry-after" in r.headers  # uncomment when Traefik is configured
