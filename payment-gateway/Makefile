# ─────────────────────────────────────────────────────────────────────────────
# Payment Gateway Makefile
# Target: Oracle Cloud ARM A1 (Ubuntu 22.04, 4 CPU, 24 GB RAM)
# Usage:  make [target] [s=SERVICE_NAME]
# ─────────────────────────────────────────────────────────────────────────────

.PHONY: up up-prod down restart build build-all ps fresh \
        logs tail logs-all shell exec health wait-healthy \
        migrate migrate-all revision alembic-current \
        test test-cov test-all seed setup-keycloak init \
        infra-up infra-down topics topic-tail \
        celery-status run-settlement scale-settlement scale-notification \
        rbi-report load-test test-rate-limits help

COMPOSE      := docker compose
COMPOSE_PROD := docker compose -f docker-compose.yml
ENV_FILE     := .env

APP_SERVICES := payment-service card-vault-service merchant-service \
                fraud-service upi-service settlement-service refund-service \
                notification-service kyc-service netbanking-service \
                transaction-service webhook-service reporting-service audit-service

MIGRATE_SERVICES := merchant-service payment-service upi-service \
                    settlement-service refund-service audit-service \
                    notification-service fraud-service

# ─── Start / Stop ─────────────────────────────────────────────────────────────

## Start all services with dev hot-reload (uses override file)
up:
	$(COMPOSE) up -d
	@echo ""
	@DOMAIN=$$(grep '^DOMAIN' $(ENV_FILE) 2>/dev/null | cut -d= -f2 || echo localhost); \
	echo "  API:      https://api.$$DOMAIN"; \
	echo "  Auth:     https://auth.$$DOMAIN"; \
	echo "  Monitor:  https://monitor.$$DOMAIN"; \
	echo "  Secrets:  https://secrets.$$DOMAIN"; \
	echo "  Errors:   https://errors.$$DOMAIN"

## Start in production mode (no override — no hot-reload, no exposed debug ports)
up-prod:
	$(COMPOSE_PROD) up -d

## Stop all services (keep volumes)
down:
	$(COMPOSE) down

## Restart one service: make restart s=payment-service
restart:
	$(COMPOSE) restart $(s)

## Build one or all images: make build [s=SERVICE]
build:
	$(COMPOSE) build $(s)

## Build all images in parallel
build-all:
	$(COMPOSE) build --parallel

## Show container status
ps:
	$(COMPOSE) ps

## Tear down EVERYTHING including volumes (irreversible data loss)
fresh:
	@echo "WARNING: Deletes all volumes. Press Enter to continue, Ctrl-C to abort."
	@read _
	$(COMPOSE) down -v --remove-orphans
	$(COMPOSE) up -d --build

# ─── Logs ─────────────────────────────────────────────────────────────────────

## Follow logs: make logs s=payment-service
logs:
	$(COMPOSE) logs -f $(s)

## Last 100 lines: make tail s=fraud-service
tail:
	$(COMPOSE) logs --tail=100 $(s)

## Follow all app service logs
logs-all:
	$(COMPOSE) logs -f $(APP_SERVICES)

# ─── Shell ────────────────────────────────────────────────────────────────────

## Open a shell: make shell s=merchant-service
shell:
	$(COMPOSE) exec $(s) bash || $(COMPOSE) exec $(s) sh

## Run a one-off command: make exec s=payment-service cmd="python -V"
exec:
	$(COMPOSE) exec $(s) $(cmd)

# ─── Health ───────────────────────────────────────────────────────────────────

## Poll health endpoints on all FastAPI services
health:
	@echo "Checking service health..."
	@for svc in $(APP_SERVICES); do \
	  result=$$($(COMPOSE) exec -T $$svc curl -sf http://localhost/health 2>/dev/null \
	             || echo '{"status":"unreachable"}'); \
	  printf "  %-30s %s\n" $$svc "$$result"; \
	done

## Block until postgres, redis, redpanda are all healthy
wait-healthy:
	@echo "Waiting for postgres-main..."
	@until $(COMPOSE) exec -T postgres-main pg_isready -U pguser >/dev/null 2>&1; \
	  do sleep 2; done; echo "  postgres-main: ready"
	@echo "Waiting for redis..."
	@until $(COMPOSE) exec -T redis redis-cli ping >/dev/null 2>&1; \
	  do sleep 2; done; echo "  redis: ready"
	@echo "Waiting for redpanda..."
	@until $(COMPOSE) exec -T redpanda rpk cluster health 2>&1 | grep -q "Healthy"; \
	  do sleep 3; done; echo "  redpanda: ready"
	@echo "Infrastructure healthy."

