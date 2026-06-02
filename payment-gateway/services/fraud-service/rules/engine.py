from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from redis.asyncio import Redis

from metrics import RULE_HITS
from schemas.fraud import FraudDecision, ScoringContext, ScoringResult
from shared.cache.redis_client import is_blacklisted, record_velocity

log = structlog.get_logger()

# ── BIN / IP heuristics ───────────────────────────────────────────────────────

# Simplified: Indian IP space covers roughly these prefixes
_INDIAN_IP_PREFIXES = (
    "49.", "103.", "122.", "117.", "106.", "115.", "116.", "182.", "183.",
    "223.", "27.", "14.", "59.", "202.", "203.", "110.", "111.", "112.",
    "113.", "114.", "119.", "120.", "121.", "1.", "2.", "4.", "5.",
)

# High-risk MCC codes
HIGH_RISK_MCC: frozenset[str] = frozenset({"7995", "5912", "5816", "7801", "7802"})

# Known Indian domestic BIN prefixes (first 5 digits) — simplified whitelist
_INDIAN_BIN5: frozenset[str] = frozenset({
    "40959", "40960", "41111", "50891", "50893", "50894",
    "60110", "60850", "65265", "65268",  # RuPay
})


def _is_indian_ip(ip: str) -> bool:
    return any(ip.startswith(p) for p in _INDIAN_IP_PREFIXES)


def _is_international_bin(first6: str) -> bool:
    return first6[:5] not in _INDIAN_BIN5


# ── Rules Engine ──────────────────────────────────────────────────────────────

class RulesEngine:
    def __init__(self, redis: Redis, db=None) -> None:
        self.redis = redis
        self.db = db

    # ── Hard-block rules ──────────────────────────────────────────────────────

    async def check_ip_blacklist(self, ctx: ScoringContext) -> tuple[bool, str]:
        if not ctx.ip_address:
            return False, ""
        hit = await is_blacklisted(self.redis, "ip", ctx.ip_address)
        return bool(hit), "ip_blacklist"

    async def check_card_blacklist(self, ctx: ScoringContext) -> tuple[bool, str]:
        if ctx.card_fingerprint:
            hit = await is_blacklisted(self.redis, "card", ctx.card_fingerprint)
            return bool(hit), "card_blacklist"
        return False, ""

    async def check_velocity_card(self, ctx: ScoringContext) -> tuple[bool, str]:
        if ctx.card_token:
            exceeded = await record_velocity(
                self.redis,
                f"fraud:vel:card:{ctx.card_token}:60",
                60, 3, str(ctx.payment_id),
            )
            return bool(exceeded), "velocity_card_60s"
        return False, ""

    async def check_velocity_ip(self, ctx: ScoringContext) -> tuple[bool, str]:
        exceeded = await record_velocity(
            self.redis,
            f"fraud:vel:ip:{ctx.ip_address}:60",
            60, 10, str(ctx.payment_id),
        )
        return bool(exceeded), "velocity_ip_60s"

    async def check_velocity_email(self, ctx: ScoringContext) -> tuple[bool, str]:
        if ctx.customer_email_hash:
            exceeded = await record_velocity(
                self.redis,
                f"fraud:vel:email:{ctx.customer_email_hash}:3600",
                3600, 5, str(ctx.payment_id),
            )
            return bool(exceeded), "velocity_email_1h"
        return False, ""

    # ── Score rules ───────────────────────────────────────────────────────────

    async def score_international_card(self, ctx: ScoringContext) -> float:
        if (
            ctx.pan_first6
            and _is_international_bin(ctx.pan_first6)
            and _is_indian_ip(ctx.ip_address)
        ):
            return 0.30
        return 0.0

    async def score_odd_hour(self, ctx: ScoringContext) -> float:
        ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
        if 1 <= ist.hour <= 4:
            return 0.10
        return 0.0

    async def score_round_amount(self, ctx: ScoringContext) -> float:
        if ctx.amount in {100_000, 200_000, 500_000, 1_000_000, 2_000_000}:
            return 0.10
        return 0.0

    async def score_new_merchant(self, ctx: ScoringContext) -> float:
        if ctx.merchant_created_at:
            ts = ctx.merchant_created_at
            if ts.tzinfo is not None:
                ts = ts.replace(tzinfo=None)
            age_days = (datetime.utcnow() - ts).days
            if age_days < 7:
                return 0.15
        return 0.0

    async def score_high_risk_mcc(self, ctx: ScoringContext) -> float:
        if ctx.merchant_mcc in HIGH_RISK_MCC:
            return 0.20
        return 0.0

    # ── Rule lists ────────────────────────────────────────────────────────────

    @property
    def HARD_BLOCK_RULES(self) -> list:
        return [
            self.check_ip_blacklist,
            self.check_card_blacklist,
            self.check_velocity_card,
            self.check_velocity_ip,
            self.check_velocity_email,
        ]

    @property
    def SCORE_RULES(self) -> list[tuple]:
        return [
            (self.score_international_card, 1.0),
            (self.score_odd_hour, 1.0),
            (self.score_round_amount, 1.0),
            (self.score_new_merchant, 1.0),
            (self.score_high_risk_mcc, 1.0),
        ]

    # ── Main evaluation ───────────────────────────────────────────────────────

    async def evaluate(self, context: ScoringContext) -> ScoringResult:
        now = datetime.now(timezone.utc)

        # 1. Run ALL hard-block rules concurrently — single asyncio.gather round
        block_results: list[tuple[bool, str]] = await asyncio.gather(
            *[rule(context) for rule in self.HARD_BLOCK_RULES]
        )
        for hit, reason in block_results:
            if hit:
                _fire_hit(reason)
                return ScoringResult(
                    fraud_score=1.0,
                    decision=FraudDecision.BLOCK,
                    reasons=[reason],
                    rule_hits=[reason],
                    evaluated_at=now,
                )

        # 2. Run ALL score rules concurrently
        score_values: list[float] = await asyncio.gather(
            *[rule(context) for rule, _ in self.SCORE_RULES]
        )
        total_score = min(sum(score_values), 1.0)
        rule_hits = [
            self.SCORE_RULES[i][0].__name__
            for i, s in enumerate(score_values)
            if s > 0
        ]

        for name in rule_hits:
            _fire_hit(name)

        # 3. Decision thresholds
        if total_score < 0.30:
            decision = FraudDecision.ALLOW
        elif total_score < 0.70:
            decision = FraudDecision.CHALLENGE
        else:
            decision = FraudDecision.BLOCK

        return ScoringResult(
            fraud_score=total_score,
            decision=decision,
            reasons=rule_hits,
            rule_hits=rule_hits,
            evaluated_at=now,
        )


