.PHONY: up down logs shell migrate migrate-all test test-all seed build ps fresh help

# ─── Docker ──────────────────────────────────────────────────────────────────

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build $(s)

ps:
	docker compose ps

fresh:
	docker compose down -v
	docker compose up -d --build

logs:
	docker compose logs -f $(s)

shell:
	docker compose exec $(s) bash

# ─── DB migrations ───────────────────────────────────────────────────────────

migrate:
	docker compose exec $(s) alembic upgrade head

migrate-all:
	@for svc in merchant-service payment-service upi-service settlement-service \
	            refund-service audit-service notification-service fraud-service; do \
	  echo "==> Migrating $$svc..."; \
	  docker compose exec $$svc alembic upgrade head; \
	done

# ─── Tests ───────────────────────────────────────────────────────────────────

test:
	docker compose exec $(s) pytest tests/ -v --tb=short

test-all:
	@for svc in payment-service merchant-service fraud-service upi-service; do \
	  echo "==> Testing $$svc..."; \
	  docker compose exec $$svc pytest tests/ -v --tb=short; \
	done

# ─── Seed ────────────────────────────────────────────────────────────────────

seed:
	docker compose exec payment-service python -m scripts.seed_db

# ─── Help ────────────────────────────────────────────────────────────────────

help:
	@echo "Usage: make [target] [s=SERVICE_NAME]"
	@echo ""
	@echo "  up              Start all services"
	@echo "  down            Stop all services"
	@echo "  build [s=SVC]   Build image(s)"
	@echo "  ps              Show service status"
	@echo "  fresh           Tear down volumes and rebuild"
	@echo "  logs s=SVC      Follow logs for a service"
	@echo "  shell s=SVC     Open shell in a running container"
	@echo "  migrate s=SVC   Run alembic upgrade for one service"
	@echo "  migrate-all     Run alembic upgrade for all services"
	@echo "  test s=SVC      Run pytest for one service"
	@echo "  test-all        Run pytest for all core services"
	@echo "  seed            Seed test data"