# ─── Migrations ───────────────────────────────────────────────────────────────

## Alembic upgrade head for one service: make migrate s=merchant-service
migrate:
	$(COMPOSE) exec $(s) alembic -c migrations/alembic.ini upgrade head

## Run alembic for ALL services in dependency order
migrate-all: wait-healthy
	@echo "==> GlitchTip schema..."
	-$(COMPOSE) run --rm glitchtip-migrate
	@echo ""
	@for svc in $(MIGRATE_SERVICES); do \
	  echo "==> $$svc..."; \
	  $(COMPOSE) exec -T $$svc alembic -c migrations/alembic.ini upgrade head \
	    && echo "    ✓ $$svc" \
	    || echo "    ✗ $$svc FAILED (check if container is running)"; \
	  echo ""; \
	done
	@echo "All migrations complete."

## Auto-generate a new migration: make revision s=payment-service msg="add index"
revision:
	$(COMPOSE) exec $(s) alembic -c migrations/alembic.ini revision --autogenerate -m "$(msg)"

## Show current migration: make alembic-current s=payment-service
alembic-current:
	$(COMPOSE) exec $(s) alembic -c migrations/alembic.ini current

# ─── Tests ────────────────────────────────────────────────────────────────────

## Run pytest for one service: make test s=fraud-service
test:
	$(COMPOSE) exec $(s) pytest tests/ -v --tb=short

## Run with coverage: make test-cov s=payment-service
test-cov:
	$(COMPOSE) exec $(s) pytest tests/ -v --tb=short --cov=. --cov-report=term-missing

## Run tests for all core services
test-all:
	@failed=""; \
	for svc in payment-service merchant-service fraud-service \
	           upi-service settlement-service; do \
	  echo "==> Testing $$svc..."; \
	  $(COMPOSE) exec -T $$svc pytest tests/ -v --tb=short \
	    && echo "    ✓ $$svc" \
	    || { echo "    ✗ $$svc FAILED"; failed="$$failed $$svc"; }; \
	  echo ""; \
	done; \
	if [ -n "$$failed" ]; then \
	  echo "FAILED:$$failed"; exit 1; \
	else echo "All tests passed."; fi

# ─── Seeds & Setup ────────────────────────────────────────────────────────────

## Seed test merchants + transactions
seed: wait-healthy
	$(COMPOSE) exec payment-service python scripts/seed_db.py

## First-time complete setup
init:
	@if [ ! -f $(ENV_FILE) ]; then \
	  cp .env.example $(ENV_FILE); \
	  echo "==> .env created. Edit it now (DOMAIN, passwords, keys) then run make init again."; \
	  exit 1; \
	fi
	@echo "==> Building all images (parallel)..."
	$(COMPOSE) build --parallel
	@echo "==> Starting infrastructure..."
	$(COMPOSE) up -d postgres-main postgres-vault redis redpanda
	@$(MAKE) wait-healthy
	@echo "==> Bootstrapping Redpanda topics..."
	$(COMPOSE) up redpanda-init
	@echo "==> Running all migrations..."
	@$(MAKE) migrate-all
	@echo "==> Starting remaining services..."
	$(COMPOSE) up -d
	@sleep 10
	@echo "==> Seeding test data..."
	@$(MAKE) seed
	@echo ""
	@echo "Payment Gateway ready!"

# ─── Infrastructure subset ────────────────────────────────────────────────────

## Start only database + messaging infrastructure
infra-up:
	$(COMPOSE) up -d postgres-main postgres-vault redis redpanda keycloak

## Stop infrastructure containers only
infra-down:
	$(COMPOSE) stop postgres-main postgres-vault redis redpanda keycloak

## List all Redpanda topics
topics:
	$(COMPOSE) exec redpanda rpk topic list

## Tail a Redpanda topic from start: make topic-tail t=payment.captured
topic-tail:
	$(COMPOSE) exec redpanda rpk topic consume $(t) --offset start

# ─── Celery ───────────────────────────────────────────────────────────────────

