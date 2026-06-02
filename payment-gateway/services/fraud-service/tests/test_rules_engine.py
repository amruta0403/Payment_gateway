"""Unit tests for the RulesEngine — no HTTP, mock Redis."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from rules.engine import RulesEngine
from schemas.fraud import FraudDecision, ScoringContext


def _ctx(**kwargs) -> ScoringContext:
    defaults = {
        "payment_id": uuid.uuid4(),
        "merchant_id": uuid.uuid4(),
        "amount": 50000,
        "payment_method": "CARD",
        "ip_address": "27.1.2.3",
        "pan_first6": "411111",
        "card_token": uuid.uuid4(),
        "customer_email_hash": "hash123",
        "merchant_created_at": None,
        "merchant_mcc": None,
    }
    defaults.update(kwargs)
    return ScoringContext(**defaults)


def _engine_with_redis(redis) -> RulesEngine:
    return RulesEngine(redis=redis)


def _redis_clean():
    """Returns mock Redis that returns 'not blacklisted, velocity ok'."""
    from tests.conftest import _MockPipeline, _make_mock_redis
    return _make_mock_redis()


# ── Hard-block rule tests ─────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_ip_blacklist_blocks():
    redis = _redis_clean()
    redis.exists = AsyncMock(return_value=True)  # blacklisted
    engine = _engine_with_redis(redis)
    hit, reason = await engine.check_ip_blacklist(_ctx(ip_address="1.2.3.4"))
    assert hit is True
    assert reason == "ip_blacklist"


@pytest.mark.anyio
async def test_ip_blacklist_clean():
    redis = _redis_clean()
    redis.exists = AsyncMock(return_value=False)
    engine = _engine_with_redis(redis)
    hit, _ = await engine.check_ip_blacklist(_ctx(ip_address="1.2.3.4"))
    assert hit is False


@pytest.mark.anyio
async def test_card_blacklist_blocks():
    redis = _redis_clean()
    redis.exists = AsyncMock(return_value=True)
    engine = _engine_with_redis(redis)
    hit, reason = await engine.check_card_blacklist(_ctx(card_fingerprint="fp_abc"))
    assert hit is True
    assert reason == "card_blacklist"


@pytest.mark.anyio
async def test_card_blacklist_no_fingerprint():
    engine = _engine_with_redis(_redis_clean())
    hit, _ = await engine.check_card_blacklist(_ctx(card_fingerprint=None))
    assert hit is False


@pytest.mark.anyio
async def test_velocity_card_exceeded():
    from tests.conftest import _MockPipeline

    class ExceededPipeline(_MockPipeline):
        def zcard(self, *a, **kw):
            self._results.append(10)  # > limit of 3
            return self

    redis = _redis_clean()
    redis.pipeline = MagicMock(return_value=ExceededPipeline())
    engine = _engine_with_redis(redis)
    hit, reason = await engine.check_velocity_card(_ctx())
    assert hit is True
    assert reason == "velocity_card_60s"


@pytest.mark.anyio
async def test_velocity_card_ok():
    engine = _engine_with_redis(_redis_clean())  # zcard returns 0
    hit, _ = await engine.check_velocity_card(_ctx())
    assert hit is False


@pytest.mark.anyio
async def test_velocity_ip_exceeded():
    from tests.conftest import _MockPipeline

    class ExceededPipeline(_MockPipeline):
        def zcard(self, *a, **kw):
            self._results.append(20)  # > limit of 10
            return self

    redis = _redis_clean()
    redis.pipeline = MagicMock(return_value=ExceededPipeline())
    engine = _engine_with_redis(redis)
    hit, reason = await engine.check_velocity_ip(_ctx())
    assert hit is True
    assert reason == "velocity_ip_60s"


# ── Score rule tests ──────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_score_round_amount():
    engine = _engine_with_redis(_redis_clean())
    score = await engine.score_round_amount(_ctx(amount=1_000_000))
    assert score == 0.10


@pytest.mark.anyio
async def test_score_non_round_amount():
    engine = _engine_with_redis(_redis_clean())
    score = await engine.score_round_amount(_ctx(amount=54321))
    assert score == 0.0


@pytest.mark.anyio
async def test_score_new_merchant():
    from datetime import timedelta
    engine = _engine_with_redis(_redis_clean())
    new_ts = datetime.utcnow() - timedelta(days=2)
    score = await engine.score_new_merchant(_ctx(merchant_created_at=new_ts))
    assert score == 0.15


@pytest.mark.anyio
async def test_score_old_merchant():
    from datetime import timedelta
    engine = _engine_with_redis(_redis_clean())
    old_ts = datetime.utcnow() - timedelta(days=100)
    score = await engine.score_new_merchant(_ctx(merchant_created_at=old_ts))
    assert score == 0.0


@pytest.mark.anyio
async def test_score_high_risk_mcc():
    engine = _engine_with_redis(_redis_clean())
    score = await engine.score_high_risk_mcc(_ctx(merchant_mcc="7995"))
    assert score == 0.20


@pytest.mark.anyio
async def test_score_safe_mcc():
    engine = _engine_with_redis(_redis_clean())
    score = await engine.score_high_risk_mcc(_ctx(merchant_mcc="5411"))
    assert score == 0.0


# ── Full evaluate tests ───────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_evaluate_allow_clean_transaction():
    engine = _engine_with_redis(_redis_clean())
    result = await engine.evaluate(_ctx(
        amount=5000,
        merchant_mcc="5411",
        merchant_created_at=None,
    ))
    assert result.decision == FraudDecision.ALLOW
    assert result.fraud_score < 0.30


@pytest.mark.anyio
async def test_evaluate_block_on_blacklist():
    redis = _redis_clean()
    redis.exists = AsyncMock(return_value=True)
    engine = _engine_with_redis(redis)
    result = await engine.evaluate(_ctx(ip_address="1.2.3.4"))
    assert result.decision == FraudDecision.BLOCK
    assert result.fraud_score == 1.0
    assert len(result.rule_hits) == 1


@pytest.mark.anyio
async def test_evaluate_challenge_medium_score():
    from datetime import timedelta
    engine = _engine_with_redis(_redis_clean())
    # new merchant (0.15) + high-risk MCC (0.20) + round amount (0.10) = 0.45
    result = await engine.evaluate(_ctx(
        amount=1_000_000,
        merchant_mcc="7995",
        merchant_created_at=datetime.utcnow() - timedelta(days=2),
    ))
    assert result.decision == FraudDecision.CHALLENGE
    assert 0.30 <= result.fraud_score < 0.70
