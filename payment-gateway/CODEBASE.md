# Payment Gateway — Codebase Reference

> **For new Claude sessions:** This document is a complete snapshot of the codebase state.
> Read this before making any changes so you understand what exists, what works, and what still needs setup.

---

## Quick Stats

| Metric | Count |
|---|---|
| Python files | 294 |
| Services | 14 FastAPI microservices |
| Shared library files | 22 |
| Database migrations | 13 (across 12 services) |
| Unit test files | 24 |
| Email HTML templates | 7 |
| GitHub Actions workflows | 2 (ci.yml, deploy.yml) |
| Grafana dashboards | 3 JSON files |
| Docker Compose services | ~30 (14 app + 16 infra) |

---

## Architecture Overview

```
Internet
  │
  ▼
Traefik v3 (TLS termination, rate limiting, routing)
  │
  ├─► payment-service:8010     — Card/UPI/NetBanking transaction lifecycle
  ├─► merchant-service:8012    — Merchant registration, KYC, API keys, webhooks
  ├─► upi-service:8014         — UPI collect/intent, NPCI mock, QR codes, mandates
  ├─► settlement-service:8015  — T+1 Celery batch settlement + Razorpay X payouts
  ├─► refund-service:8016      — Refund routing (card→payment-svc, UPI→upi-svc)
  ├─► transaction-service:8020 — Read-only transaction query API
  ├─► webhook-service:8021     — Reliable HMAC-signed event delivery with retry
  ├─► reporting-service:8022   — MIS reports, CSV export, GST reports
  ├─► kyc-service:8018         — Standalone KYC orchestration (PAN/GSTIN/bank)
  └─► netbanking-service:8019  — 12-bank redirect handler + callback processing

Internal (no public Traefik route):
  ├─► card-vault-service:8011  — PCI-CDE AES-256-GCM card tokenisation
  ├─► fraud-service:8013       — Rules engine + IsolationForest ML (<100ms p95)
  ├─► notification-service:8017— Email (Resend/SMTP) + SMS (Fast2SMS) via Kafka+Celery
  └─► audit-service:8024       — Append-only partitioned audit log (all Kafka topics)

Infrastructure:
  ├─► PostgreSQL 16 (main DB)  + PostgreSQL 16 (CDE vault — internal network only)
  ├─► Redis 7                  — Cache, rate-limit, velocity checks, Celery broker
  ├─► Redpanda                 — Kafka-compatible (24 topics)
  ├─► Keycloak 24              — JWT auth, realm=payment-gateway
  ├─► Infisical                — Secrets management (self-hosted)
  ├─► Prometheus + Grafana     — Metrics (3 dashboards: gateway, services, infra)
  └─► GlitchTip                — Error tracking (open-source Sentry)
```

---

## Technology Stack