def _fire_hit(rule_name: str) -> None:
    """Increment Prometheus counter for rule hit — never raises."""
    try:
        RULE_HITS.labels(rule_name=rule_name).inc()
    except Exception:
        pass


# ── Known rule names (for DB seeding) ────────────────────────────────────────

ALL_RULE_NAMES: list[dict] = [
    {"rule_name": "check_ip_blacklist",      "description": "Block transactions from blacklisted IPs", "weight": 1.0},
    {"rule_name": "check_card_blacklist",    "description": "Block transactions using blacklisted cards", "weight": 1.0},
    {"rule_name": "check_velocity_card",     "description": "Block if same card used >3 times in 60s", "weight": 1.0},
    {"rule_name": "check_velocity_ip",       "description": "Block if same IP used >10 times in 60s", "weight": 1.0},
    {"rule_name": "check_velocity_email",    "description": "Block if same email used >5 times in 1h", "weight": 1.0},
    {"rule_name": "score_international_card","description": "Adds 0.30 for intl card on Indian IP", "weight": 1.0},
    {"rule_name": "score_odd_hour",          "description": "Adds 0.10 for transactions 1-4am IST", "weight": 1.0},
    {"rule_name": "score_round_amount",      "description": "Adds 0.10 for round amounts (1L/2L/5L/10L)", "weight": 1.0},
    {"rule_name": "score_new_merchant",      "description": "Adds 0.15 for merchants < 7 days old", "weight": 1.0},
    {"rule_name": "score_high_risk_mcc",     "description": "Adds 0.20 for gambling/pharma MCCs", "weight": 1.0},
]
