import { useState } from "react";

/* ── tiny helpers ─────────────────────────────────────────────────────────── */
function CopyBtn({ text }) {
  const [ok, setOk] = useState(false);
  const go = () => {
    navigator.clipboard.writeText(text.trim());
    setOk(true);
    setTimeout(() => setOk(false), 2000);
  };
  return (
    <button onClick={go} style={{
      padding:"5px 14px", fontSize:11, cursor:"pointer", borderRadius:5, fontWeight:500,
      background: ok ? "var(--color-background-success)" : "var(--color-background-primary)",
      color:      ok ? "var(--color-text-success)"       : "var(--color-text-secondary)",
      border:"0.5px solid var(--color-border-secondary)",
    }}>{ok ? "✓ Copied!" : "Copy prompt"}</button>
  );
}

function Tag({ t, color }) {
  const m = {
    blue:  { bg:"#E6F1FB", c:"#185FA5" },
    green: { bg:"#EAF3DE", c:"#3B6D11" },
    amber: { bg:"#FAEEDA", c:"#854F0B" },
    red:   { bg:"#FCEBEB", c:"#A32D2D" },
    teal:  { bg:"#E1F5EE", c:"#0F6E56" },
    purple:{ bg:"#EEEDFE", c:"#534AB7" },
    gray:  { bg:"#F1EFE8", c:"#5F5E5A" },
  };
  const s = m[color] || m.blue;
  return (
    <span style={{ fontSize:10, fontWeight:600, padding:"2px 8px", borderRadius:3,
      background:s.bg, color:s.c, whiteSpace:"nowrap" }}>{t}</span>
  );
}