| Layer | Technology | Notes |
|---|---|---|
| **API Framework** | FastAPI 0.111+ | Async, Pydantic v2 validation |
| **ORM** | SQLAlchemy 2.0 async | asyncpg driver, NullPool for migrations |
| **Validation** | Pydantic v2 | All schemas with type annotations |
| **Auth** | Keycloak 24 + JWT | `get_combined_auth_dependency()` tries Bearer JWT → falls back to X-Api-Key |
| **Encryption** | AES-256-GCM | `FieldEncryptor` in `shared/utils/encryption.py`, key stored in env var |
| **Message broker** | Redpanda (Kafka API) | aiokafka consumer/producer, DLQ routing |
| **Cache** | Redis 7 | Idempotency, rate-limit, velocity checks, Celery backend |
| **Task queue** | Celery + Redis | settlement-service + notification-service workers |
| **DB migrations** | Alembic async | `create_async_engine` with `NullPool` |
| **Reverse proxy** | Traefik v3 | TLS (Let's Encrypt), rate limiting, security headers |
| **Monitoring** | Prometheus + Grafana | `prometheus-fastapi-instrumentator` in every service |
| **Error tracking** | GlitchTip (Sentry SDK) | `shared/telemetry.py` wired into all 14 `main.py` files |
| **Secrets** | Infisical (self-hosted) | `INFISICAL_TOKEN` per service |
| **ML** | scikit-learn IsolationForest | fraud-service, model at `model/fraud_v1.pkl` |
| **Python packaging** | uv workspace | `pyproject.toml` per service, shared as workspace member |
| **CI/CD** | GitHub Actions | `.github/workflows/ci.yml` + `deploy.yml` |
| **Target infra** | Oracle Cloud ARM A1 | Ubuntu 22.04, 4 CPU, 24 GB RAM — free tier |

---

## Repository Structure

```
payment-gateway/
├── shared/                          ← Shared library (22 files, uv workspace member)
│   ├── auth/
│   │   ├── keycloak.py              ← JWT validator, get_combined_auth_dependency()
│   │   └── api_key.py               ← API key hashing + validation
│   ├── cache/
│   │   └── redis_client.py          ← 11 Redis helper functions (all pipeline + fail-open)
│   ├── db/
│   │   ├── base.py                  ← Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, set_rls_context()
│   │   └── session.py               ← create_engine(), create_session_factory(), get_db()
│   ├── kafka/
│   │   ├── producer.py              ← PaymentEventProducer (acks=all, idempotent, gzip)
│   │   ├── consumer.py              ← PaymentEventConsumer (DLQ routing)
│   │   └── topics.py                ← 24 topic constants
│   ├── models/
│   │   └── enums.py                 ← 17 shared enum classes
│   ├── exceptions/
│   │   └── handlers.py              ← 13 exception types + register_exception_handlers()
│   ├── utils/
│   │   ├── encryption.py            ← FieldEncryptor (AES-256-GCM), hash_field(), generate_key_b64()
│   │   ├── masking.py               ← mask_pan/phone/email/vpa(), LogSanitiser
│   │   ├── money.py                 ← paise↔rupees conversion, Indian locale ₹
│   │   └── idempotency.py           ← IdempotencyMiddleware (Starlette)
│   └── telemetry.py                 ← init_error_tracking(settings) → GlitchTip/Sentry
│
├── services/
│   ├── payment-service/             ← Port 8010 — full implementation (25 py files)
│   ├── card-vault-service/          ← Port 8011 — PCI CDE (21 py files)
│   ├── merchant-service/            ← Port 8012 — full (32 py files, 6 routers)
│   ├── fraud-service/               ← Port 8013 — full (22 py files, ML model)
│   ├── upi-service/                 ← Port 8014 — full (21 py files)
│   ├── settlement-service/          ← Port 8015 — full (31 py files, Celery tasks)
│   ├── notification-service/        ← Port 8017 — full (22 py files, Celery tasks)
│   ├── refund-service/              ← Port 8016 — full (16 py files)
│   ├── audit-service/               ← Port 8024 — full (18 py files, Kafka consumer)
│   ├── kyc-service/                 ← Port 8018 — basic (12 py files)
│   ├── netbanking-service/          ← Port 8019 — basic (12 py files)
│   ├── transaction-service/         ← Port 8020 — read-only (12 py files)
│   ├── webhook-service/             ← Port 8021 — delivery worker (13 py files)
│   └── reporting-service/           ← Port 8022 — reports+CSV (10 py files)
│
├── infra/
│   ├── traefik/
│   │   ├── traefik.yml              ← Entrypoints, Let's Encrypt, providers
│   │   └── dynamic/middleware.yml   ← Rate limits, security headers, HTTPS redirect
│   ├── prometheus/
│   │   └── prometheus.yml           ← Scrapes all 14 services + exporters
│   ├── grafana/
│   │   ├── provisioning/            ← Auto-provisioned datasource + dashboard config
│   │   └── dashboards/              ← 3 JSON dashboards (gateway, services, infra)
│   └── postgres/
│       └── init-multiple-dbs.sh     ← Creates keycloak/infisical/glitchtip databases
│
├── scripts/
│   ├── setup_keycloak.sh            ← Creates realm, client, roles, test users via REST API
│   ├── seed_db.py                   ← Seeds merchants, bank accounts, transactions, API keys
│   └── init_local.sh                ← Full local bootstrap script
│
├── tests/
│   ├── e2e/test_golden_path.py      ← 14-step end-to-end payment flow test
│   ├── integration/test_rate_limiting.py ← Traefik rate limit tests (requires live stack)
│   └── load/
│       ├── locustfile.py            ← Fraud-service load test (p95 < 100ms SLO)
│       └── run_load_test.sh         ← Run with: make load-test
│
├── .github/
│   └── workflows/
│       ├── ci.yml                   ← Lint + test matrix + Docker build/push (arm64+amd64)
│       └── deploy.yml               ← SSH deploy to OCI, migrations, health check
│
├── docs/
│   └── API.md                       ← Full API reference (21 sections, all endpoints)
│
├── docker-compose.yml               ← All 30 services, correct build contexts
├── docker-compose.override.yml      ← Dev hot-reload, volume mounts for all 14 services
├── Makefile                         ← up/down/init/migrate-all/test-all/load-test/...
├── .env.example                     ← 70+ variables with comments
├── requirements-dev.txt             ← locust, httpx, ruff, mypy for host machine
└── CODEBASE.md                      ← This file

# MERCHANT DASHBOARD — lives at the REPO ROOT, not inside payment-gateway/
../dashboard/                        ← Sibling directory at d:\DJ\dashboard\
  ├── frontend/                      ← Next.js 14 + Tailwind (port 3001)
  └── backend/                       ← FastAPI BFF (port 8099)
# See ../dashboard/README.md for setup instructions
```

---

## Service-by-Service Feature Summary

### payment-service
- **State machine**: `PaymentStateMachine` with `ALLOWED_TRANSITIONS` dict — all status changes validated
- **Acquirer adapters**: Abstract `AcquirerAdapter` + `MockAcquirerAdapter` + `RazorpayAdapter`
- **3DS support**: `three_ds_status`, `eci`, `cavv`, `xid` stored per transaction
- **Fraud gate**: Calls `fraud-service /v1/score` synchronously before every payment; blocks if `BLOCK`
- **Card tokenisation**: Calls `card-vault-service /vault/tokenize` — PAN never stored in main DB
- **Idempotency**: Redis-based, 24h TTL, X-Idempotency-Key header
- **RLS**: PostgreSQL row-level security — merchants see only their own transactions
- **Migrations**: `0001_initial.py` (transactions + transaction_events, enums, RLS, trigger), `0002_add_dispute_table.py`

### card-vault-service
- **CDE isolation**: `cde_network` (internal=true), `InternalServiceAuthMiddleware` checks X-Service-Token + source IP subnet
- **Multi-key rotation**: Keys stored as `v{n}:{b64(nonce||ciphertext)}`, `re_encrypt()` rotates 50-row batches
- **CVV handling**: Deleted immediately after Luhn check — never stored anywhere
- **Access log**: `vault_access_log` is append-only (REVOKE UPDATE/DELETE/TRUNCATE from PUBLIC)
- **BIN database**: 20 common BINs seeded, `detect_network()` auto-classifies cards

### merchant-service
- **Encrypted fields**: `business_name`, `pan`, `gstin`, `support_email`, `support_phone` (AES-256-GCM)
- **Hash fields**: `business_name_hash`, `pan_hash`, `gstin_hash` (SHA-256, for search without decryption)
- **Keycloak integration**: Creates `merchant_{id}` group, assigns MERCHANT_OWNER role on registration
- **Penny drop**: Razorpay FundAccount validation API (mock in dev: random 1–2 paise)
- **API keys**: `sk_{env}_{random}` prefix, SHA-256 hash stored — full key shown once only
- **Webhook secrets**: `secrets.token_hex(32)` — SHA-256 hash stored, secret shown once
- **6 routers**: merchants, kyc, bank_accounts, api_keys, webhooks, dashboard

### fraud-service
- **Rules engine**: 5 hard-block rules (IP/card blacklist + 3 velocity checks) + 5 score rules — all run via `asyncio.gather` (concurrent)
- **ML model**: `sklearn.IsolationForest` loaded from `model/fraud_v1.pkl` at startup — if missing, generates toy model
- **Blended score**: `final = 0.6 × rules_score + 0.4 × ml_score`
- **Performance**: `asyncio.create_task(rules_eval)` then `ml.predict()` (sync, CPU) then `await rules_task` — target p95 < 100ms
- **Prometheus**: `fraud_decisions_total{decision}`, `fraud_scoring_duration_seconds`, `fraud_rule_hits_total{rule_name}`
- **Redis pipelining**: Every velocity check uses 4-command pipeline (`ZREMRANGEBYSCORE → ZADD → ZCARD → EXPIRE`)

### upi-service
- **Mock NPCI client**: Known test VPAs (`success@upi`, `fail@upi`, `timeout@upi`, `invalid@xyz`)
- **Auto-resolution**: Mock resolves collect to SUCCESS after `resolution_delay` seconds (0 in tests)
- **QR generation**: `qrcode[pil]` library — UPI deep link encoded as PNG, returned as base64
- **VPA caching**: Redis `cache_get/set` with 5-minute TTL
- **Polling**: `poll_until_terminal()` with delays `[5,10,20,30,30,30,30,30,60,60,60,60]s` → expire after ~7.5 min
- **Callback**: `POST /upi/callback` — NO `/v1` prefix (NPCI-facing), HMAC-SHA256 validated
- **UPI 2.0 mandates**: DAILY/WEEKLY/MONTHLY, create/execute/revoke

### settlement-service
- **Celery tasks** (sync SQLAlchemy + psycopg2):
  - `create_daily_batch`: Groups captured txns by merchant, calculates fees, creates batches
  - `initiate_payout`: Calls `MockPayoutProvider` or `RazorpayXProvider`
  - `reconcile`: Re-queues failed batches, alerts on stuck PROCESSING batches
- **Fee calculator**: `ALL arithmetic in integer paise` — Decimal only for % math, then `ROUND_HALF_UP → int`
- **Beat schedule**: `create_daily_batch` at 17:30 UTC (23:00 IST), `reconcile` at 00:30 UTC (06:00 IST)
- **RBI zero-MDR**: UPI transactions ≤ ₹2,000 — `fee = 0` (RBI P2M mandate)

### notification-service
- **Kafka consumer**: Subscribes to 7 topics → dispatches `send_email_task.delay()` / `send_sms_task.delay()`
- **Email**: `ResendEmailProvider` (primary) → `SMTPEmailProvider` (fallback), factory auto-selects
- **SMS**: `Fast2SMSProvider` (production) → `MockSMSProvider` (development)
- **7 Jinja2 templates**: payment_success, payment_failed, refund_initiated, refund_completed, settlement_advice, kyc_approved, kyc_rejected — mobile-responsive HTML with inline CSS
- **Idempotency**: Checks `event_id + channel` before sending — no duplicate notifications on retry
- **Encryption**: Recipient email/phone encrypted at rest in `notification_logs`

### audit-service
- **Subscribes to ALL topics**: `group_id="audit-consumers"`, `auto_offset_reset="earliest"` — no events missed
- **Sanitizer**: `sanitise_for_audit()` — redacts 14 sensitive key patterns + card number regex, depth limit 3
- **Partitioned table**: `audit_logs PARTITION BY RANGE(created_at)`, monthly partitions 2025–2026 + default partition
- **Append-only**: `REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM payment_app_user`
- **Cursor pagination**: base64-encoded `(created_at, id)` cursor for deterministic ordering
- **CSV export**: Max 31-day range, COMPLIANCE_OFFICER role required

---

## Data Flow: Complete Payment Journey

```
Client
  │  POST /v1/payments (card payment)
  ▼
payment-service
  │  1. Validate request (Pydantic, Luhn check, E.164 phone)
  │  2. Check idempotency key in Redis
  │  3. POST fraud-service /v1/score ──► fraud-service evaluates rules + ML
  │     If BLOCK → reject immediately
  │  4. POST card-vault /vault/tokenize ──► store encrypted PAN, return token
  │  5. Insert Transaction (status=CREATED)
  │  6. Call acquirer (Mock or Razorpay)
  │  7. Update Transaction (status=CAPTURED)
  │  8. Publish payment.captured → Redpanda
  │
  ▼ (Kafka events)
  ├─► notification-service — sends email/SMS to customer
  ├─► audit-service — writes sanitized event to audit_logs partition
  └─► webhook-service — delivers to merchant-registered HTTPS endpoints

  ▼ (Celery Beat — 23:00 IST daily)
settlement-service.create_daily_batch
  │  Groups CAPTURED txns by merchant
  │  Calculates fee breakdown (integer paise, Decimal for % math)
  │  Creates settlement_batch + settlement_transactions
  │  Updates txn status → SETTLEMENT_INITIATED
  │
  ▼
settlement-service.initiate_payout
  │  Finds merchant's primary verified bank account (decrypts account number)
  │  Calls RazorpayX payout API (or Mock)
  │  Updates txn status → SETTLED, records UTR number
  │
  ▼ (Kafka)
  └─► notification-service — sends settlement advice email to merchant
```

---

## Authentication Flow

```
Client Request
  │
  ├─ Has Authorization: Bearer {JWT} ?
  │    ► Validate with Keycloak JWKS
  │    ► Extract: sub, merchant_id, roles, email
  │
  ├─ Has X-Api-Key: sk_{env}_{prefix}_{secret} ?
  │    ► SHA-256 hash → lookup in api_keys table
  │    ► Validate merchant_id matches, is_active=true, not expired
  │
  └─ Neither → 401 Unauthorized

All routes use:  get_combined_auth_dependency()  (tries JWT first, falls back to API key)
Internal routes: X-Service-Token header (validated by InternalServiceAuthMiddleware)
```

---

## Database Schema Summary

All services share **one PostgreSQL instance** (except `card-vault-service` which uses a separate `postgres-vault` on the CDE network).

| Table | Service | Notes |
|---|---|---|
| `transactions` | payment-service | RLS enabled, `updated_at` trigger |
| `transaction_events` | payment-service | BigSerial PK, append-only audit trail |
| `dispute_chargebacks` | payment-service | RLS enabled, backfill migration in 0002 |
| `card_tokens` | card-vault-service | Encrypted PAN, `vault_access_log` append-only |
| `vault_access_log` | card-vault-service | REVOKE UPDATE/DELETE/TRUNCATE |
| `bin_database` | card-vault-service | 20 BINs seeded |
| `merchants` | merchant-service | Encrypted+hashed fields, RLS |
| `merchant_bank_accounts` | merchant-service | Encrypted account_number |
| `kyc_documents` | merchant-service | Encrypted S3 key path |
| `api_keys` | merchant-service | key_hash only — full key never stored |
| `merchant_webhooks` | merchant-service | secret_hash only |
| `webhook_deliveries` | merchant-service | — |
| `upi_transactions` | upi-service | Encrypted vpa_payer |
| `merchant_vpas` | upi-service | — |
| `upi_mandates` | upi-service | Encrypted customer_vpa |
| `settlement_batches` | settlement-service | — |
| `settlement_transactions` | settlement-service | Cross-service ref (no FK) |
| `settlement_payouts` | settlement-service | UTR number recorded |
| `refunds` | refund-service | RLS enabled |
| `fraud_blacklist` | fraud-service | — |
| `fraud_rules` | fraud-service | 10 rules seeded |
| `notification_logs` | notification-service | Encrypted recipient |
| `notification_preferences` | notification-service | Opt-out tracking |
| `kyc_sessions` | kyc-service | — |
| `webhook_endpoints` | webhook-service | secret_hash only |
| `webhook_deliveries` | webhook-service | Delivery attempt history |
| `netbanking_sessions` | netbanking-service | — |
| `audit_logs` | audit-service | PARTITION BY RANGE(created_at), monthly 2025–2026 |

---

## Environment Variables (Key Ones)

See `.env.example` for the full list (70+ variables). Critical variables:

| Variable | Purpose | Generate with |
|---|---|---|
| `CARD_ENCRYPTION_KEY_V1` | AES-256-GCM key for PAN/VPA/account encryption | `python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"` |
| `INTERNAL_SERVICE_TOKEN` | Card-vault + fraud service auth | `openssl rand -hex 32` |
| `KEYCLOAK_CLIENT_SECRET` | Payment services → Keycloak | `openssl rand -hex 32` |
| `INFISICAL_ENCRYPTION_KEY` | Infisical server encryption | `openssl rand -hex 16` |
| `GLITCHTIP_SECRET_KEY` | Django secret for GlitchTip | `openssl rand -base64 50` |
| `POSTGRES_PASSWORD` | Main database | Strong random password |
| `VAULT_POSTGRES_PASSWORD` | CDE vault database | Different strong password |
| `GRAFANA_ADMIN_PASSWORD` | Grafana UI | Strong password |

---

## What Is Complete ✅

### All 14 services have:
- `main.py` with lifespan, middleware, health endpoint
- `config.py` with Pydantic Settings
- `dependencies.py` with `get_db_session`, `get_principal`, `get_redis`
- Working `Dockerfile` (workspace-root build context, `PYTHONPATH=/app`)
- `pyproject.toml` with all deps including `sentry-sdk`
- `shared/telemetry.py` wired in (GlitchTip/Sentry)
- At least one router with real endpoints

### 9 services are fully production-ready:
`payment-service`, `card-vault-service`, `merchant-service`, `fraud-service`, `upi-service`, `settlement-service`, `notification-service`, `refund-service`, `audit-service`

### 5 services are functionally complete (not production-hardened):
`transaction-service`, `webhook-service`, `reporting-service`, `kyc-service`, `netbanking-service`

### Infrastructure:
- Docker Compose with all services, correct CDE network isolation
- Traefik v3 with TLS, rate limiting, security headers, HTTPS redirect
- Prometheus scraping all 14 services + postgres-exporter + redis-exporter
- Grafana with 3 auto-provisioned dashboards
- GlitchTip + Infisical configured

### Testing:
- Unit tests for all 9 fully-built services (~24 test files)
- Integration rate-limiting tests (`tests/integration/`)
- Locust load test with p95 < 100ms SLO enforcement (`tests/load/`)
- End-to-end golden path test (`tests/e2e/test_golden_path.py`)

### Docs & DevOps:
- Full API reference (`docs/API.md` — 21 sections, every endpoint)
- Makefile with 20+ targets
- GitHub Actions CI (lint + test matrix + Docker build ARM64+AMD64)
- GitHub Actions deploy (SSH → OCI → migrations → health check)
- `scripts/setup_keycloak.sh` — Realm + client + roles + test users
- `scripts/seed_db.py` — Full seed with encrypted fields

---

## What Is Pending ⏳ (To Run End-to-End)

### 🔴 MUST DO before first payment works

#### 1. Generate encryption key
```bash
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
# Put result in .env → CARD_ENCRYPTION_KEY_V1=
```

#### 2. Copy and fill .env
```bash
cp .env.example .env
# Edit: DOMAIN, POSTGRES_PASSWORD, VAULT_POSTGRES_PASSWORD, KEYCLOAK_ADMIN_PASSWORD,
#       CARD_ENCRYPTION_KEY_V1, INTERNAL_SERVICE_TOKEN, KEYCLOAK_CLIENT_SECRET,
#       ACME_EMAIL (for Let's Encrypt)
```

#### 3. Start infrastructure and run migrations
```bash
make init
# This does: build → start infra → wait healthy → topics → migrate-all → start all → seed
```

#### 4. Set up Keycloak realm
```bash
make setup-keycloak
# Creates: realm, client, roles (MERCHANT_OWNER/ADMIN/COMPLIANCE_OFFICER/...), test users
# Test users created:
#   test-merchant  / Test@1234!  (MERCHANT_OWNER)
#   test-admin     / Admin@1234! (ADMIN)
```

#### 5. Generate Fraud ML model
The fraud-service auto-generates `model/fraud_v1.pkl` on first startup if missing (using scikit-learn IsolationForest on synthetic data). **No manual step needed.** But for production, train on real data:
```bash
docker compose exec fraud-service python model/scorer.py
```

#### 6. Get test API token
```bash
curl -X POST http://localhost:8080/auth/realms/payment-gateway/protocol/openid-connect/token \
  -d "client_id=payment-backend&client_secret=YOUR_SECRET" \
  -d "username=test-merchant&password=Test@1234!&grant_type=password" | jq .access_token
```

---

### 🟡 NEEDED for real payments (acquirer integration)

#### Razorpay Payment Processing
```bash
# .env
ACQUIRER_MODE=razorpay          # Change from: mock
RAZORPAY_KEY_ID=rzp_test_xxx
RAZORPAY_KEY_SECRET=xxx
```

#### Razorpay X (Settlements / Payouts)
```bash
PAYOUT_PROVIDER=razorpay        # Change from: mock
RAZORPAY_X_KEY_ID=rzpx_test_xxx
RAZORPAY_X_KEY_SECRET=xxx
RAZORPAY_X_ACCOUNT=1234567890   # Your Razorpay X source account number
```

#### NPCI / UPI (Real payments)
```bash
NPCI_CLIENT_MODE=live           # Change from: mock
NPCI_CALLBACK_SECRET=xxx        # Get from NPCI integration team
```

---

### 🟡 NEEDED for notifications

#### Email (choose one)
```bash
# Option A: Resend (recommended — free 3,000 emails/month)
RESEND_API_KEY=re_xxxxxxxx

# Option B: SMTP (Gmail app password)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your@gmail.com
SMTP_PASSWORD=app-specific-password
```

#### SMS — Fast2SMS
```bash
FAST2SMS_API_KEY=xxxxxxxx
SMS_SENDER_ID=PAYGTW
```

---

### 🟡 NEEDED for KYC document storage

#### Cloudflare R2 (recommended — free 10 GB/month)
```bash
AWS_ACCESS_KEY_ID=xxxxx
AWS_SECRET_ACCESS_KEY=xxxxx
AWS_REGION=auto
S3_KYC_BUCKET=payment-kyc-docs
S3_ENDPOINT_URL=https://xxxxx.r2.cloudflarestorage.com
```

---

### 🟡 NEEDED for error tracking

#### GlitchTip (self-hosted — already in docker-compose)
```bash
# 1. Visit https://errors.your-domain.com after make up
# 2. Create account and project
# 3. Copy the DSN → put in .env
GLITCHTIP_DSN=https://xxxx@errors.your-domain.com/1
```

---

### 🟡 NEEDED for secrets management

#### Infisical (self-hosted — already in docker-compose)
```bash
# 1. Visit https://secrets.your-domain.com after make up
# 2. Create account, project, and token
INFISICAL_TOKEN=st.xxxxxxxx

# Also configure Infisical server's own secrets in .env:
INFISICAL_ENCRYPTION_KEY=    # 32-char hex
INFISICAL_AUTH_SECRET=       # 32-char string
```

---

### 🟡 NEEDED for TLS (production domain)

#### Let's Encrypt (Traefik handles this automatically)
```bash
DOMAIN=api.yourdomain.com      # Your real domain
ACME_EMAIL=ops@yourdomain.com  # For Let's Encrypt notifications

# DNS: Point these A records to your OCI instance IP:
# api.yourdomain.com
# auth.yourdomain.com
# monitor.yourdomain.com
# secrets.yourdomain.com
# errors.yourdomain.com
# traefik.yourdomain.com
```

---

### 🟡 NEEDED for CI/CD (GitHub Actions deploy)

#### GitHub repository secrets
Go to: `Settings → Secrets and variables → Actions` and add:

| Secret | Value |
|---|---|
| `OCI_SSH_KEY` | Private SSH key for OCI instance (`cat ~/.ssh/oci_key`) |
| `OCI_HOST` | OCI instance public IP or hostname |
| `OCI_USER` | SSH username (usually `ubuntu`) |

---

### 🟢 NICE TO HAVE (future improvements)

#### Keycloak realm export (reproducible setup)
```bash
# After setup_keycloak.sh runs, export realm for version control:
docker compose exec keycloak /opt/keycloak/bin/kc.sh export \
  --realm payment-gateway \
  --file /tmp/realm-export.json
docker compose cp keycloak:/tmp/realm-export.json infra/keycloak/realm-export.json
```
Then in `docker-compose.yml`, add the import volume:
```yaml
keycloak:
  volumes:
    - ./infra/keycloak/realm-export.json:/opt/keycloak/data/import/realm.json:ro
  command: ["start", "--import-realm", ...]
```

#### Production Keycloak (PostgreSQL instead of dev-mem)
In `docker-compose.override.yml`, Keycloak uses `dev-mem`. In production (without override):
- Uses PostgreSQL (already configured in `docker-compose.yml`)
- Run `make up-prod` instead of `make up`

#### 5 stub services need production hardening:
- `transaction-service` — add more filter options, full-text search
- `webhook-service` — Celery task for background delivery (currently sync)
- `reporting-service` — PDF export, scheduled email reports
- `kyc-service` — DigiLocker integration for production verification
- `netbanking-service` — Real bank redirect with signed params per bank

#### Redis authentication (production)
```bash
# Add to .env:
REDIS_PASSWORD=strong-redis-password

# Update redis in docker-compose.yml:
command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
```

#### Separate Celery queues for different priorities
Currently `settlement` and `notification` workers. Consider adding:
- `high` queue: Payment webhook delivery (SLA < 30s)
- `low` queue: Reports generation, CSV exports

---

## First-Time Local Setup (Step-by-Step)

```bash
# 1. Clone and enter the project
cd payment-gateway

# 2. Copy env file
cp .env.example .env

# 3. Edit .env — minimum required changes:
#    POSTGRES_PASSWORD=something_strong
#    VAULT_POSTGRES_PASSWORD=something_different
#    CARD_ENCRYPTION_KEY_V1=$(python3 -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())")
#    INTERNAL_SERVICE_TOKEN=$(openssl rand -hex 32)

# 4. Run full init (build + migrate + seed)
make init
# Takes ~5-10 minutes on first run (downloading images + building)

# 5. Set up Keycloak
make setup-keycloak

# 6. Get a test token
TOKEN=$(curl -sf -X POST \
  http://localhost:8080/auth/realms/payment-gateway/protocol/openid-connect/token \
  -d "client_id=payment-backend&client_secret=change-me-secret" \
  -d "username=test-merchant&password=Test@1234!&grant_type=password" | jq -r .access_token)

# 7. Test a payment
curl -X POST http://localhost:8010/v1/payments \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: $(uuidgen)" \
  -d '{
    "merchant_id": "11111111-1111-1111-1111-111111111111",
    "amount": 50000,
    "currency": "INR",
    "payment_method": "CARD",
    "card": {"number": "4111111111111111", "expiry_month": 12, "expiry_year": 2026, "cvv": "123"}
  }'

# 8. View Grafana dashboards
open http://localhost:3000   # admin / (value of GRAFANA_ADMIN_PASSWORD)
```

---

## Useful Makefile Targets

```bash
make up                    # Start all (dev hot-reload)
make up-prod               # Start all (production, no hot-reload)
make down                  # Stop all
make ps                    # Container status
make health                # Poll /health on all 14 services
make logs s=payment-service # Follow logs for one service
make shell s=fraud-service  # Open bash in container
make migrate-all           # Run Alembic for all 12 services
make test s=fraud-service   # Run pytest for one service
make test-all              # Run tests for all 9 core services
make seed                  # Re-seed test data
make setup-keycloak        # Configure Keycloak realm
make load-test             # Locust load test (fraud-service p95 < 100ms)
make load-test-ui          # Interactive Locust UI at :8089
make topics                # List Redpanda topics
make run-settlement d=2025-01-15  # Manually trigger settlement batch
make rbi-report start=2025-01-01 end=2025-01-31  # Download RBI CSV
```

---

## Known Limitations / Technical Debt

| Item | Detail |
|---|---|
| **Keycloak dev-mem** | `docker-compose.override.yml` uses `KC_DB=dev-mem` — all KC data lost on restart in dev. Run `make up-prod` for persistent Keycloak. |
| **Webhook delivery** | `webhook-service` test delivery is synchronous. Background delivery via Celery task is scaffolded but not connected yet. |
| **Net banking** | Bank redirect is mocked. Real banks require bank-specific signed parameter formats (not implemented). |
| **DigiLocker KYC** | `kyc-service` only has MOCK and MANUAL providers. DigiLocker OAuth integration is stubbed. |
| **Reporting PDFs** | Only CSV export is implemented. PDF via WeasyPrint/ReportLab is not built yet. |
| **Redis auth** | Redis has no password set in docker-compose. Add `requirepass` for production. |
| **Key rotation** | `card-vault-service` has key rotation API but no automated rotation job. |
| **NPCI live** | UPI is mock-only. Live NPCI integration requires PSP certification and API credentials. |
| **Vault key source** | In dev, if `CARD_ENCRYPTION_KEY_V1` is unset, an ephemeral key is generated at startup and logged as WARNING. Data encrypted with ephemeral key is lost on restart. |

---

*Last updated: Based on full codebase build session. ~294 Python files, 14 services, complete infrastructure.*
