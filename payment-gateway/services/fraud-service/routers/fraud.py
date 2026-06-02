from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db_session, get_principal
from metrics import FRAUD_DECISIONS, RULE_HITS, SCORING_DURATION
from models.fraud import FraudBlacklist, FraudRule
from schemas.fraud import (
    BlacklistAddRequest,
    FraudDecision,
    RuleResponse,
    ScoringContext,
    ScoringRequest,
    ScoringResult,
)

log = structlog.get_logger()
router = APIRouter(tags=["fraud"])

_ALLOWED_LIST_TYPES = {"ip", "card", "email"}
_BL_REDIS_PREFIX = "bl"  # matches shared.cache.redis_client._BL_PREFIX


def _require_role(principal, *roles: str) -> None:
    proles = getattr(principal, "roles", [])
    if not any(r in proles for r in roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")


def _validate_list_type(list_type: str) -> None:
    if list_type not in _ALLOWED_LIST_TYPES:
        raise HTTPException(status_code=422, detail=f"list_type must be one of {_ALLOWED_LIST_TYPES}")


# ── Hot path: POST /score ─────────────────────────────────────────────────────

@router.post("/score", response_model=ScoringResult)
async def score_transaction(
    body: ScoringRequest,
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Synchronously evaluates fraud risk. MUST complete in < 100ms p95.
    Called by payment-service before processing every transaction.
    """
    t0 = time.perf_counter()
    ctx = ScoringContext(**body.model_dump())
    state = request.app.state
    engine = state.rules_engine
    ml_scorer = state.ml_scorer

    # Start rules evaluation (async, Redis I/O) as a background task,
    # then run ML prediction (sync, CPU) concurrently.
    rules_task = asyncio.create_task(engine.evaluate(ctx))
    ml_score: float = ml_scorer.predict(ctx)   # sync, < 2ms
    rules_result: ScoringResult = await rules_task

    # Hard block from rules — skip ML blend
    if rules_result.decision == FraudDecision.BLOCK:
        _record_metrics(rules_result, t0)
        return rules_result

    # Blend: 60% rules + 40% ML
    blended = 0.6 * rules_result.fraud_score + 0.4 * ml_score

    if blended < 0.30:
        decision = FraudDecision.ALLOW
    elif blended < 0.70:
        decision = FraudDecision.CHALLENGE
    else:
        decision = FraudDecision.BLOCK

    result = ScoringResult(
        fraud_score=round(blended, 4),
        decision=decision,
        reasons=rules_result.reasons,
        rule_hits=rules_result.rule_hits,
        evaluated_at=datetime.now(timezone.utc),
    )
    _record_metrics(result, t0)
    return result


def _record_metrics(result: ScoringResult, t0: float) -> None:
    duration = time.perf_counter() - t0
    try:
        SCORING_DURATION.observe(duration)
        FRAUD_DECISIONS.labels(decision=result.decision.value).inc()
    except Exception:
        pass
    if duration > 0.1:
        log.warning("fraud.scoring.slow", duration_ms=round(duration * 1000, 1))


# ── Admin: blacklist management ───────────────────────────────────────────────

@router.post("/admin/blacklist/{list_type}", status_code=201)
async def add_to_blacklist(
    list_type: str,
    body: BlacklistAddRequest,
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _require_role(principal, "ADMIN", "RISK_ANALYST")
    _validate_list_type(list_type)

    redis = request.app.state.redis
    redis_key = f"{_BL_REDIS_PREFIX}:{list_type}:{body.value}"
    await redis.set(redis_key, "1")

    record = FraudBlacklist(
        list_type=list_type,
        value=body.value,
        created_by=str(getattr(principal, "sub", "unknown")),
        is_active=True,
    )
    db.add(record)
    await db.commit()

    log.info("blacklist.add", list_type=list_type, value=body.value[:20])
    return {"status": "added", "list_type": list_type, "value": body.value}


@router.delete("/admin/blacklist/{list_type}/{value}", status_code=200)
async def remove_from_blacklist(
    list_type: str,
    value: str,
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _require_role(principal, "ADMIN", "RISK_ANALYST")
    _validate_list_type(list_type)

    redis = request.app.state.redis
    redis_key = f"{_BL_REDIS_PREFIX}:{list_type}:{value}"
    await redis.delete(redis_key)

    await db.execute(
        FraudBlacklist.__table__.update()
        .where(
            FraudBlacklist.list_type == list_type,
            FraudBlacklist.value == value,
            FraudBlacklist.is_active.is_(True),
        )
        .values(is_active=False)
    )
    await db.commit()

    log.info("blacklist.remove", list_type=list_type, value=value[:20])
    return {"status": "removed", "list_type": list_type, "value": value}


# ── Admin: rules management ───────────────────────────────────────────────────

@router.get("/admin/rules", response_model=list[RuleResponse])
async def list_rules(
    request: Request,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _require_role(principal, "ADMIN", "RISK_ANALYST")

    rows = (
        await db.execute(select(FraudRule).order_by(FraudRule.created_at))
    ).scalars().all()

    redis = request.app.state.redis

    # Fetch hit counts from Redis in a single pipeline
    pipe = redis.pipeline(transaction=False)
    for r in rows:
        pipe.get(f"fraud:rule_hits:{r.rule_name}")
    hit_counts_raw = await pipe.execute()

    return [
        RuleResponse(
            id=r.id,
            rule_name=r.rule_name,
            is_active=r.is_active,
            description=r.description,
            weight=r.weight,
            hit_count=int(hit_counts_raw[i] or 0),
            created_at=r.created_at,
        )
        for i, r in enumerate(rows)
    ]


@router.post("/admin/rules/{rule_name}/toggle")
async def toggle_rule(
    rule_name: str,
    principal=Depends(get_principal),
    db: AsyncSession = Depends(get_db_session),
):
    _require_role(principal, "ADMIN", "RISK_ANALYST")

    rule = (
        await db.execute(select(FraudRule).where(FraudRule.rule_name == rule_name))
    ).scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    rule.is_active = not rule.is_active
    await db.commit()
    await db.refresh(rule)

    log.info("fraud_rule.toggled", rule_name=rule_name, is_active=rule.is_active)
    return {"rule_name": rule.rule_name, "is_active": rule.is_active}
