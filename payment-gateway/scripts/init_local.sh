#!/usr/bin/env bash
set -euo pipefail

SERVICES=(
  "payment-service:8010"
  "merchant-service:8012"
  "fraud-service:8013"
  "upi-service:8014"
  "settlement-service:8015"
  "refund-service:8016"
  "notification-service:8017"
  "kyc-service:8018"
  "netbanking-service:8019"
  "audit-service:8024"
)

MIGRATION_SERVICES=(
  merchant-service
  payment-service
  upi-service
  settlement-service
  refund-service
  audit-service
  notification-service
  fraud-service
)

wait_for_health() {
  local name=$1
  local port=$2
  local max_attempts=30
  local attempt=0

  echo "⏳ Waiting for ${name} to be healthy..."
  until curl -sf "http://localhost:${port}/health" > /dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ $attempt -ge $max_attempts ]; then
      echo "❌ ${name} failed to become healthy after ${max_attempts} attempts"
      exit 1
    fi
    sleep 5
  done
  echo "✓ ${name} is healthy"
}

echo ""
echo "══════════════════════════════════════════════════"
echo "  Payment Gateway — Local Init"
echo "══════════════════════════════════════════════════"
echo ""

# Wait for postgres
echo "⏳ Waiting for postgres-main..."
until docker compose exec -T postgres-main pg_isready -U "${POSTGRES_USER:-pguser}" > /dev/null 2>&1; do
  sleep 2
done
echo "✓ postgres-main ready"

# Wait for redis
echo "⏳ Waiting for redis..."
until docker compose exec -T redis redis-cli ping > /dev/null 2>&1; do
  sleep 2
done
echo "✓ redis ready"

# Wait for redpanda
echo "⏳ Waiting for redpanda..."
until docker compose exec -T redpanda rpk cluster health 2>/dev/null | grep -q "Healthy:.*true"; do
  sleep 3
done
echo "✓ redpanda ready"

# Run migrations
echo ""
echo "── Running migrations ──────────────────────────────"
for svc in "${MIGRATION_SERVICES[@]}"; do
  echo "  → ${svc}"
  docker compose exec -T "${svc}" alembic upgrade head || echo "    ⚠ ${svc} migration failed (may already be current)"
done

# Wait for all services healthy
echo ""
echo "── Waiting for services ────────────────────────────"
for entry in "${SERVICES[@]}"; do
  name="${entry%%:*}"
  port="${entry##*:}"
  wait_for_health "$name" "$port"
done

# Seed
echo ""
echo "── Seeding data ────────────────────────────────────"
docker compose exec -T payment-service python -m scripts.seed_db

# Summary
echo ""
echo "══════════════════════════════════════════════════"
echo "  ✓ Local environment ready!"
echo "══════════════════════════════════════════════════"
echo ""
printf "  %-28s %s\n" "SERVICE" "URL"
printf "  %-28s %s\n" "──────────────────────────" "──────────────────────────"
printf "  %-28s %s\n" "Payment API"       "http://localhost:8010"
printf "  %-28s %s\n" "Merchant API"      "http://localhost:8012"
printf "  %-28s %s\n" "UPI API"           "http://localhost:8014"
printf "  %-28s %s\n" "Keycloak"          "http://localhost/auth"
printf "  %-28s %s\n" "Grafana"           "http://localhost/monitor"
printf "  %-28s %s\n" "Prometheus"        "http://localhost:9090"
echo ""
