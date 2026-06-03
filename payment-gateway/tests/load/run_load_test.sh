#!/usr/bin/env bash
# =============================================================================
# run_load_test.sh — Run Locust load test against fraud-service
#
# Usage:
#   ./tests/load/run_load_test.sh [users] [spawn-rate] [duration]
#
# Defaults:
#   users=50, spawn-rate=10, duration=60s
#
# Examples:
#   ./tests/load/run_load_test.sh                 # 50 users, 60s, headless
#   ./tests/load/run_load_test.sh 100 20 120s     # 100 users, 120s
#   ./tests/load/run_load_test.sh ui              # Interactive web UI mode
# =============================================================================
set -euo pipefail

USERS="${1:-50}"
SPAWN_RATE="${2:-10}"
DURATION="${3:-60s}"
HOST="${FRAUD_SERVICE_URL:-http://localhost:8013}"
RESULTS_DIR="tests/load/results"
LOCUSTFILE="tests/load/locustfile.py"

mkdir -p "$RESULTS_DIR"

if ! command -v locust &>/dev/null; then
  echo "Locust not found. Install: pip install locust"
  exit 1
fi

echo "════════════════════════════════════════════════════"
echo "  Fraud Service Load Test"
echo "  Host:        $HOST"
echo "  Users:       $USERS"
echo "  Spawn rate:  $SPAWN_RATE/s"
echo "  Duration:    $DURATION"
echo "  Results:     $RESULTS_DIR/"
echo "════════════════════════════════════════════════════"

if [[ "${1:-}" == "ui" ]]; then
  echo "Starting Locust web UI at http://localhost:8089 ..."
  locust -f "$LOCUSTFILE" \
    --host "$HOST" \
    --web-port 8089
else
  locust -f "$LOCUSTFILE" \
    --host "$HOST" \
    --users "$USERS" \
    --spawn-rate "$SPAWN_RATE" \
    --run-time "$DURATION" \
    --headless \
    --csv "$RESULTS_DIR/fraud_score_$(date +%Y%m%d_%H%M%S)" \
    --html "$RESULTS_DIR/report_$(date +%Y%m%d_%H%M%S).html" \
    --exit-code-on-error 1

  echo ""
  echo "Load test complete. Results in $RESULTS_DIR/"
fi