## Show active Celery tasks across workers
celery-status:
	$(COMPOSE) exec celery-worker-settlement \
	  celery -A celery_app:celery_app inspect active
	$(COMPOSE) exec celery-worker-settlement \
	  celery -A celery_app:celery_app inspect scheduled

## Manually trigger a settlement batch: make run-settlement d=2025-01-15
run-settlement:
	$(COMPOSE) exec settlement-service python -c \
	  "from tasks.settlement import create_daily_batch; r = create_daily_batch.delay('$(d)'); print('Task ID:', r.id)"

## Scale settlement workers: make scale-settlement n=4
scale-settlement:
	$(COMPOSE) up -d --scale celery-worker-settlement=$(n) celery-worker-settlement

## Scale notification workers: make scale-notification n=6
scale-notification:
	$(COMPOSE) up -d --scale celery-worker-notification=$(n) celery-worker-notification

# ─── Reports ──────────────────────────────────────────────────────────────────

## Run Locust load test against fraud-service (p95 < 100ms SLO)
## Usage: make load-test [users=50] [duration=60s]
load-test:
	@bash tests/load/run_load_test.sh ${users:-50} ${spawn:-10} ${duration:-60s}

## Run fraud-service UI load test (interactive Locust web UI at :8089)
load-test-ui:
	FRAUD_SERVICE_URL=http://localhost:8013 \
	locust -f tests/load/locustfile.py --host http://localhost:8013 --web-port 8089

## Integration rate-limit tests (requires RATE_LIMIT_TEST_URL env var)
test-rate-limits:
	@echo "==> Running Traefik rate-limit integration tests..."
	pytest tests/integration/test_rate_limiting.py -v -s \
	  --tb=short -x \
	  -k "rate" || echo "Set RATE_LIMIT_TEST_URL to run against a live stack"

## First-time Keycloak realm + client + roles + test users
setup-keycloak:
	@echo "==> Setting up Keycloak realm..."
	@bash scripts/setup_keycloak.sh

## Download RBI CSV: make rbi-report start=2025-01-01 end=2025-01-31
rbi-report:
	@DOMAIN=$$(grep '^DOMAIN' $(ENV_FILE) | cut -d= -f2); \
	curl -sf -H "Authorization: Bearer $$API_TOKEN" \
	  "https://api.$$DOMAIN/v1/admin/reports/rbi?start_date=$(start)&end_date=$(end)" \
	  -o rbi_$(start)_$(end).csv && echo "Saved: rbi_$(start)_$(end).csv"

# ─── Help ─────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "Payment Gateway — Makefile (Oracle ARM A1)"
	@echo "══════════════════════════════════════════"
	@echo ""
	@echo "SETUP          make init                First-time build + migrate + seed"
	@echo "               make up                  Start (dev hot-reload)"
	@echo "               make up-prod             Start (production)"
	@echo "               make down                Stop all"
	@echo "               make fresh               Destroy volumes + rebuild"
	@echo ""
	@echo "BUILD          make build [s=SVC]        Build one or all"
	@echo "               make build-all            Build in parallel"
	@echo ""
	@echo "MONITORING     make ps                   Container status"
	@echo "               make health               Poll /health on all services"
	@echo "               make logs s=SVC           Follow logs"
	@echo "               make tail s=SVC           Last 100 lines"
	@echo ""
	@echo "SHELL          make shell s=SVC          Open bash"
	@echo "               make exec s=SVC cmd=CMD   Run command"
	@echo ""
	@echo "MIGRATIONS     make migrate s=SVC        One service"
	@echo "               make migrate-all          All services in order"
	@echo "               make revision s=SVC msg=  Generate new revision"
	@echo ""
	@echo "TESTS          make test s=SVC           One service"
	@echo "               make test-cov s=SVC       With coverage"
	@echo "               make test-all             All core services"
	@echo ""
	@echo "DATA           make seed                 Insert test data"
	@echo "               make topics               List Kafka topics"
	@echo "               make topic-tail t=TOPIC   Tail a topic"
	@echo ""
	@echo "CELERY         make celery-status        Active tasks"
	@echo "               make run-settlement d=DATE Manual batch"
	@echo "               make scale-settlement n=N Scale workers"
	@echo ""
	@echo "Variables:     s=SERVICE  d=DATE  t=TOPIC  n=COUNT  msg=TEXT"
	@echo ""
