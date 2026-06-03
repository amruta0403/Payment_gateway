"""Shared httpx client for all proxy calls to microservices."""
from __future__ import annotations

import httpx
import structlog

log = structlog.get_logger()

_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


async def proxy_get(base_url: str, path: str, token: str, params: dict | None = None) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, headers=_auth_headers(token), params=params)
        resp.raise_for_status()
        return resp.json()


async def proxy_post(base_url: str, path: str, token: str, body: dict | None = None) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, headers=_auth_headers(token), json=body)
        resp.raise_for_status()
        return resp.json()


async def proxy_delete(base_url: str, path: str, token: str) -> int:
    url = f"{base_url.rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.delete(url, headers=_auth_headers(token))
        return resp.status_code


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
