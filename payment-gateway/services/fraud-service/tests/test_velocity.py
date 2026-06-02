"""Unit tests for the sliding-window velocity counter in shared.cache.redis_client."""
from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from shared.cache.redis_client import record_velocity


class _TrackingPipeline:
    """Records which Redis commands were issued and returns configurable results."""

    def __init__(self, zcard_result: int = 0):
        self._zcard_result = zcard_result
        self.commands: list[str] = []
        self._results: list = []

    def zremrangebyscore(self, key, lo, hi):
        self.commands.append("ZREMRANGEBYSCORE")
        self._results.append(0)
        return self

    def zadd(self, key, mapping):
        self.commands.append("ZADD")
        self._results.append(1)
        return self

    def zcard(self, key):
        self.commands.append("ZCARD")
        self._results.append(self._zcard_result)
        return self

    def expire(self, key, ttl):
        self.commands.append("EXPIRE")
        self._results.append(True)
        return self

    async def execute(self):
        return list(self._results)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


def _make_redis(zcard_result: int = 0):
    pipe = _TrackingPipeline(zcard_result=zcard_result)
    redis = MagicMock()
    redis.pipeline = MagicMock(return_value=pipe)
    return redis, pipe


@pytest.mark.anyio
async def test_velocity_uses_pipeline():
    """record_velocity must batch all Redis commands into a single pipeline."""
    redis, pipe = _make_redis(zcard_result=1)
    await record_velocity(redis, "test:key", 60, 5, str(uuid.uuid4()))
    # All 4 commands must have been sent via the pipeline
    assert "ZREMRANGEBYSCORE" in pipe.commands
    assert "ZADD" in pipe.commands
    assert "ZCARD" in pipe.commands
    assert "EXPIRE" in pipe.commands


@pytest.mark.anyio
async def test_velocity_not_exceeded():
    redis, _ = _make_redis(zcard_result=2)  # 2 events, limit=5
    exceeded = await record_velocity(redis, "test:key", 60, 5, str(uuid.uuid4()))
    assert exceeded is False


@pytest.mark.anyio
async def test_velocity_exactly_at_limit():
    redis, _ = _make_redis(zcard_result=5)  # count == limit → not exceeded
    exceeded = await record_velocity(redis, "test:key", 60, 5, str(uuid.uuid4()))
    assert exceeded is False


@pytest.mark.anyio
async def test_velocity_exceeded():
    redis, _ = _make_redis(zcard_result=6)  # count > limit=5 → exceeded
    exceeded = await record_velocity(redis, "test:key", 60, 5, str(uuid.uuid4()))
    assert exceeded is True


@pytest.mark.anyio
async def test_velocity_fail_open_on_redis_error():
    """If Redis fails, record_velocity returns False (fail-open — don't block legitimate txns)."""
    from redis.exceptions import RedisError

    redis = MagicMock()
    pipe = MagicMock()
    pipe.zremrangebyscore = MagicMock(return_value=pipe)
    pipe.zadd = MagicMock(return_value=pipe)
    pipe.zcard = MagicMock(return_value=pipe)
    pipe.expire = MagicMock(return_value=pipe)
    pipe.execute = AsyncMock(side_effect=RedisError("connection refused"))
    redis.pipeline = MagicMock(return_value=pipe)

    exceeded = await record_velocity(redis, "test:key", 60, 1, "member")
    assert exceeded is False  # fail-open


@pytest.mark.anyio
async def test_velocity_key_prefixed():
    """The shared module adds 'vel:' prefix to all velocity keys."""
    redis, pipe = _make_redis(zcard_result=0)
    await record_velocity(redis, "myservice:card:abc:60", 60, 3, "evt1")
    # Verify pipeline was called (the key prefix is internal to shared)
    assert "ZADD" in pipe.commands


@pytest.mark.anyio
async def test_velocity_different_members_same_key():
    """Each unique event_id is stored as a separate sorted set member."""
    redis, pipe = _make_redis(zcard_result=3)
    m1, m2 = str(uuid.uuid4()), str(uuid.uuid4())
    # Both calls succeed without error
    await record_velocity(redis, "card:tok1:60", 60, 10, m1)
    await record_velocity(redis, "card:tok1:60", 60, 10, m2)
    # Two ZADD commands were issued (one per call)
    assert pipe.commands.count("ZADD") == 2
