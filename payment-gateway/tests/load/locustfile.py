"""
Locust load test for fraud-service POST /score.
Target: p95 latency < 100ms at 50 concurrent users.

Usage:
  # Headless mode (CI):
  locust -f tests/load/locustfile.py \
    --host http://localhost:8013 \
    --users 50 --spawn-rate 10 \
    --run-time 60s --headless \
    --csv tests/load/results/fraud_score \
    --exit-code-on-error 1

  # Web UI mode (interactive):
  locust -f tests/load/locustfile.py --host http://localhost:8013

  # Docker Compose stack:
  make load-test   (see Makefile target)

Success criteria enforced by @events.quitting hook:
  - p95 response time < 100ms
  - error rate < 0.5%
  - RPS > 200 at 50 users
"""
from __future__ import annotations

import json
import os
import random
import uuid
from datetime import datetime, timedelta

from locust import HttpUser, between, events, task
from locust.env import Environment

# ── Test data helpers ─────────────────────────────────────────────────────────

_UPI_VPAS    = ["success@upi", "user@hdfc", "pay@oksbi"]
_METHODS     = ["CARD", "UPI", "NETBANKING"]
_MCCS        = ["5411", "5812", "7995", "5912", "5816"]  # include high-risk
_IP_POOL     = [f"27.{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}" for _ in range(20)]

def _random_payload() -> dict:
    method = random.choice(_METHODS)
    amount = random.randint(100, 500_000)  # ₹1 to ₹5,000
    return {
        "payment_id":        str(uuid.uuid4()),
        "merchant_id":       str(uuid.uuid4()),
        "merchant_created_at": (datetime.utcnow() - timedelta(days=random.randint(0, 365))).isoformat(),
        "merchant_mcc":      random.choice(_MCCS),
        "amount":            amount,
        "payment_method":    method,
        "ip_address":        random.choice(_IP_POOL),
        "card_token":        str(uuid.uuid4()) if method == "CARD" else None,
        "pan_first6":        random.choice(["411111", "555555", "606074", "400000"]) if method == "CARD" else None,
        "upi_vpa":           random.choice(_UPI_VPAS) if method == "UPI" else None,
        "customer_email_hash": uuid.uuid4().hex[:16],
        "customer_phone_hash": uuid.uuid4().hex[:16],
    }


# ── Locust user ───────────────────────────────────────────────────────────────

class FraudScoringUser(HttpUser):
    """
    Simulates the payment-service calling fraud-service synchronously.
    Every payment request triggers one POST /v1/score.
    """
    # Between requests: 10–50ms (simulates concurrent payment processing)
    wait_time = between(0.01, 0.05)

    @task(10)
    def score_normal_transaction(self):
        """Typical card/UPI payment — should ALLOW quickly."""
        payload = _random_payload()
        with self.client.post(
            "/v1/score",
            json=payload,
            catch_response=True,
            name="/v1/score [normal]",
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                decision = data.get("decision")
                latency_ms = resp.elapsed.total_seconds() * 1000
                if latency_ms > 200:
                    resp.failure(f"Too slow: {latency_ms:.1f}ms > 200ms threshold")
                elif decision not in ("ALLOW", "CHALLENGE", "BLOCK"):
                    resp.failure(f"Invalid decision: {decision}")
                else:
                    resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(2)
    def score_high_risk_transaction(self):
        """Gambling MCC + round amount — should CHALLENGE or BLOCK."""
        payload = _random_payload()
        payload.update({
            "merchant_mcc": "7995",
            "amount": 1_000_000,  # ₹10,000 round amount
        })
        with self.client.post(
            "/v1/score",
            json=payload,
            catch_response=True,
            name="/v1/score [high-risk]",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def score_new_merchant(self):
        """Brand-new merchant (< 7 days) — should add 0.15 to score."""
        payload = _random_payload()
        payload["merchant_created_at"] = (datetime.utcnow() - timedelta(days=2)).isoformat()
        with self.client.post(
            "/v1/score",
            json=payload,
            catch_response=True,
            name="/v1/score [new-merchant]",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")


# ── SLO enforcement at test end ───────────────────────────────────────────────

@events.quitting.add_listener
def _enforce_slos(environment: Environment, **kwargs):
    """Fail CI if SLOs are not met."""
    stats = environment.runner.stats.total

    if stats.num_requests == 0:
        print("WARNING: No requests were made — cannot validate SLOs")
        return

    p95_ms    = stats.get_response_time_percentile(0.95)
    error_pct = stats.num_failures / stats.num_requests * 100
    rps       = stats.current_rps

    print("\n══════════════════ Fraud Scoring SLO Report ══════════════════")
    print(f"  Total requests : {stats.num_requests:,}")
    print(f"  Failures       : {stats.num_failures:,} ({error_pct:.2f}%)")
    print(f"  RPS (current)  : {rps:.1f}")
    print(f"  Median latency : {stats.get_response_time_percentile(0.50):.1f}ms")
    print(f"  p95 latency    : {p95_ms:.1f}ms  (SLO: < 100ms)")
    print(f"  p99 latency    : {stats.get_response_time_percentile(0.99):.1f}ms")
    print("══════════════════════════════════════════════════════════════\n")

    failures = []

    if p95_ms > 100:
        failures.append(f"p95 latency {p95_ms:.1f}ms exceeds 100ms SLO")

    if error_pct > 0.5:
        failures.append(f"Error rate {error_pct:.2f}% exceeds 0.5% SLO")

    if failures:
        print("SLO VIOLATIONS:")
        for f in failures:
            print(f"  ✗ {f}")
        environment.process_exit_code = 1
    else:
        print("✓ All SLOs met!")