/* ── prompt card ──────────────────────────────────────────────────────────── */
function PromptCard({ num, title, phase, tags=[], why, prompt, deps=[] }) {
  const phaseColors = { 1:"teal", 2:"blue", 3:"amber", 4:"purple", 5:"green" };
  return (
    <div style={{
      border:"0.5px solid var(--color-border-tertiary)",
      borderRadius:12, marginBottom:12, overflow:"hidden",
      background:"var(--color-background-primary)",
    }}>
      {/* header */}
      <div style={{
        padding:"14px 18px",
        background:"var(--color-background-secondary)",
        borderBottom:"0.5px solid var(--color-border-tertiary)",
        display:"flex", alignItems:"center", justifyContent:"space-between", gap:12,
      }}>
        <div style={{ display:"flex", alignItems:"center", gap:10 }}>
          <span style={{
            width:28, height:28, borderRadius:"50%", display:"flex",
            alignItems:"center", justifyContent:"center", fontSize:12, fontWeight:600,
            background:"var(--color-background-info)", color:"var(--color-text-info)",
            flexShrink:0,
          }}>{num}</span>
          <div>
            <div style={{ fontWeight:500, fontSize:14 }}>{title}</div>
            <div style={{ display:"flex", gap:5, marginTop:4, flexWrap:"wrap" }}>
              <Tag t={`Phase ${phase}`} color={phaseColors[phase]} />
              {tags.map(g => <Tag key={g.t} t={g.t} color={g.c} />)}
            </div>
          </div>
        </div>
        <CopyBtn text={prompt} />
      </div>

      {/* meta */}
      {(why || deps.length > 0) && (
        <div style={{
          padding:"10px 18px", fontSize:12, color:"var(--color-text-secondary)",
          borderBottom:"0.5px solid var(--color-border-tertiary)",
          display:"grid", gridTemplateColumns: deps.length ? "1fr 1fr" : "1fr", gap:12,
        }}>
          {why && (
            <div>
              <span style={{ fontWeight:500, color:"var(--color-text-primary)" }}>Why: </span>
              {why}
            </div>
          )}
          {deps.length > 0 && (
            <div>
              <span style={{ fontWeight:500, color:"var(--color-text-primary)" }}>Run after: </span>
              {deps.join(", ")}
            </div>
          )}
        </div>
      )}

      {/* prompt preview */}
      <div style={{ padding:"14px 18px" }}>
        <pre style={{
          fontFamily:"var(--font-mono)", fontSize:11.5, lineHeight:1.65,
          whiteSpace:"pre-wrap", wordBreak:"break-word", margin:0,
          color:"var(--color-text-secondary)",
          maxHeight:260, overflowY:"auto",
          background:"var(--color-background-secondary)",
          border:"0.5px solid var(--color-border-tertiary)",
          borderRadius:8, padding:"12px 14px",
        }}>{prompt.trim()}</pre>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════════
   ALL PROMPTS
══════════════════════════════════════════════════════════════════════════════ */

const PROMPTS = [

/* ─── PROMPT 1 ──────────────────────────────────────────────────────────────── */
{
  num: 1,
  title: "Monorepo scaffold + shared tooling",
  phase: 1,
  tags: [{ t:"Run first", c:"red" }, { t:"Foundation", c:"gray" }],
  why: "Every other prompt depends on this folder layout and shared pyproject.toml conventions.",
  deps: [],
  prompt: `You are building a production-grade Python payment gateway monorepo.
Create the COMPLETE folder structure and ALL base configuration files exactly as described.

# DIRECTORY TREE TO CREATE
payment-gateway/
├── shared/
│   ├── __init__.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── session.py
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── keycloak.py
│   │   └── api_key.py
│   ├── kafka/
│   │   ├── __init__.py
│   │   ├── producer.py
│   │   ├── consumer.py
│   │   └── topics.py
│   ├── cache/
│   │   ├── __init__.py
│   │   └── redis_client.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── encryption.py
│   │   ├── masking.py
│   │   ├── money.py
│   │   └── idempotency.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── enums.py
│   └── exceptions/
│       ├── __init__.py
│       └── handlers.py
├── services/
│   ├── payment-service/
│   ├── card-vault-service/
│   ├── merchant-service/
│   ├── upi-service/
│   ├── netbanking-service/
│   ├── settlement-service/
│   ├── refund-service/
│   ├── fraud-service/
│   ├── notification-service/
│   ├── reporting-service/
│   ├── audit-service/
│   ├── transaction-service/
│   ├── webhook-service/
│   └── kyc-service/
├── infra/
│   ├── traefik/
│   │   ├── traefik.yml
│   │   └── dynamic/
│   │       └── middleware.yml
│   ├── keycloak/
│   ├── prometheus/
│   │   └── prometheus.yml
│   └── grafana/
│       └── dashboards/
├── scripts/
│   ├── init_local.sh
│   └── seed_db.py
├── docker-compose.yml
├── docker-compose.override.yml
├── .env.example
├── .gitignore
├── Makefile
└── pyproject.toml  (root workspace config)

# FOR EACH SERVICE IN services/ CREATE:
services/{name}/
├── Dockerfile
├── pyproject.toml
├── .dockerignore
├── main.py
├── config.py
├── routers/
│   └── __init__.py
├── models/
│   └── __init__.py
├── schemas/
│   └── __init__.py
├── services/
│   └── __init__.py
├── dependencies.py
└── tests/
    ├── __init__.py
    └── conftest.py

# EXACT CONTENT FOR EACH FILE:

## pyproject.toml (per service) — use uv workspace member format:
[project]
name = "{service-name}"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.111.0",
  "uvicorn[standard]>=0.29.0",
  "sqlalchemy>=2.0.30",
  "alembic>=1.13.0",
  "asyncpg>=0.29.0",
  "pydantic>=2.7.0",
  "pydantic-settings>=2.2.0",
  "aiokafka>=0.11.0",
  "httpx>=0.27.0",
  "redis[asyncio]>=5.0.4",
  "python-jose[cryptography]>=3.3.0",
  "cryptography>=42.0.0",
  "structlog>=24.1.0",
  "prometheus-fastapi-instrumentator>=7.0.0",
  "celery[redis]>=5.4.0",
  "hvac>=2.1.0",
  "boto3>=1.34.0",
]
[tool.uv.sources]
shared = { workspace = true }

## Dockerfile (multi-stage, non-root, ARM64-compatible):
FROM python:3.12-slim AS base
WORKDIR /app
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

FROM base AS deps
COPY pyproject.toml .
RUN pip install --no-cache-dir uv && uv pip install --system -r pyproject.toml

FROM deps AS final
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY . .
COPY --from=build /app/shared /app/shared
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \\
  CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

## main.py (identical pattern for every service, SERVICE_NAME from env):
- FastAPI app with lifespan context manager
- Startup: init DB pool, init Redis pool, init Kafka producer, init encryption keys from Infisical
- Shutdown: close all connections gracefully
- Middleware: RequestIDMiddleware (inject X-Request-ID), LogSanitiserMiddleware (strip card numbers/CVV from logs using regex), CORSMiddleware
- Routers: include all routers from routers/ with prefix /v1
- Endpoints: GET /health → {status, service, version, uptime_seconds}, GET /metrics (Prometheus)
- Exception handlers: register all custom exceptions from shared.exceptions.handlers
- Structlog: configure JSON logging with service name, trace_id from request context

## config.py (pydantic-settings BaseSettings):
All settings loaded from environment with defaults:
DATABASE_URL, REDIS_URL, KAFKA_BOOTSTRAP_SERVERS, KEYCLOAK_URL,
KEYCLOAK_REALM, KEYCLOAK_CLIENT_ID, KEYCLOAK_CLIENT_SECRET,
SERVICE_NAME, ENVIRONMENT (dev/staging/prod), LOG_LEVEL,
INFISICAL_TOKEN, CARD_ENCRYPTION_KEY_VERSION,
INTERNAL_SERVICE_TOKEN, AWS_REGION, S3_KYC_BUCKET

## shared/db/base.py:
- SQLAlchemy 2.0 async engine with asyncpg driver
- Connection pool: min=5, max=20, overflow=10, pool_timeout=30
- Base declarative class with: id (UUID PK, default uuid4), created_at (TIMESTAMPTZ, server_default NOW()), updated_at (TIMESTAMPTZ, onupdate), is_deleted (Boolean, default False, indexed)
- SoftDeleteMixin that overrides default query filter
- set_rls_context(conn, merchant_id, is_admin) — sets PostgreSQL session variables for RLS

## shared/auth/keycloak.py:
- KeycloakTokenValidator: fetch JWKS from Keycloak /.well-known/openid-configuration, cache 1h
- validate_token(token) → TokenPayload(sub, email, roles, merchant_id, exp, jti)
- require_roles(*roles): FastAPI Depends factory — raises 403 if user lacks all listed roles
- get_current_user(): FastAPI Depends → TokenPayload
- verify_not_revoked(jti, redis): check token not in Redis blacklist
- Combined auth dependency: try Bearer JWT, fall back to x-api-key header (call shared/auth/api_key.py)

## shared/kafka/topics.py:
Define ALL topic name constants as class attributes on class Topics:
payment.initiated, payment.authorized, payment.captured, payment.failed, payment.cancelled,
refund.initiated, refund.processing, refund.completed, refund.failed,
upi.collect_initiated, upi.callback_received, upi.status_updated,
merchant.registered, merchant.kyc_doc_uploaded, merchant.kyc_completed, merchant.kyc_rejected,
settlement.batch_created, settlement.payout_initiated, settlement.completed, settlement.failed,
audit.events, dlq.payment_events, dlq.merchant_events

## shared/utils/encryption.py:
FieldEncryptor class:
- AES-256-GCM using Python cryptography library
- __init__(key_b64: str) — decode base64 key, assert 32 bytes
- encrypt(plaintext: str) → str: os.urandom(12) nonce, base64(nonce + ciphertext)
- decrypt(ciphertext: str) → str
- encrypt_fields(obj, fields): encrypt named fields on dict/model
- hash_field(value: str) → str: SHA-256 hex for searchable hash columns

## shared/utils/money.py:
- paise_to_rupees(paise: int) → str: "₹1,23,456.78" (Indian locale format)
- rupees_to_paise(rupees: Decimal) → int
- validate_amount(amount: int): raise if <= 0 or > 10_00_00_000 (₹1 crore max)
- format_inr(paise: int) → str

## shared/exceptions/handlers.py:
Custom exception hierarchy with code, message, http_status:
PaymentGatewayError (base), CardDeclinedError(402), FraudBlockedError(402),
DuplicateRequestError(409), MerchantInactiveError(403), InsufficientFundsError(402),
InvalidCardError(400), UpiDeclinedError(402), SettlementFailedError(500),
TokenNotFoundError(404), UnauthorizedError(401), ForbiddenError(403)
FastAPI exception handler: return {error: {code, message, param, request_id, timestamp}}

## Makefile targets:
make up              — docker compose up -d
make down            — docker compose down
make logs s=SERVICE  — docker compose logs -f SERVICE
make shell s=SERVICE — docker compose exec SERVICE bash
make migrate s=SVC   — docker compose exec SERVICE alembic upgrade head
make test s=SERVICE  — docker compose exec SERVICE pytest tests/ -v
make seed            — python scripts/seed_db.py
make build           — docker compose build
make ps              — docker compose ps

## .gitignore: include .env, __pycache__, *.pyc, .pytest_cache, *.egg-info, dist/, .venv/, node_modules/, *.log, letsencrypt/

## scripts/init_local.sh:
Wait for all services healthy (poll /health endpoints), run alembic migrations for all services, run seed_db.py, print status table.

Write COMPLETE working code for every file. No TODOs, no placeholders. All imports must be correct.`,
},

/* ─── PROMPT 2 ──────────────────────────────────────────────────────────────── */
{
  num: 2,
  title: "shared/ library — complete implementation",
  phase: 1,
  tags: [{ t:"Critical path", c:"red" }, { t:"All services depend on this", c:"gray" }],
  why: "All 14 services import from shared/. Must be complete before any service prompt.",
  deps: ["Prompt 1"],
  prompt: `Complete the shared/ library for the payment gateway. Write FULL working Python code for every file.

## shared/db/session.py
Async SQLAlchemy session factory:
\`\`\`python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from shared.db.base import Base
import structlog

log = structlog.get_logger()

def create_engine(database_url: str, pool_size: int = 10):
    return create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=10,
        pool_timeout=30,
        pool_pre_ping=True,
        echo=False,
    )

def create_session_factory(engine) -> async_sessionmaker:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db(session_factory: async_sessionmaker):
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
\`\`\`

## shared/auth/keycloak.py — full implementation:
- Import: httpx, jose (JWT), pydantic, structlog, redis.asyncio
- KeycloakConfig: url, realm, client_id, client_secret, jwks_cache_ttl=3600
- TokenPayload(BaseModel): sub:str, email:str, roles:list[str], merchant_id:str|None, exp:int, jti:str
- KeycloakTokenValidator class:
  * __init__(config): self._jwks_cache = None, self._jwks_fetched_at = 0
  * async get_jwks(): fetch /realms/{realm}/protocol/openid-connect/certs, cache in memory TTL
  * async validate_token(token:str) → TokenPayload:
    - decode header to get kid
    - find matching key in JWKS
    - jose.jwt.decode with RS256 algorithm, verify exp, iss, aud
    - extract merchant_id from custom claim
    - return TokenPayload
  * get_current_user() → FastAPI Depends(OAuth2PasswordBearer) that calls validate_token
  * require_roles(*roles): Depends factory returning inner async def that checks TokenPayload.roles

## shared/auth/api_key.py — full implementation:
- hash_api_key(key: str) → str: SHA-256 hex digest
- async validate_api_key(key: str, db: AsyncSession) → ApiKeyContext:
  * query api_keys table by key_hash
  * check is_active, not expired
  * update last_used_at, usage_count (fire-and-forget)
  * return ApiKeyContext(merchant_id, permissions, environment)
- get_api_key_header(): FastAPI Depends checking x-api-key header

## shared/cache/redis_client.py — full implementation:
ConnectionPool from URL, decode_responses=True, retry on timeout.
Implement ALL these async functions:
- get_idempotency(redis, merchant_id, key) → dict|None
- set_idempotency(redis, merchant_id, key, response, ttl=86400)
- check_rate_limit(redis, identifier, endpoint, limit, window=60) → (bool, int)
- record_velocity(redis, key, window_seconds, max_count, member) → bool (True = exceeded)
- is_blacklisted(redis, list_type: Literal["ip","card","email"], value) → bool
- add_to_blacklist(redis, list_type, value)
- cache_get(redis, key) → Any|None
- cache_set(redis, key, value, ttl=300)
- revoke_token(redis, jti, ttl_seconds)
- is_token_revoked(redis, jti) → bool
- acquire_lock(redis, key, ttl=30) → asynccontextmanager yielding bool

All functions must handle RedisError gracefully — log warning, fail open (return safe default).

## shared/kafka/producer.py — full implementation:
PaymentEventProducer:
- __init__(bootstrap_servers, source_service)
- async start(): AIOKafkaProducer with acks="all", enable_idempotence=True, compression_type="gzip"
- async stop()
- async publish(topic, event_type, payload, key=None, trace_id=None):
  Build BaseEvent(event_id=uuid4, event_type, source_service, trace_id, timestamp=utcnow, payload)
  Send as JSON. Log at DEBUG level.
- async publish_batch(events: list[tuple[topic, event_type, payload, key]])

BaseEvent dataclass: event_id, event_type, source_service, trace_id, timestamp, schema_version="1.0", payload

## shared/kafka/consumer.py — full implementation:
PaymentEventConsumer:
- __init__(topics, group_id, bootstrap_servers, dlq_topic)
- async start(): AIOKafkaConsumer, enable_auto_commit=False, auto_offset_reset="earliest"
- async stop()
- async consume(handler: Callable[[str, BaseEvent], Awaitable[None]]):
  Loop over messages, deserialize, call handler, commit on success.
  On exception: log error with full traceback, route to DLQ, still commit.
- async _route_to_dlq(original_msg, error_str): publish to dlq topic with original content + error details

## shared/utils/masking.py:
- mask_pan(pan: str) → str: "411111••••••1111"
- mask_phone(phone: str) → str: "+91•••••43210"
- mask_email(email: str) → str: "r••i@example.com"
- mask_vpa(vpa: str) → str: "r••i@hdfc"
- LogSanitiser: regex-based scrubber for log entries:
  * PAN pattern: 16-digit sequences → masked
  * CVV pattern: cvv/cvc followed by 3-4 digits → [REDACTED]
  * API key pattern: sk_live_xxxxx → sk_live_[REDACTED]
  * Card expiry: MM/YY or MM/YYYY → [REDACTED]

## shared/utils/idempotency.py:
IdempotencyMiddleware for Starlette:
- dispatch(request, call_next):
  * Only intercept POST requests with X-Idempotency-Key header
  * Extract merchant_id from request state (set by auth middleware)
  * Check Redis for existing response
  * If found: return cached response with X-Idempotency-Replayed: true header
  * If not found: call_next, cache response body + status code in Redis 24h

## shared/models/enums.py:
All Python Enum classes matching the PostgreSQL enums exactly:
MerchantStatus, BusinessType, TransactionStatus, PaymentMethod, FraudDecision,
SettlementStatus, PayoutStatus, PayoutMethod, RefundStatus, RefundSource,
KycDocumentType, KycDocumentStatus, UpiStatus, NotificationType, NotificationStatus,
CardNetwork, CardCategory, Environment (LIVE/SANDBOX)

Write all code completely. Every import at the top. No type: ignore comments. Full type annotations throughout. Use | None instead of Optional. Use list[str] instead of List[str].`,
},

/* ─── PROMPT 3 ──────────────────────────────────────────────────────────────── */
{
  num: 3,
  title: "Payment Service — orchestration engine",
  phase: 2,
  tags: [{ t:"Core service", c:"blue" }, { t:"State machine", c:"teal" }],
  why: "The central payment orchestrator. All payment flows route through this service.",
  deps: ["Prompt 1", "Prompt 2"],
  prompt: `Build the complete Payment Service (services/payment-service/).
This is the core orchestration layer — it receives payment requests, coordinates with other services, and manages the payment state machine.

# DATABASE MODEL (models/payment.py)
SQLAlchemy 2.0 async model — table name: transactions
All columns exactly as in the schema SQL:
id, merchant_id, amount (BigInteger CHECK > 0), currency (default INR),
captured_amount, refunded_amount (default 0),
status (Enum: TransactionStatus), payment_method (Enum: PaymentMethod),
card_token (UUID nullable), card_last4, card_network,
upi_vpa (encrypted), upi_txn_id, bank_code, wallet_name, wallet_txn_id,
gateway_txn_id, acquirer_ref_no, rrn, auth_code, bank_txn_id,
idempotency_key (UNIQUE NOT NULL), customer_email (encrypted), customer_phone (encrypted),
customer_name (encrypted), customer_id,
ip_address (String/INET), user_agent, device_fingerprint,
fraud_score (Numeric 4,3), fraud_decision (Enum), rule_hits (JSON default []),
three_ds_status, three_ds_eci, three_ds_cavv (encrypted), three_ds_xid,
order_id, description, merchant_metadata (JSON default {}),
callback_url, redirect_url, error_code, error_message,
authorized_at, captured_at, settled_at, failed_at, cancelled_at, created_at, updated_at

TransactionEvent model (table: transaction_events):
id (BigInteger), transaction_id FK, from_status (Enum nullable), to_status (Enum),
triggered_by (str), actor_id (UUID nullable), message (str), metadata (JSON), created_at

# STATE MACHINE (state_machine.py)
PaymentStateMachine class:
ALLOWED_TRANSITIONS dict:
  CREATED     → [PENDING, FAILED, CANCELLED]
  PENDING     → [PROCESSING, FAILED, CANCELLED]
  PROCESSING  → [AUTHORIZED, CAPTURED, FAILED]
  AUTHORIZED  → [CAPTURED, CANCELLED, FAILED]
  CAPTURED    → [SETTLEMENT_INITIATED, REFUNDED, PARTIALLY_REFUNDED, DISPUTED]
  SETTLEMENT_INITIATED → [SETTLED, FAILED]
  SETTLED     → [REFUNDED, PARTIALLY_REFUNDED, DISPUTED]
  FAILED      → []  (terminal)
  CANCELLED   → []  (terminal)

async def transition(payment, new_status, db, triggered_by, actor_id=None, message=None, metadata={}):
  1. Check transition allowed in ALLOWED_TRANSITIONS[payment.status]
  2. Raise InvalidTransitionError if not allowed (400 + current state info)
  3. old_status = payment.status
  4. payment.status = new_status
  5. Set timestamp column if applicable (captured_at on CAPTURED, etc.)
  6. Create TransactionEvent record
  7. await db.flush()
  8. Return payment

# SCHEMAS (schemas/payment.py) — Pydantic v2
PaymentCreateRequest:
  amount: int = Field(gt=0, le=100_000_00, description="Amount in paise")
  currency: str = Field(default="INR", pattern="^[A-Z]{3}$")
  payment_method: PaymentMethod
  card: CardDetails | None = None
  upi_vpa: str | None = None
  bank_code: str | None = None
  customer: CustomerDetails
  order_id: str | None = None
  description: str | None = None
  callback_url: HttpUrl | None = None
  metadata: dict = {}

CardDetails: number (16 digits Luhn validated), expiry_month (1-12), expiry_year (>=2024), cvv (3-4 digits), cardholder_name

CustomerDetails: email (EmailStr), phone (E.164 Indian: +91XXXXXXXXXX), name: str | None

PaymentResponse: id, merchant_id, amount, currency, status, payment_method, card_last4, card_network, order_id, gateway_txn_id, fraud_score, created_at, updated_at
  + action_required: dict | None (for 3DS redirect, UPI collect)

PaymentListResponse: items: list[PaymentResponse], total: int, cursor: str | None

# ROUTER (routers/payments.py)
POST /v1/payments
  Auth: require JWT (merchant) or API key
  Headers: X-Idempotency-Key (required, 400 if missing)
  Steps:
  1. Validate idempotency key — check Redis, return cached if exists
  2. Validate amount, currency, payment_method
  3. Begin DB transaction
  4. Create Payment record (status=CREATED)
  5. Flush to get ID
  6. Transition → PENDING
  7. Call fraud service (httpx POST /score, timeout=5s):
     If BLOCK → transition FAILED, return 402 FraudBlockedError
     If CHALLENGE → set fraud_decision, continue with 3DS
  8. Route to method handler:
     CARD: POST to card-vault-service /vault/tokenize, get token → call acquirer
     UPI: POST to upi-service /upi/collect or /upi/intent
     NETBANKING: POST to netbanking-service /netbanking/initiate
  9. Store result in payment record
  10. Transition to appropriate status
  11. Publish Kafka event: Topics.PAYMENT_INITIATED
  12. Cache response in Redis idempotency key
  13. Return PaymentResponse

GET /v1/payments
  Query: status, payment_method, from_date, to_date, order_id, cursor, limit (max 100)
  RLS: merchant can only see own transactions (set_rls_context)
  Return: PaymentListResponse with cursor-based pagination

GET /v1/payments/{payment_id}
  Return: PaymentResponse (mask sensitive: card_last4 only, no card_token, mask VPA)

POST /v1/payments/{payment_id}/capture
  Validate: status must be AUTHORIZED
  Call acquirer adapter .capture(gateway_txn_id, amount)
  Transition → CAPTURED
  Publish Topics.PAYMENT_CAPTURED
  Return: PaymentResponse

POST /v1/payments/{payment_id}/cancel
  Validate: status in [CREATED, PENDING, AUTHORIZED]
  If AUTHORIZED: call acquirer .void(gateway_txn_id)
  Transition → CANCELLED
  Return: PaymentResponse

GET /v1/payments/{payment_id}/events
  Return: list of TransactionEvent for timeline view

# ACQUIRER ADAPTERS (adapters/)
adapters/base.py — Abstract AcquirerAdapter(ABC):
  @abstractmethod async charge(token, amount, currency, metadata) → ChargeResult
  @abstractmethod async capture(txn_id, amount) → CaptureResult
  @abstractmethod async refund(txn_id, amount) → RefundResult
  @abstractmethod async void(txn_id) → VoidResult

adapters/mock.py — MockAcquirerAdapter(AcquirerAdapter):
  Test card behaviour:
  "4111111111111111" → always SUCCESS
  "4000000000000002" → always DECLINED (insufficient_funds)
  "4000000000000069" → always DECLINED (expired_card)
  "4000000000000119" → always ERROR (processing_error)
  All other cards: SUCCESS
  Delay: asyncio.sleep(0.2) to simulate network latency

adapters/razorpay.py — RazorpayAdapter(AcquirerAdapter): stub with HTTP calls to Razorpay API

# INTER-SERVICE HTTP CLIENT (services/http_client.py)
ServiceClient:
  - httpx.AsyncClient with base_url, default headers (X-Service-Token, X-Trace-ID), timeout=10s
  - Retry: 2 retries on 5xx with exponential backoff (0.5s, 1s)
  - Circuit breaker: track consecutive failures per service, open after 5 failures, half-open after 30s
  - Methods: get, post, put, delete — all return parsed JSON or raise ServiceUnavailableError

# ALEMBIC (migrations/)
alembic.ini pointing to DATABASE_URL from env
env.py: async migration using asyncpg
Initial migration: create transactions table + transaction_events table + all indexes

# TESTS (tests/)
conftest.py: pytest-asyncio, in-memory SQLite for unit tests, mock httpx client
test_state_machine.py: test every valid and invalid transition
test_payments_api.py: test POST /v1/payments (success, fraud block, duplicate idempotency key, invalid amount)
test_acquirer_mock.py: test all mock card behaviours

Write COMPLETE working code. All files. All imports. Full type annotations. No stubs.`,
},

/* ─── PROMPT 4 ──────────────────────────────────────────────────────────────── */
{
  num: 4,
  title: "Card Vault Service — PCI-CDE tokenization",
  phase: 2,
  tags: [{ t:"PCI-DSS CDE", c:"red" }, { t:"Isolated network", c:"amber" }],
  why: "The only service that touches raw PANs. Must be on isolated cde_network Docker network.",
  deps: ["Prompt 2"],
  prompt: `Build the complete Card Vault Service (services/card-vault-service/).
This service lives in the PCI-CDE isolated Docker network. It is the ONLY service that EVER sees or stores a raw PAN. CVV is NEVER stored — not even encrypted.

# SECURITY RULES — ENFORCE THESE IN CODE, NOT JUST COMMENTS:
1. main.py: add middleware InternalServiceAuthMiddleware — every request must have
   X-Service-Token header matching INTERNAL_SERVICE_TOKEN from settings. Return 403 otherwise.
   Only allow requests where X-Forwarded-For or remote IP is on cde_network subnet.
2. NEVER log PAN, CVV, full card numbers — LogSanitiser from shared/utils/masking.py MUST be active
3. CVV received in tokenize request → used once, then del cvv from locals, never stored
4. All DB queries go to postgres-vault (VAULT_DATABASE_URL), NOT main DB

# DATABASE MODEL (models/card_token.py) — table: card_tokens (in card_vault_db)
id (UUID PK), token (UUID UNIQUE default uuid4),
pan_encrypted (Text NOT NULL), key_version (SmallInteger NOT NULL default 1),
pan_fingerprint (VARCHAR 64 NOT NULL),
pan_last4 (CHAR 4), pan_first6 (CHAR 6),
pan_length (SmallInteger default 16),
expiry_month (SmallInteger CHECK 1-12), expiry_year (SmallInteger),
cardholder_name (Text encrypted, nullable),
card_network (Enum: CardNetwork), card_category (Enum: CardCategory),
issuer_bank (VARCHAR 100, nullable), issuer_country (CHAR 2, nullable),
is_domestic (Boolean default True),
merchant_id (UUID NOT NULL), customer_id (UUID nullable),
is_active (Boolean default True), last_used_at, usage_count (Integer default 0),
expires_at (Date nullable), created_at

VaultAccessLog model — table: vault_access_log (append-only):
id (BigInteger), card_token (UUID), operation (VARCHAR 20: TOKENIZE/RETRIEVE/CHARGE/DELETE/ROTATE),
requesting_service (VARCHAR 50), requesting_ip (String), trace_id, outcome, failure_reason, created_at

BinDatabase model — table: bin_database:
bin (CHAR 6 PK), card_network (Enum), card_category (Enum), issuer_bank, issuer_country, is_domestic, updated_at

# ENCRYPTION (services/encryption.py)
CardVaultEncryptor:
  __init__(key_store: dict[int, bytes]): load keys by version number
  encrypt_pan(pan: str, key_version: int) → str: "v{version}:{base64(nonce+ciphertext)}"
  decrypt_pan(encrypted: str) → str: parse version prefix, decrypt with correct key
  rotate_key(old_version: int, new_version: int): decrypt with old, re-encrypt with new

async def load_keys_from_infisical(infisical_client) → dict[int, bytes]:
  Fetch CARD_ENCRYPTION_KEY_V1, V2, etc. from Infisical
  Return {1: bytes, 2: bytes, ...}

# LUHN & BIN DETECTION (utils/card_utils.py)
def luhn_check(pan: str) → bool: standard Luhn algorithm
def detect_network(pan: str) → CardNetwork:
  Visa: starts with 4
  Mastercard: starts with 51-55 or 2221-2720
  Amex: starts with 34 or 37
  RuPay: starts with 60, 6521, 6522, 6524-6525, 817
  Discover: starts with 6011, 622126-622925, 644-649, 65
  Otherwise: UNKNOWN
def detect_category(first6: str, db) → CardCategory: look up bin_database table
def is_card_expired(month: int, year: int) → bool: compare with current date

# SCHEMAS (schemas/)
TokenizeRequest: pan (str, Luhn validated), expiry_month, expiry_year, cvv (str, pattern ^[0-9]{3,4}$), cardholder_name (str|None), merchant_id (UUID), customer_id (UUID|None)
TokenizeResponse: token (UUID), last4, first6, card_network, card_category, issuer_bank, is_domestic, expires_at
CardMetadataResponse: token, last4, first6, card_network, card_category, issuer_bank, expiry_month, expiry_year, is_domestic (NO PAN EVER IN RESPONSE)
ChargeDataRequest: token (UUID) — no CVV field (PCI: CVV never stored, never returned)
ChargeDataResponse: pan (str), expiry_month, expiry_year (NO CVV — must be re-entered for card-on-file)

# ROUTER (routers/vault.py)
POST /vault/tokenize
  1. Validate Luhn → 400 if invalid
  2. Check card not expired → 400 if expired
  3. detect_network, detect_category from BIN table
  4. Compute fingerprint = SHA-256(pan)
  5. Check dedup: SELECT token WHERE fingerprint=X AND merchant_id=Y AND is_active=True
     → return existing token (same TokenizeResponse)
  6. Encrypt PAN with current key version
  7. del cvv  # immediately discard, never touch again
  8. INSERT card_tokens record
  9. INSERT vault_access_log (operation=TOKENIZE, outcome=success)
  10. Return TokenizeResponse (NO PAN, NO CVV)

POST /vault/charge-data  (INTERNAL ONLY — called by payment-service acquirer adapter)
  Rate limit: 1 call per token per 30 seconds (Redis)
  1. Lookup token → get pan_encrypted, key_version
  2. Decrypt PAN
  3. Log access (operation=CHARGE)
  4. Return ChargeDataResponse (pan + expiry ONLY, no CVV, no cardholder_name)
  NOTE: In response headers add: Cache-Control: no-store, no-cache

GET /vault/card/{token}/metadata
  Return CardMetadataResponse (safe fields only — no PAN, no encrypted data)

DELETE /vault/card/{token}
  Soft delete: is_active = False
  Log operation=DELETE

POST /vault/admin/rotate-key (Admin only, internal only)
  Body: {new_key_version: int}
  Background task: re-encrypt all active PANs from old version to new version in batches of 50
  Return immediately with job_id, status=started

GET /vault/admin/rotation-status/{job_id}
  Return progress of key rotation job

# HEALTH INCLUDES CDE STATUS:
GET /health: {status, service, vault_db_connected, current_key_version, total_tokens}

# TESTS:
test_luhn.py: valid and invalid Luhn numbers
test_tokenize.py: happy path, duplicate detection, expired card, invalid Luhn
test_encryption.py: encrypt/decrypt round-trip, key version parsing, rotation
test_internal_auth.py: requests without X-Service-Token return 403

Write COMPLETE working code. No stubs. Full implementation.`,
},

/* ─── PROMPT 5 ──────────────────────────────────────────────────────────────── */
{
  num: 5,
  title: "Merchant Service — onboarding, KYC, API keys",
  phase: 2,
  tags: [{ t:"KYC/KYB", c:"teal" }, { t:"API keys", c:"green" }],
  why: "Merchants must be onboarded before any transaction can be processed.",
  deps: ["Prompt 2"],
  prompt: `Build the complete Merchant Service (services/merchant-service/).

# MODELS (models/)

merchants.py — SQLAlchemy model for 'merchants' table (full schema from 01_schema_main.sql):
All columns including encrypted fields, fee_config JSONB, keycloak_group_id, etc.

merchant_bank_account.py — 'merchant_bank_accounts' table

kyc_document.py — 'kyc_documents' table

api_key.py — 'api_keys' table:
  id, merchant_id FK, name, key_prefix (UNIQUE), key_hash (UNIQUE),
  environment (LIVE/SANDBOX), permissions (JSON), last_used_at, last_used_ip,
  usage_count, expires_at, is_active, created_at

merchant_webhook.py — 'merchant_webhooks' table + 'webhook_deliveries' table

# SCHEMAS (schemas/)
MerchantRegisterRequest: business_name, business_type, pan (validated), gstin (optional, 15-char), website_url, support_email, support_phone, business_category (MCC code)
MerchantResponse: id, business_name (decrypted), business_type, status, created_at, fee_config, onboarding_checklist
OnboardingChecklist: pan_verified, gstin_verified, bank_account_added, bank_verified, kyc_docs_uploaded, kyc_approved

BankAccountRequest: account_holder_name, account_number, ifsc_code, account_type
KycDocumentUploadRequest: document_type (Enum), file (UploadFile)

ApiKeyCreateRequest: name, environment (LIVE/SANDBOX), permissions: list[str]
ApiKeyCreateResponse: id, name, key_prefix, full_key (ONLY returned here, hash stored), environment, permissions, created_at
  NOTE: full_key shown ONCE — response includes warning string

WebhookCreateRequest: url (HttpUrl, must be HTTPS), events: list[str]
WebhookCreateResponse: id, url, events, webhook_secret (shown ONCE), created_at

# SERVICES (services/)

merchant_service.py:
  async create_merchant(request, registering_user_id, db, keycloak, kafka):
    1. Validate PAN format (10 alphanumeric, starts with letter)
    2. Validate GSTIN format if provided (regex)
    3. Encrypt: business_name, pan, gstin, support_email, support_phone
    4. Hash: business_name (for search), pan, gstin
    5. INSERT merchant (status=DRAFT)
    6. Create Keycloak group: "merchant_{merchant_id}"
    7. Assign registering_user_id to that group with MERCHANT_OWNER role
    8. Update merchant.keycloak_group_id
    9. Publish Topics.MERCHANT_REGISTERED Kafka event
    10. Return merchant + onboarding_checklist

kyc_service.py:
  async upload_document(merchant_id, document_type, file, db, s3_client):
    1. Validate file type (PDF, JPG, PNG only), max 5MB
    2. Compute SHA-256 of file bytes
    3. Encrypt S3 key path (don't store plaintext path)
    4. Upload to R2/S3: key = merchants/{merchant_id}/{doc_type}/{uuid}.{ext}
       with ServerSideEncryption=AES256
    5. INSERT kyc_documents record (status=PENDING)
    6. Publish Topics.MERCHANT_KYC_DOC_UPLOADED
    7. If ENVIRONMENT=development: auto-approve after 3 seconds (background task)
    8. Return document record

  async approve_document(document_id, admin_user_id, db, kafka):
    UPDATE status=VERIFIED, verified_by, verified_at
    Check if all required docs now verified → if yes, update merchant status=ACTIVE
    Publish Topics.MERCHANT_KYC_COMPLETED

penny_drop_service.py:
  async initiate_penny_drop(bank_account_id, db):
    Generate random 1-2 paise amount
    Call Razorpay FundAccount validate API (or mock in dev)
    Store penny_drop_ref and penny_drop_amount
    Return {status: "initiated", expected_amount: X}

  async verify_penny_drop(bank_account_id, stated_amount, db):
    Compare stated_amount with penny_drop_amount in DB
    If match: is_verified=True, verified_at=now()
    Return {verified: bool}

api_key_service.py:
  async create_api_key(merchant_id, request, db):
    prefix = f"sk_{request.environment.lower()}_{secrets.token_urlsafe(8)}"
    secret = f"{prefix}_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(secret.encode()).hexdigest()
    INSERT api_keys(key_prefix=prefix, key_hash=key_hash, ...)
    Return ApiKeyCreateResponse(full_key=secret, ...)  # shown ONCE

  async revoke_api_key(key_id, merchant_id, db):
    UPDATE is_active=False WHERE id=key_id AND merchant_id=merchant_id

webhook_service.py:
  async create_webhook(merchant_id, request, db):
    secret = secrets.token_hex(32)
    secret_hash = hashlib.sha256(secret.encode()).hexdigest()
    INSERT merchant_webhooks(secret_hash=secret_hash, ...)
    Return WebhookCreateResponse(webhook_secret=secret)  # shown ONCE

  async send_test_webhook(webhook_id, merchant_id, db, http_client):
    Build test payload: {event: "test", data: {message: "webhook test"}}
    Sign with HMAC-SHA256 using stored secret
    POST to webhook URL with signed payload
    Log delivery in webhook_deliveries

# ROUTER (routers/)
merchants.py:
  POST   /v1/merchants/register          — public (authenticated user)
  GET    /v1/merchants/{id}              — MERCHANT_OWNER or ADMIN
  PUT    /v1/merchants/{id}              — MERCHANT_OWNER
  GET    /v1/merchants/{id}/checklist    — onboarding progress

kyc.py:
  POST   /v1/merchants/{id}/kyc/documents        — upload doc (multipart)
  GET    /v1/merchants/{id}/kyc/documents        — list docs
  POST   /v1/admin/kyc/{doc_id}/approve          — COMPLIANCE_OFFICER
  POST   /v1/admin/kyc/{doc_id}/reject           — COMPLIANCE_OFFICER

bank_accounts.py:
  POST   /v1/merchants/{id}/bank-accounts        — add bank account
  GET    /v1/merchants/{id}/bank-accounts        — list
  POST   /v1/merchants/{id}/bank-accounts/{ba_id}/penny-drop  — initiate
  POST   /v1/merchants/{id}/bank-accounts/{ba_id}/verify      — verify

api_keys.py:
  POST   /v1/merchants/{id}/api-keys          — create (returns full key ONCE)
  GET    /v1/merchants/{id}/api-keys          — list (prefix only, no full key)
  DELETE /v1/merchants/{id}/api-keys/{key_id} — revoke

webhooks.py:
  POST   /v1/merchants/{id}/webhooks               — register
  GET    /v1/merchants/{id}/webhooks               — list
  DELETE /v1/merchants/{id}/webhooks/{webhook_id}  — delete
  POST   /v1/merchants/{id}/webhooks/{webhook_id}/test — send test event

dashboard.py:
  GET /v1/merchants/{id}/dashboard:
    Return (all from main DB with RLS):
    - today_volume_paise, today_count, today_success_rate (%)
    - last_7_days: list of {date, volume, count}
    - pending_settlements_paise
    - last_5_transactions: list[PaymentResponse]

# ALEMBIC MIGRATION for all merchant-service tables

# TESTS:
test_registration.py, test_api_keys.py, test_webhooks.py, test_kyc_upload.py

Write COMPLETE working code. All files. Full implementation.`,
},

/* ─── PROMPT 6 ──────────────────────────────────────────────────────────────── */
{
  num: 6,
  title: "Fraud Detection Service — rules + ML scoring",
  phase: 2,
  tags: [{ t:"< 100ms p95", c:"red" }, { t:"Real-time sync", c:"amber" }],
  why: "Called synchronously by payment-service. Must respond under 100ms. Blocks bad transactions.",
  deps: ["Prompt 2"],
  prompt: `Build the complete Fraud Detection Service (services/fraud-service/).
CRITICAL: This service is called SYNCHRONOUSLY by payment-service. p95 response time MUST be under 100ms.
Every Redis operation must be pipelined. No DB queries in the hot path.

# RULES ENGINE (rules/engine.py)
RulesEngine class:
  __init__(redis, db): self.redis = redis, self.db = db

  HARD_BLOCK_RULES: list of async functions, each returns (hit: bool, reason: str)

  async check_ip_blacklist(context) → (bool, str):
    return await is_blacklisted(redis, "ip", context.ip_address), "ip_blacklist"

  async check_card_blacklist(context) → (bool, str):
    if context.card_fingerprint:
      return await is_blacklisted(redis, "card", context.card_fingerprint), "card_blacklist"
    return False, ""

  async check_velocity_card(context) → (bool, str):
    if context.card_token:
      exceeded = await record_velocity(redis, f"fraud:vel:card:{context.card_token}:60", 60, 3, context.payment_id)
      return exceeded, "velocity_card_60s"
    return False, ""

  async check_velocity_ip(context) → (bool, str):
    exceeded = await record_velocity(redis, f"fraud:vel:ip:{context.ip_address}:60", 60, 10, context.payment_id)
    return exceeded, "velocity_ip_60s"

  async check_velocity_email(context) → (bool, str):
    if context.customer_email_hash:
      exceeded = await record_velocity(redis, f"fraud:vel:email:{context.customer_email_hash}:3600", 3600, 5, context.payment_id)
      return exceeded, "velocity_email_1h"
    return False, ""

  SCORE_RULES: list of (async_fn, weight) tuples:

  async score_international_card(ctx) → float:
    if ctx.pan_first6 and is_international_bin(ctx.pan_first6) and is_indian_ip(ctx.ip_address):
      return 0.30
    return 0.0

  async score_odd_hour(ctx) → float:
    ist_hour = (datetime.utcnow() + timedelta(hours=5, minutes=30)).hour
    if 1 <= ist_hour <= 4: return 0.10
    return 0.0

  async score_round_amount(ctx) → float:
    if ctx.amount in [100000, 200000, 500000, 1000000, 2000000]: return 0.10
    return 0.0

  async score_new_merchant(ctx) → float:
    merchant_age = (datetime.utcnow() - ctx.merchant_created_at).days if ctx.merchant_created_at else 0
    if merchant_age < 7: return 0.15
    return 0.0

  async score_high_risk_mcc(ctx) → float:
    HIGH_RISK_MCC = {"7995", "5912", "5816", "7801", "7802"}
    if ctx.merchant_mcc in HIGH_RISK_MCC: return 0.20
    return 0.0

  async evaluate(context: ScoringContext) → ScoringResult:
    # 1. Run all hard-block rules concurrently
    block_tasks = [rule(context) for rule in HARD_BLOCK_RULES]
    block_results = await asyncio.gather(*block_tasks)
    for hit, reason in block_results:
      if hit:
        return ScoringResult(score=1.0, decision=FraudDecision.BLOCK, reasons=[reason], rule_hits=[reason])

    # 2. Run all score rules concurrently
    score_tasks = [rule(context) for rule, _ in SCORE_RULES]
    score_values = await asyncio.gather(*score_tasks)
    total_score = min(sum(score_values), 1.0)
    rule_hits = [SCORE_RULES[i][0].__name__ for i, s in enumerate(score_values) if s > 0]

    # 3. Decision
    if total_score < 0.30: decision = FraudDecision.ALLOW
    elif total_score < 0.70: decision = FraudDecision.CHALLENGE
    else: decision = FraudDecision.BLOCK

    return ScoringResult(score=total_score, decision=decision, reasons=rule_hits, rule_hits=rule_hits)

# ML MODEL (model/scorer.py)
FraudMLScorer:
  __init__(model_path): load sklearn IsolationForest from pickle on startup

  extract_features(context: ScoringContext) → np.ndarray:
    Return array: [log1p(amount), hour_of_day/24, day_of_week/7,
                   is_international*1.0, merchant_age_days/365, 0.5]
    # last feature is placeholder for customer_txn_count (Redis lookup optional)

  predict(context) → float: 0.0 to 1.0 score
    features = extract_features(context).reshape(1,-1)
    score = self.model.decision_function(features)[0]
    # Normalise IsolationForest score to 0-1 range
    return float(np.clip((score * -1 + 0.5), 0.0, 1.0))

  generate_toy_model(): train IsolationForest on synthetic data, save to model/fraud_v1.pkl
  Call generate_toy_model() in a __main__ block so it runs on first install.

# SCHEMAS (schemas/fraud.py)
ScoringRequest: payment_id (UUID), merchant_id (UUID), merchant_created_at (datetime|None), merchant_mcc (str|None), amount (int), card_token (UUID|None), card_fingerprint (str|None), pan_first6 (str|None), upi_vpa (str|None), payment_method (str), ip_address (str), user_agent (str|None), device_fingerprint (str|None), customer_email_hash (str|None), customer_phone_hash (str|None), billing_country (str|None)

ScoringResult: fraud_score (float), decision (FraudDecision), reasons (list[str]), rule_hits (list[str]), evaluated_at (datetime)

# ROUTER (routers/fraud.py)
POST /score
  1. Parse ScoringRequest
  2. Evaluate with RulesEngine (Redis calls) + MLScorer (CPU) concurrently:
     rules_task = asyncio.create_task(engine.evaluate(context))
     ml_score = ml_scorer.predict(context)  # sync, very fast
     rules_result = await rules_task
  3. If BLOCK from rules: return immediately (skip ML blend)
  4. Else blend: final_score = 0.6*rules_score + 0.4*ml_score
  5. Re-evaluate decision thresholds on blended score
  6. Return ScoringResult
  Target: < 100ms p95. Add Prometheus histogram: fraud_scoring_duration_seconds

POST /admin/blacklist/{list_type}  — RISK_ANALYST role
  Body: {value: str}
  Add to Redis SET + record in fraud_blacklist DB table

DELETE /admin/blacklist/{list_type}/{value}  — RISK_ANALYST role

GET /admin/rules
  Return fraud_rules from DB with hit_count (Redis counter) and is_active

POST /admin/rules/{rule_name}/toggle  — RISK_ANALYST role

# PROMETHEUS METRICS:
Counter: fraud_decisions_total{decision="ALLOW/CHALLENGE/BLOCK"}
Histogram: fraud_scoring_duration_seconds{le="0.05,0.1,0.2,0.5"}
Counter: fraud_rule_hits_total{rule_name="..."}

# TESTS (tests/)
test_rules_engine.py: mock Redis, test each hard-block and score rule
test_fraud_api.py: mock Redis + DB, test scoring endpoint response time assertion
test_velocity.py: test sliding window velocity counter logic

Write COMPLETE working code. All files. Full type annotations.`,
},

/* ─── PROMPT 7 ──────────────────────────────────────────────────────────────── */
{
  num: 7,
  title: "UPI Service — NPCI flows with mock client",
  phase: 3,
  tags: [{ t:"India-specific", c:"teal" }, { t:"Mock-first", c:"green" }],
  why: "Handles all UPI payments. Mock client simulates NPCI so you can build without TPAP approval.",
  deps: ["Prompt 2"],
  prompt: `Build the complete UPI Service (services/upi-service/).

# MODEL (models/upi_transaction.py) — table: upi_transactions (in main DB)
id, transaction_id (UUID not FK — cross-service ref), merchant_id (UUID),
our_ref_id (VARCHAR 50 UNIQUE), npci_txn_id (VARCHAR 100 nullable),
vpa_payer (Text encrypted, nullable), vpa_payee (VARCHAR 100),
payer_name (Text encrypted, nullable), amount (BigInteger),
status (Enum: UpiStatus), collect_expiry_at (TIMESTAMPTZ nullable),
upi_deep_link (Text nullable), qr_code_base64 (Text nullable),
decline_code (VARCHAR 10 nullable), decline_reason (Text nullable),
initiated_at (TIMESTAMPTZ default now), completed_at, callback_received_at,
raw_callback (JSON nullable — full NPCI payload for debug)

MerchantVpa model — table: merchant_vpas:
id, merchant_id (UUID), vpa (VARCHAR 100 UNIQUE), is_active (Boolean), created_at

# NPCI CLIENT INTERFACE (adapters/base.py)
Abstract NpciClient(ABC):
  @abstractmethod async resolve_vpa(vpa: str) → VpaResolution(is_valid, account_name, bank_name)
  @abstractmethod async send_collect(collect_req: CollectRequest) → CollectResponse
  @abstractmethod async check_status(our_ref_id: str) → StatusResponse
  @abstractmethod async validate_callback(headers, body) → bool

# MOCK CLIENT (adapters/mock_npci.py)
MockNpciClient(NpciClient):
  Known test VPAs:
    "success@upi" → resolve: valid, name="Test User", bank="HDFC Bank"
    "fail@upi" → resolve: valid but collect always fails
    "timeout@upi" → resolve: valid, collect times out after 5s
    "invalid@xyz" → resolve: invalid VPA
    Any other @upi / @hdfc / @sbi / @oksbi / @okaxis / @paytm etc → valid, name="Mock User"

  send_collect(req) → CollectResponse:
    - Generate our_ref_id: f"PG{datetime.now():%Y%m%d%H%M%S}{random 6 digits}"
    - If payer_vpa == "fail@upi": return status=FAILED, decline_code="U30"
    - If payer_vpa == "timeout@upi": await asyncio.sleep(6), return FAILED
    - Else: return status=PENDING (simulate async success after 5s)
    - Schedule background auto-resolution: asyncio.create_task(_resolve_after(ref_id, 5))

  async _resolve_after(ref_id, delay_seconds):
    await asyncio.sleep(delay_seconds)
    await _update_transaction_status(ref_id, UpiStatus.SUCCESS)
    await _publish_upi_completed_event(ref_id)

  generate_qr(vpa, amount, description) → str (base64 PNG):
    Use qrcode library: qrcode.make(upi_deep_link).save(buffer)
    Return base64.b64encode(buffer.getvalue()).decode()
    pip install qrcode[pil]

# SCHEMAS (schemas/upi.py)
CollectRequest: payment_id (UUID), payer_vpa (str, regex validated: r'^[a-zA-Z0-9._-]+@[a-zA-Z]+$'), amount (int > 0), description (str max 50 chars), expiry_seconds (int default 300 max 1800), merchant_vpa (str)
CollectResponse: our_ref_id, npci_txn_id (nullable), status (UpiStatus), expires_at, qr_code_base64 (nullable)

IntentRequest: payment_id, amount, merchant_vpa, description
IntentResponse: upi_deep_link, qr_code_base64, expires_at

VpaValidateResponse: vpa, is_valid (bool), account_name (str|None), bank_name (str|None)

UpiStatusResponse: our_ref_id, npci_txn_id, status, completed_at, decline_code, decline_reason

UpiCallbackPayload (for NPCI callback): txnId, refId, txnRef, amount, status, respCode, respMsg, payerVPA, payeeVPA, txnAuthDate

# SERVICES (services/upi_service.py)
UpiService:
  __init__(npci_client, db, redis, kafka_producer)

  async initiate_collect(payment_id, request, merchant_id) → CollectResponse:
    1. Validate payer_vpa format
    2. Lookup merchant_vpa from merchant_vpas table (or use default gateway VPA)
    3. Call npci_client.send_collect(CollectRequest(...))
    4. INSERT upi_transactions record
    5. Start polling task: asyncio.create_task(poll_until_terminal(our_ref_id))
    6. Return CollectResponse

  async generate_intent(payment_id, request, merchant_id) → IntentResponse:
    deep_link = f"upi://pay?pa={merchant_vpa}&pn=PaymentGateway&am={amount/100:.2f}&cu=INR&tn={desc}&tr={ref_id}"
    qr = npci_client.generate_qr(merchant_vpa, amount, desc)
    INSERT upi_transactions (status=INITIATED, upi_deep_link, qr_code_base64)
    Return IntentResponse

  async poll_until_terminal(our_ref_id, max_attempts=12):
    delays = [5, 10, 20, 30, 30, 30, 30, 30, 60, 60, 60, 60]
    for delay in delays:
      await asyncio.sleep(delay)
      result = await npci_client.check_status(our_ref_id)
      if result.status in [UpiStatus.SUCCESS, UpiStatus.FAILED, UpiStatus.EXPIRED]:
        await _finalize_transaction(our_ref_id, result)
        return
    await _expire_transaction(our_ref_id)

  async handle_callback(payload: UpiCallbackPayload, signature_header: str) → bool:
    # Validate HMAC-SHA256 signature from NPCI
    # Update upi_transactions status
    # Update callback_received_at, raw_callback
    # Publish Topics.UPI_CALLBACK_RECEIVED Kafka event
    # If SUCCESS: publish Topics.PAYMENT_CAPTURED via payment-service event

# ROUTER (routers/upi.py)
POST /v1/upi/collect         — initiate collect request
POST /v1/upi/intent          — generate payment link + QR
GET  /v1/upi/vpa/{vpa}/validate — validate VPA (cache 5min in Redis)
GET  /v1/upi/transaction/{payment_id}/status — get current status
POST /upi/callback           — NPCI webhook (no auth — HMAC validated internally)

# UPI MANDATE (UPI 2.0 recurring)
POST /v1/upi/mandates        — create subscription mandate
GET  /v1/upi/mandates/{id}   — status
POST /v1/upi/mandates/{id}/execute — debit against mandate
DELETE /v1/upi/mandates/{id} — revoke

UpiMandate model: id, merchant_id, customer_vpa, amount, frequency (DAILY/WEEKLY/MONTHLY), start_date, end_date, status, mandate_ref_id

# TESTS:
test_upi_collect.py: mock NPCI client, test collect flow, auto-resolution
test_vpa_validate.py: test VPA regex, mock client responses, Redis caching
test_callback.py: test HMAC validation, status update

Write COMPLETE working code. All files. Full implementation.`,
},

/* ─── PROMPT 8 ──────────────────────────────────────────────────────────────── */
{
  num: 8,
  title: "Settlement Service — T+1 batch jobs",
  phase: 3,
  tags: [{ t:"Celery", c:"purple" }, { t:"Financial critical", c:"red" }],
  why: "Handles all merchant payouts. Settlement math must be exact — always in paise, never floats.",
  deps: ["Prompt 2", "Prompt 5"],
  prompt: `Build the complete Settlement Service (services/settlement-service/) using FastAPI + Celery.

# MODELS (models/)
settlement_batch.py — table: settlement_batches (full schema from SQL)
settlement_transaction.py — table: settlement_transactions
settlement_payout.py — table: settlement_payouts

# FEE CALCULATOR (utils/fee_calculator.py)
CRITICAL: All arithmetic in integer paise. Never use float. Use Python Decimal only for percentage math, then convert to int.

FeeCalculator:
  calculate_fee(amount_paise: int, payment_method: PaymentMethod, fee_config: dict) → FeeBreakdown:
    FeeBreakdown: gross, fee_paise, gst_paise, net_paise

    CARD:
      mdr_pct = Decimal(str(fee_config["card_mdr_percent"]))
      fee = int((Decimal(amount_paise) * mdr_pct / 100).to_integral_value(ROUND_HALF_UP))

    UPI (per RBI mandate — no MDR for P2M below ₹2000 = 200000 paise):
      if amount_paise <= 200000: fee = 0
      else: fee = int(fee_config.get("upi_flat_fee_paise", 0))

    NETBANKING:
      fee = int(fee_config.get("netbanking_flat_fee_paise", 1000))

    gst_pct = Decimal(str(fee_config.get("gst_percent", 18)))
    gst = int((Decimal(fee) * gst_pct / 100).to_integral_value(ROUND_HALF_UP))
    net = amount_paise - fee - gst

    assert net >= 0, "Net cannot be negative"
    assert gross == fee + gst + net, "Fee components must sum to gross"
    return FeeBreakdown(gross=amount_paise, fee_paise=fee, gst_paise=gst, net_paise=net)

# CELERY TASKS (tasks/settlement.py)
@app.task(name="settlement.create_daily_batch", bind=True, max_retries=3, default_retry_delay=300)
def create_daily_batch(self, settlement_date_str: str):
  settlement_date = date.fromisoformat(settlement_date_str)
  with get_sync_db() as db:
    merchant_ids = db.execute(
      select(Transaction.merchant_id).where(
        Transaction.status == TransactionStatus.CAPTURED,
        func.date(Transaction.captured_at) == settlement_date,
      ).distinct()
    ).scalars().all()

    for merchant_id in merchant_ids:
      txns = db.execute(select(Transaction).where(
        Transaction.merchant_id == merchant_id,
        Transaction.status == TransactionStatus.CAPTURED,
        func.date(Transaction.captured_at) == settlement_date,
      )).scalars().all()

      fee_config = db.execute(select(Merchant.fee_config).where(Merchant.id == merchant_id)).scalar()
      gross = sum(t.captured_amount or t.amount for t in txns)
      fees = [fee_calculator.calculate_fee(t.captured_amount or t.amount, t.payment_method, fee_config) for t in txns]
      total_fee = sum(f.fee_paise for f in fees)
      total_gst = sum(f.gst_paise for f in fees)
      net = gross - total_fee - total_gst

      batch = SettlementBatch(merchant_id=merchant_id, settlement_date=settlement_date,
        gross_amount=gross, fee_amount=total_fee, gst_on_fee=total_gst,
        net_amount=net, transaction_count=len(txns), status=SettlementStatus.PENDING)
      db.add(batch); db.flush()

      for txn, fee in zip(txns, fees):
        db.add(SettlementTransaction(batch_id=batch.id, transaction_id=txn.id,
          amount=txn.captured_amount or txn.amount, fee=fee.fee_paise, gst=fee.gst_paise, net=fee.net_paise))
        txn.status = TransactionStatus.SETTLEMENT_INITIATED

      db.commit()
      initiate_payout.delay(str(batch.id))

@app.task(name="settlement.initiate_payout", bind=True, max_retries=5, default_retry_delay=600)
def initiate_payout(self, batch_id: str):
  with get_sync_db() as db:
    batch = db.get(SettlementBatch, batch_id)
    bank_account = db.execute(select(MerchantBankAccount).where(
      MerchantBankAccount.merchant_id == batch.merchant_id,
      MerchantBankAccount.is_primary == True,
      MerchantBankAccount.is_verified == True,
    )).scalar_one_or_none()

    if not bank_account:
      logger.error(f"No verified primary bank account for merchant {batch.merchant_id}")
      return

    payout = SettlementPayout(batch_id=batch.id, merchant_bank_account_id=bank_account.id,
      amount=batch.net_amount, payout_method=PayoutMethod.IMPS, status=PayoutStatus.INITIATED)
    db.add(payout); db.flush()

    result = payout_provider.create_payout(
      account_number=decrypt(bank_account.account_number),
      ifsc=bank_account.ifsc_code, amount=batch.net_amount, reference=str(batch.id))

    if result.success:
      payout.utr_number = result.utr
      payout.status = PayoutStatus.SUCCESS
      batch.status = SettlementStatus.COMPLETED
      for txn_id in [st.transaction_id for st in batch.settlement_transactions]:
        db.execute(update(Transaction).where(Transaction.id == txn_id).values(
          status=TransactionStatus.SETTLED, settled_at=datetime.utcnow()))
    else:
      payout.status = PayoutStatus.FAILED
      payout.failure_reason = result.error
      batch.status = SettlementStatus.FAILED
      self.retry(exc=Exception(result.error))

    db.commit()

# CELERY BEAT SCHEDULE (celeryconfig.py)
CELERYBEAT_SCHEDULE = {
  "daily-settlement-batch": {
    "task": "settlement.create_daily_batch",
    "schedule": crontab(hour=17, minute=30),  # 23:00 IST = 17:30 UTC
  },
  "daily-reconciliation": {
    "task": "settlement.reconcile",
    "schedule": crontab(hour=0, minute=30),   # 06:00 IST = 00:30 UTC
  },
}

# PAYOUT PROVIDER: Abstract PayoutProvider + MockPayoutProvider + RazorpayXProvider (stub)

# API ROUTES (routers/settlements.py)
GET  /v1/settlements                          — list batches
GET  /v1/settlements/{id}                     — detail
POST /v1/admin/settlements/trigger            — FINANCE_OPS manually trigger
POST /v1/admin/settlements/{id}/retry-payout  — retry failed
GET  /v1/settlements/summary                  — monthly merchant summary
GET  /v1/admin/reports/rbi                    — RBI CSV report (COMPLIANCE_OFFICER)

# TESTS: test_fee_calculator.py, test_batch_creation.py, test_reconcile.py

Write COMPLETE working code. Celery tasks sync. API routes async.`,
},

/* ─── PROMPT 9 ──────────────────────────────────────────────────────────────── */
{
  num: 9,
  title: "Notification + Refund + Audit Services",
  phase: 3,
  tags: [{ t:"Event-driven", c:"teal" }, { t:"3 services", c:"gray" }],
  why: "These three services share a common pattern: consume Kafka events, act, log. Build together.",
  deps: ["Prompt 2", "Prompt 3"],
  prompt: `Build THREE services in one pass. They share the same Kafka-consumer pattern.

──────────────────────────────────────────────────────
SERVICE 1: Notification Service (services/notification-service/)
──────────────────────────────────────────────────────

# MODEL — table: notification_logs
id (UUID PK), event_id (UUID), notification_type (Enum), recipient (Text encrypted),
template_id (str), status (Enum: NotificationStatus), attempts (SmallInt default 0),
last_attempt_at, delivered_at, error_message, provider_message_id, payload (JSON), created_at

# EMAIL TEMPLATES (templates/email/) — Jinja2 HTML, mobile-responsive, inline CSS:
  payment_success.html, payment_failed.html, refund_initiated.html,
  refund_completed.html, settlement_advice.html, kyc_approved.html, kyc_rejected.html

# EMAIL PROVIDER (providers/email.py)
ResendEmailProvider: POST https://api.resend.com/emails with Authorization: Bearer {RESEND_API_KEY}
SMTPEmailProvider: fallback using aiosmtplib

# SMS PROVIDER (providers/sms.py)
Fast2SMSProvider: POST https://www.fast2sms.com/dev/bulkV2

# CELERY TASKS (tasks/notification.py)
send_email_task: check idempotency via NotificationLog, render Jinja2 template, send, log
send_sms_task: same pattern

# KAFKA CONSUMER: Subscribe to payment.captured, payment.failed, refund.completed,
  settlement.completed, merchant.kyc_completed, merchant.kyc_rejected → dispatch Celery tasks

──────────────────────────────────────────────────────
SERVICE 2: Refund Service (services/refund-service/)
──────────────────────────────────────────────────────

# MODEL — table: refunds (full schema)

# SCHEMAS
RefundCreateRequest: transaction_id, amount (int > 0), reason (str max 500), notes, idempotency_key
RefundResponse: id, transaction_id, amount, status, gateway_refund_id, utr_number, processed_at, created_at

# REFUND SERVICE
async create_refund(request, merchant_id, initiated_by, db, http_client, kafka):
  1. Check idempotency_key uniqueness
  2. Fetch original transaction (must belong to merchant, status in [CAPTURED, SETTLED])
  3. Validate amount: amount <= (transaction.amount - transaction.refunded_amount)
  4. Create Refund record (status=INITIATED)
  5. Route: CARD → payment-service /internal/refund | UPI → upi-service /upi/refund
  6. Update transaction.refunded_amount, set REFUNDED or PARTIALLY_REFUNDED
  7. Publish Topics.REFUND_INITIATED
  8. Return RefundResponse

# ROUTER
POST /v1/refunds, GET /v1/refunds/{id}, GET /v1/payments/{payment_id}/refunds

──────────────────────────────────────────────────────
SERVICE 3: Audit Service (services/audit-service/)
──────────────────────────────────────────────────────

# AUDIT SERVICE
Records ALL Kafka events into append-only audit_logs table.

sanitise_for_audit(data: dict) → dict:
  Remove: pan, cvv, card_number, password, secret, key, token, otp
  Replace card-like values with "[REDACTED]"
  Max depth 3

# KAFKA CONSUMER: group_id="audit-consumers", subscribe to ALL topics
For each event: INSERT audit_logs (never UPDATE or DELETE)

# ROUTER (routers/audit.py)
GET /v1/audit/logs — COMPLIANCE_OFFICER or SUPER_ADMIN (cursor pagination)
GET /v1/audit/logs/export — CSV download, max 31 day range
POST /internal/kong-access-log — HTTP access log ingestion

Write COMPLETE working code for all three services. All imports. Full tests for each.`,
},

/* ─── PROMPT 10 ──────────────────────────────────────────────────────────────── */
{
  num: 10,
  title: "docker-compose.yml + Traefik + Prometheus + Makefile",
  phase: 4,
  tags: [{ t:"Infrastructure", c:"gray" }, { t:"Free stack", c:"green" }],
  why: "The glue that connects all 14 services. Must work on Oracle Cloud ARM A1 (free tier).",
  deps: ["All previous prompts"],
  prompt: `Generate the complete infrastructure configuration for the payment gateway free stack.
Target: Oracle Cloud ARM A1 (Ubuntu 22.04, 4 CPU, 24GB RAM). Zero paid services.

# docker-compose.yml (FULL — every service)
Networks: payment_network (bridge), cde_network (bridge, internal:true)
Volumes: postgres_main_data, postgres_vault_data, redis_data, redpanda_data, keycloak_data,
         traefik_letsencrypt, grafana_data, prometheus_data, infisical_data

INFRASTRUCTURE SERVICES:
  traefik (v3.0), postgres-main (16-alpine), postgres-vault (CDE network only),
  redis (7-alpine), redpanda + redpanda-init (create all 20 topics),
  keycloak (24.0), infisical, prometheus, grafana, glitchtip,
  celery-worker-settlement, celery-worker-notification, celery-beat

ALL 14 FASTAPI SERVICES with port map:
  payment-service:8010, card-vault-service:8011 (internal), merchant-service:8012,
  fraud-service:8013 (internal), upi-service:8014, settlement-service:8015,
  refund-service:8016, notification-service:8017, kyc-service:8018,
  netbanking-service:8019, transaction-service:8020, webhook-service:8021,
  reporting-service:8022, audit-service:8024 (internal)

Each service: image, build, restart:unless-stopped, env_file, depends_on (healthy),
networks, healthcheck, Traefik labels (skip for card-vault, audit, fraud)

# infra/traefik/traefik.yml
entryPoints: web(80→HTTPS redirect), websecure(443+TLS)
certificatesResolvers.letsencrypt.acme: httpChallenge, storage /letsencrypt/acme.json
providers.docker: exposedByDefault=false, network=payment_network
providers.file: /etc/traefik/dynamic, watch=true
metrics.prometheus: {}

# infra/traefik/dynamic/middleware.yml
payment-ratelimit (100/min), merchant-ratelimit (60/min), reports-ratelimit (20/min),
secure-headers (HSTS/nosniff/frame-deny), compress, dashboard-auth (basicAuth)

# infra/prometheus/prometheus.yml
Scrape all 14 services + traefik + postgres-exporter + redis-exporter

# Makefile — full targets:
up, down, logs, shell, build, ps, fresh, migrate, migrate-all, test, test-all, seed

migrate-all runs alembic for: merchant, payment, upi, settlement, refund, audit, notification, fraud

# docker-compose.override.yml
Every FastAPI service: volumes (live code mount), command (uvicorn --reload),
environment (ENVIRONMENT=development, DEBUG=true)

# .env.example — 60+ variables with comments, grouped by:
Environment, Databases, Redis, Kafka, Keycloak, Infisical, Services, Acquirer, UPI, Email, SMS, Storage, Security, Monitoring

Write EVERY file completely. All 14 service definitions. Complete Traefik config. Full Makefile.`,
},

/* ─── PROMPT 11 ──────────────────────────────────────────────────────────────── */
{
  num: 11,
  title: "Alembic migrations for all services",
  phase: 4,
  tags: [{ t:"DB migrations", c:"blue" }, { t:"Run last", c:"amber" }],
  why: "Creates all tables in correct order. Run after all service prompts are complete.",
  deps: ["Prompts 3–9"],
  prompt: `Generate Alembic migration files for ALL services in the payment gateway.

For EACH service create: alembic.ini, alembic/env.py, alembic/versions/0001_initial.py

ENV.PY (async pattern — same for all):
\`\`\`python
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from alembic import context
from app.config import settings
from shared.db.base import Base
from app.models import *  # noqa: F401, F403

target_metadata = Base.metadata

async def run_migrations_online():
    connectable = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(lambda conn: context.configure(
            connection=conn, target_metadata=target_metadata))
        async with connection.begin():
            await connection.run_sync(lambda conn: context.run_migrations())
    await connectable.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio
    asyncio.run(run_migrations_online())
\`\`\`

INITIAL MIGRATION PER SERVICE:

payment-service: transactions + transaction_events + indexes + RLS policies + updated_at trigger
  + CREATE EXTENSION IF NOT EXISTS "uuid-ossp"

merchant-service: merchants + merchant_bank_accounts + kyc_documents + api_keys +
  merchant_webhooks + webhook_deliveries + all indexes + RLS + triggers

settlement-service: settlement_batches + settlement_transactions + settlement_payouts + indexes

refund-service: refunds + RLS policy (merchant isolation) + indexes

upi-service: upi_transactions + merchant_vpas + upi_mandates + indexes

fraud-service: fraud_rules table + seed INSERT for all 12 default rules

audit-service: audit_logs PARTITION BY RANGE(created_at) + monthly partitions 2025-2026
  + REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM payment_app_user
  + GRANT INSERT, SELECT ON audit_logs TO payment_app_user

notification-service: notification_logs table

card-vault-service (VAULT_DATABASE_URL): card_tokens + key_versions + vault_access_log +
  bin_database + seed ~20 common BINs
  + REVOKE UPDATE, DELETE, TRUNCATE ON vault_access_log FROM vault_app_user

Also: payment-service 0002_add_dispute_table.py — dispute_chargebacks table

NOTES:
- Use op.execute() for raw SQL (RLS, triggers, REVOKE/GRANT)
- DROP POLICY IF EXISTS before CREATE POLICY (idempotent)
- CREATE OR REPLACE FUNCTION for triggers

Write COMPLETE alembic files for all 8 services. All tables. All constraints. Runnable.`,
},

];

/* ══════════════════════════════════════════════════════════════════════════════
   PHASES
══════════════════════════════════════════════════════════════════════════════ */

const PHASES = [
  { num:1, label:"Foundation",      color:"#0F6E56", bg:"#E1F5EE", prompts:[1,2] },
  { num:2, label:"Core services",   color:"#185FA5", bg:"#E6F1FB", prompts:[3,4,5,6] },
  { num:3, label:"Indian payments", color:"#854F0B", bg:"#FAEEDA", prompts:[7,8,9] },
  { num:4, label:"Infrastructure",  color:"#534AB7", bg:"#EEEDFE", prompts:[10,11] },
];

/* ══════════════════════════════════════════════════════════════════════════════
   APP
══════════════════════════════════════════════════════════════════════════════ */
export default function App() {
  const [filter, setFilter] = useState("all");

  const shown = filter === "all"
    ? PROMPTS
    : PROMPTS.filter(p => p.phase === Number(filter));

  return (
    <div style={{ fontFamily:"var(--font-sans)", maxWidth:920, margin:"0 auto", padding:"0 0 56px" }}>

      {/* header */}
      <div style={{ padding:"22px 0 18px" }}>
        <h1 style={{ fontSize:20, fontWeight:500, marginBottom:5 }}>Claude Code — Backend Build Prompts</h1>
        <p style={{ fontSize:13, color:"var(--color-text-secondary)", margin:0 }}>
          11 prompts · run in order · each builds on the previous · copy → paste into Claude Code
        </p>
      </div>

      {/* phase map */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:8, marginBottom:22 }}>
        {PHASES.map(ph => (
          <div key={ph.num}
            onClick={() => setFilter(filter === String(ph.num) ? "all" : String(ph.num))}
            style={{
              padding:"10px 12px", borderRadius:8, cursor:"pointer",
              background: filter === String(ph.num) ? ph.bg : "var(--color-background-secondary)",
              border:`0.5px solid ${filter === String(ph.num) ? ph.color+"55" : "var(--color-border-tertiary)"}`,
            }}>
            <div style={{ fontSize:10, fontWeight:600, color: filter === String(ph.num) ? ph.color : "var(--color-text-tertiary)", marginBottom:2 }}>PHASE {ph.num}</div>
            <div style={{ fontSize:13, fontWeight:500, color: filter === String(ph.num) ? ph.color : "var(--color-text-primary)" }}>{ph.label}</div>
            <div style={{ fontSize:11, color:"var(--color-text-tertiary)", marginTop:2 }}>Prompts {ph.prompts.join(", ")}</div>
          </div>
        ))}
      </div>

      {/* instructions */}
      <div style={{ background:"var(--color-background-secondary)", borderRadius:10, padding:"12px 16px", marginBottom:22, fontSize:12, color:"var(--color-text-secondary)", lineHeight:1.7 }}>
        <strong style={{ fontWeight:500, color:"var(--color-text-primary)" }}>How to use: </strong>
        Open Claude Code in your repo root (<code style={{ fontFamily:"var(--font-mono)", fontSize:11 }}>claude</code> command).
        Copy each prompt in order. Wait for it to finish before running the next.
        After Prompt 1 run <code style={{ fontFamily:"var(--font-mono)", fontSize:11 }}>make up</code> to start infrastructure.
        After Prompt 2 run <code style={{ fontFamily:"var(--font-mono)", fontSize:11 }}>make migrate-all</code>.
        Click a phase above to filter.
      </div>

      {/* prompts */}
      {shown.map(p => <PromptCard key={p.num} {...p} />)}

      {/* footer */}
      <div style={{ marginTop:32, padding:"16px 0", borderTop:"0.5px solid var(--color-border-tertiary)", fontSize:12, color:"var(--color-text-tertiary)", lineHeight:1.7 }}>
        After all 11 prompts: run <code style={{ fontFamily:"var(--font-mono)" }}>bash scripts/init_local.sh</code> to initialize the full stack.
        Then visit: api.localhost/health · auth.localhost (Keycloak) · monitor.localhost (Grafana) · secrets.localhost (Infisical)
      </div>
    </div>
  );
}
