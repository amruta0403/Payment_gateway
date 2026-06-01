from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from typing import Any, Literal

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

log = structlog.get_logger()

_IDEM_PREFIX = "idem"
_RATE_PREFIX = "rate"
_VEL_PREFIX = "vel"
_BL_PREFIX = "bl"
_CACHE_PREFIX = "cache"
_TOKEN_BL_PREFIX = "token_bl"
_LOCK_PREFIX = "lock"


def _idem_key(merchant_id: str, key: str) -> str:
    return f"{_IDEM_PREFIX}:{merchant_id}:{key}"


async def get_idempotency(redis: Redis, merchant_id: str, key: str) -> dict | None:
    try:
        raw = await redis.get(_idem_key(merchant_id, key))
        if raw:
            return json.loads(raw)
        return None
    except RedisError as exc:
        log.warning("redis.get_idempotency.error", error=str(exc))
        return None


async def set_idempotency(
    redis: Redis,
    merchant_id: str,
    key: str,
    response: dict,
    ttl: int = 86400,
) -> None:
    try:
        await redis.setex(_idem_key(merchant_id, key), ttl, json.dumps(response))
    except RedisError as exc:
        log.warning("redis.set_idempotency.error", error=str(exc))


async def check_rate_limit(
    redis: Redis,
    identifier: str,
    endpoint: str,
    limit: int,
    window: int = 60,
) -> tuple[bool, int]:
    key = f"{_RATE_PREFIX}:{endpoint}:{identifier}"
    try:
        pipe = redis.pipeline()
        await pipe.incr(key)
        await pipe.expire(key, window)
        count, _ = await pipe.execute()
        return count > limit, int(count)
    except RedisError as exc:
        log.warning("redis.rate_limit.error", error=str(exc))
        return False, 0


async def record_velocity(
    redis: Redis,
    key: str,
    window_seconds: int,
    max_count: int,
    member: str,
) -> bool:
    full_key = f"{_VEL_PREFIX}:{key}"
    now_ms = int(time.time() * 1000)
    cutoff_ms = now_ms - (window_seconds * 1000)
    try:
        pipe = redis.pipeline()
        await pipe.zremrangebyscore(full_key, "-inf", cutoff_ms)
        await pipe.zadd(full_key, {member: now_ms})
        await pipe.zcard(full_key)
        await pipe.expire(full_key, window_seconds + 5)
        results = await pipe.execute()
        count = results[2]
        return count > max_count
    except RedisError as exc:
        log.warning("redis.velocity.error", error=str(exc))
        return False


def _bl_key(list_type: str, value: str) -> str:
    return f"{_BL_PREFIX}:{list_type}:{value}"


async def is_blacklisted(
    redis: Redis,
    list_type: Literal["ip", "card", "email"],
    value: str,
) -> bool:
    try:
        return bool(await redis.exists(_bl_key(list_type, value)))
    except RedisError as exc:
        log.warning("redis.blacklist.check.error", error=str(exc))
        return False


async def add_to_blacklist(
    redis: Redis,
    list_type: Literal["ip", "card", "email"],
    value: str,
    ttl: int | None = None,
) -> None:
    try:
        key = _bl_key(list_type, value)
        await redis.set(key, "1")
        if ttl:
            await redis.expire(key, ttl)
    except RedisError as exc:
        log.warning("redis.blacklist.add.error", error=str(exc))


async def cache_get(redis: Redis, key: str) -> Any | None:
    try:
        raw = await redis.get(f"{_CACHE_PREFIX}:{key}")
        if raw:
            return json.loads(raw)
        return None
    except RedisError as exc:
        log.warning("redis.cache_get.error", error=str(exc))
        return None


async def cache_set(redis: Redis, key: str, value: Any, ttl: int = 300) -> None:
    try:
        await redis.setex(f"{_CACHE_PREFIX}:{key}", ttl, json.dumps(value))
    except RedisError as exc:
        log.warning("redis.cache_set.error", error=str(exc))


async def revoke_token(redis: Redis, jti: str, ttl_seconds: int) -> None:
    try:
        await redis.setex(f"{_TOKEN_BL_PREFIX}:{jti}", ttl_seconds, "1")
    except RedisError as exc:
        log.warning("redis.revoke_token.error", error=str(exc))


async def is_token_revoked(redis: Redis, jti: str) -> bool:
    try:
        return bool(await redis.exists(f"{_TOKEN_BL_PREFIX}:{jti}"))
    except RedisError as exc:
        log.warning("redis.is_token_revoked.error", error=str(exc))
        return False


@asynccontextmanager
async def acquire_lock(redis: Redis, key: str, ttl: int = 30):
    lock_key = f"{_LOCK_PREFIX}:{key}"
    acquired = False
    try:
        acquired = bool(await redis.set(lock_key, "1", nx=True, ex=ttl))
        yield acquired
    except RedisError as exc:
        log.warning("redis.lock.error", error=str(exc))
        yield False
    finally:
        if acquired:
            try:
                await redis.delete(lock_key)
            except RedisError:
                pass
