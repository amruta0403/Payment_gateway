# Payment Gateway — Merchant Dashboard

Standalone full-stack merchant dashboard.
Lives **alongside** the `payment-gateway/` monorepo, not inside it.

```
d:\DJ\                         ← repo root
├── payment-gateway/           ← backend microservices (run first)
└── dashboard/                 ← this project (runs separately)
    ├── frontend/   ← Next.js 14 + Tailwind + Recharts   (port 3001)
    └── backend/    ← FastAPI BFF (aggregation + proxy)   (port 8099)
```

---

## Prerequisites

The `payment-gateway` services must be running before starting the dashboard.

```bash
# From the repo root — start the payment gateway first
cd ../payment-gateway
make up          # or: docker compose up -d
make setup-keycloak
```

---

## Quick Start

```bash
# From the repo root
cd dashboard

# 1. Copy env files and fill in values
cp frontend/.env.example frontend/.env.local
cp backend/.env.example  backend/.env
# Edit both files if your service ports differ from defaults

# 2A. Docker Compose (easiest)
docker compose up -d
open http://localhost:3001

# 2B. Manual (two terminals)
# Terminal 1 — Backend BFF
cd backend && pip install -r requirements.txt
uvicorn main:app --reload --port 8099

# Terminal 2 — Frontend
cd frontend && npm install
npm run dev     # → http://localhost:3001
```

Login with Keycloak test users:
- `test-merchant` / `Test@1234!`
- `test-admin` / `Admin@1234!`

---

## Features

| Page | Description |
|---|---|
| **Overview** | KPI cards, 30-day volume chart, payment method split, recent transactions |
| **Transactions** | Full list with filters (status, method, date range), detail view |
| **Payments** | Create test payments (card/UPI/netbanking), live fraud score display |
| **Refunds** | Initiate refunds, track status, full/partial |
| **Settlements** | T+1 batch history — gross → fee → GST → net breakdown |
| **API Keys** | Create/revoke keys, `full_key` shown once with copy button |
| **Webhooks** | Register HTTPS endpoints, test delivery, view logs |
| **Settings** | Merchant profile, onboarding checklist, bank accounts |

---

## Environment Variables

### `frontend/.env.local`

```env
NEXTAUTH_URL=http://localhost:3001
NEXTAUTH_SECRET=replace-with-any-random-32-char-string
KEYCLOAK_URL=http://localhost:8080
KEYCLOAK_REALM=payment-gateway
KEYCLOAK_CLIENT_ID=payment-backend
KEYCLOAK_CLIENT_SECRET=change-me-secret
NEXT_PUBLIC_BFF_URL=http://localhost:8099
```

> `KEYCLOAK_CLIENT_SECRET` must match the value in `payment-gateway/.env`.

### `backend/.env`

```env
# Payment Gateway service URLs (adjust if running on different host/ports)
PAYMENT_SERVICE_URL=http://localhost:8010
MERCHANT_SERVICE_URL=http://localhost:8012
SETTLEMENT_SERVICE_URL=http://localhost:8015
REFUND_SERVICE_URL=http://localhost:8016
TRANSACTION_SERVICE_URL=http://localhost:8020
WEBHOOK_SERVICE_URL=http://localhost:8021
FRAUD_SERVICE_URL=http://localhost:8013
REPORTING_SERVICE_URL=http://localhost:8022

# Keycloak (same realm as payment-gateway)
KEYCLOAK_URL=http://localhost:8080
KEYCLOAK_REALM=payment-gateway

# CORS — allow the frontend origin
ALLOWED_ORIGINS=http://localhost:3001
```

> If `payment-gateway` is running via Docker Compose and you are running the dashboard
> manually on the host, use `localhost` (Docker ports are mapped to host).
>
> If running the dashboard **inside the same Docker network**, replace
> `localhost` with service names (e.g. `http://payment-service:8010`).

---

## Architecture

```
Browser  →  Next.js :3001  →  FastAPI BFF :8099
                                     │
             ┌───────────────────────┼─────────────────────┐
             ▼                       ▼                     ▼
     payment-service:8010    merchant-service:8012   transaction-service:8020
     fraud-service:8013      settlement-service:8015  webhook-service:8021
     refund-service:8016      reporting-service:8022
     keycloak:8080
```

The BFF (`backend/`) never stores data — it:
1. Validates the Keycloak JWT from the frontend
2. Aggregates dashboard stats from multiple services concurrently
3. Proxies all other requests with the user's token

---

## Running in Docker network (alongside payment-gateway compose)

If you want the dashboard containers to reach the payment-gateway containers
by **service name** (not localhost), attach them to the same Docker network:

```yaml
# dashboard/docker-compose.yml — add to each service:
networks:
  default:
    external: true
    name: payment-gateway_payment_network
```

And update `backend/.env`:
```env
PAYMENT_SERVICE_URL=http://payment-service:8010
MERCHANT_SERVICE_URL=http://merchant-service:8012
# ... etc
```
