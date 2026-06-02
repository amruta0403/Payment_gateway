from __future__ import annotations

from prometheus_client import Counter, Histogram

FRAUD_DECISIONS = Counter(
    "fraud_decisions_total",
    "Fraud decisions by type",
    ["decision"],
)

SCORING_DURATION = Histogram(
    "fraud_scoring_duration_seconds",
    "End-to-end fraud scoring latency in seconds",
    buckets=[0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0],
)

RULE_HITS = Counter(
    "fraud_rule_hits_total",
    "Count of times each fraud rule fired",
    ["rule_name"],
)
