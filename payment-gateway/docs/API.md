# Payment Gateway — Complete API Reference

**Base URL**: `https://api.{your-domain.com}`  
**API Version**: v1  
**Protocol**: HTTPS only (HTTP redirects to HTTPS)  
**Content-Type**: `application/json` (all requests and responses)  

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [Rate Limits](#2-rate-limits)
3. [Error Codes](#3-error-codes)
4. [Idempotency](#4-idempotency)
5. [Pagination](#5-pagination)
6. [Payment Service](#6-payment-service-port-8010)
7. [Card Vault Service](#7-card-vault-service-internal)
8. [Merchant Service](#8-merchant-service-port-8012)
9. [Fraud Service](#9-fraud-service-internal)
10. [UPI Service](#10-upi-service-port-8014)
11. [Settlement Service](#11-settlement-service-port-8015)
12. [Refund Service](#12-refund-service-port-8016)
13. [Notification Service](#13-notification-service-port-8017)
14. [KYC Service](#14-kyc-service-port-8018)
15. [Netbanking Service](#15-netbanking-service-port-8019)
16. [Transaction Service](#16-transaction-service-port-8020)
17. [Webhook Service](#17-webhook-service-port-8021)
18. [Reporting Service](#18-reporting-service-port-8022)
19. [Audit Service](#19-audit-service-internal)
20. [Webhooks — Event Delivery](#20-webhooks--event-delivery)
21. [SDK Examples](#21-sdk-examples)

---

## 1. Authentication

All API endpoints require one of two authentication methods:

### 1.1 Bearer JWT (Keycloak)

Obtain a token from Keycloak:

```bash
curl -X POST https://auth.{domain}/auth/realms/payment-gateway/protocol/openid-connect/token \
  -d "client_id=payment-backend" \
  -d "client_secret=YOUR_CLIENT_SECRET" \
  -d "username=YOUR_USERNAME" \
  -d "password=YOUR_PASSWORD" \
  -d "grant_type=password"
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiJ9...",
  "expires_in": 3600,
  "refresh_token": "eyJhbGciOiJIUzI1...",
  "token_type": "Bearer"
}
```

Use in requests:
```
Authorization: Bearer eyJhbGciOiJSUzI1NiJ9...
```

### 1.2 API Key

API keys are created via the Merchant Service. They are scoped to a single merchant.

```
X-Api-Key: sk_live_abc123_...
```

API keys are identified by their `key_prefix` but validated by their SHA-256 hash. The `full_key` is shown **exactly once** at creation time.

### 1.3 Internal Service-to-Service

Internal services (card-vault, fraud, audit) require an additional header:

```
X-Service-Token: {INTERNAL_SERVICE_TOKEN from .env}
```

### 1.4 Roles

| Role | Description |
|---|---|
| `MERCHANT_OWNER` | Full access to their own merchant resources |
| `ADMIN` | Platform-wide admin — can access all merchants |
| `COMPLIANCE_OFFICER` | Read-only access to audit logs, KYC, reports |
| `FINANCE_OPS` | Settlement management, payouts, RBI reports |
| `RISK_ANALYST` | Fraud rule management, blacklist operations |
| `SUPPORT` | Read-only customer support access |

---

## 2. Rate Limits

Rate limits are enforced by Traefik at the reverse proxy level.

| Endpoint Group | Limit | Burst | Window |
|---|---|---|---|
| `/v1/payments` | 100 req/min | 50 | 60s |
| `/v1/merchants` | 60 req/min | 30 | 60s |
| `/v1/reports` | 20 req/min | 10 | 60s |
| `/v1/upi` | 100 req/min | 50 | 60s |
| All others | 100 req/min | 50 | 60s |

Rate limited responses return HTTP **429 Too Many Requests**.

---

## 3. Error Codes

All errors follow this format:

```json
{
  "detail": "Human-readable message",
  "code": "MACHINE_READABLE_CODE",
  "request_id": "req_abc123"
}
```

| HTTP Status | Meaning |
|---|---|
| `400` | Bad Request — validation error |
| `401` | Unauthorized — missing or invalid token |
| `403` | Forbidden — insufficient role or merchant isolation |
| `404` | Not Found |
| `409` | Conflict — e.g. duplicate idempotency key |
| `422` | Unprocessable Entity — Pydantic validation failed |
| `429` | Too Many Requests — rate limit exceeded |
| `500` | Internal Server Error |
| `503` | Service Unavailable |

---

## 4. Idempotency

All mutating requests (`POST`, `PUT`) should include:

```
X-Idempotency-Key: {uuid-v4}
```

The idempotency key is stored for 24 hours. Duplicate requests with the same key return the original response without side effects.

---

## 5. Pagination

List endpoints use cursor or offset pagination.

**Offset (default):**
```
GET /v1/transactions?page=2&page_size=50
```

**Cursor (audit logs):**
```
GET /v1/audit/logs?cursor={opaque_cursor}&limit=50
```

**Standard list response:**
```json
{
  "items": [...],
  "total": 1234,
  "page": 2,
  "page_size": 50,
  "has_more": true
}
```

---

## 6. Payment Service (port 8010)

Handles card, UPI, and netbanking payments. The core transaction lifecycle service.

### 6.1 Create Payment

```
POST /v1/payments
```

**Request:**
```json
{
  "merchant_id": "11111111-1111-1111-1111-111111111111",
  "amount": 50000,
  "currency": "INR",
  "payment_method": "CARD",
  "card": {
    "number": "4111111111111111",
    "expiry_month": 12,
    "expiry_year": 2026,
    "cvv": "123",
    "cardholder_name": "John Doe"
  },
  "customer": {
    "email": "john@example.com",
    "phone": "+919876543210",
    "name": "John Doe"
  },
  "description": "Order #1234 — 2x Premium Widget",
  "order_id": "order_1234",
  "callback_url": "https://yourshop.com/payment/callback",
  "redirect_url": "https://yourshop.com/payment/success",
  "merchant_metadata": {
    "product_id": "widget-001",
    "customer_tier": "premium"
  }
}
```

**Response (201 Created):**
```json
{
  "id": "txn_abc123",
  "merchant_id": "11111111-1111-1111-1111-111111111111",
  "amount": 50000,
  "currency": "INR",
  "status": "CAPTURED",
  "payment_method": "CARD",
  "card_last4": "1111",
  "card_network": "VISA",
  "gateway_txn_id": "GW_XYZ789",
  "rrn": "512345678901",
  "auth_code": "A12345",
  "fraud_score": 0.12,
  "fraud_decision": "ALLOW",
  "authorized_at": "2025-01-15T10:30:00Z",
  "captured_at": "2025-01-15T10:30:01Z",
  "created_at": "2025-01-15T10:29:59Z"
}
```

**Payment Status Values:**
| Status | Description |
|---|---|
| `CREATED` | Payment record created, not yet processed |
| `PENDING` | Awaiting bank/acquirer response |
| `PROCESSING` | Being processed by acquirer |
| `AUTHORIZED` | Auth hold placed, not yet captured |
| `CAPTURED` | Money debited, awaiting settlement |
| `SETTLEMENT_INITIATED` | Settlement batch created |
| `SETTLED` | Funds transferred to merchant bank |
| `FAILED` | Payment failed — no charge |
| `CANCELLED` | Cancelled before processing |
| `REFUNDED` | Fully refunded |
| `PARTIALLY_REFUNDED` | Partially refunded |
| `DISPUTED` | Chargeback raised |

### 6.2 Get Payment

```
GET /v1/payments/{transaction_id}
```

**Response (200 OK):** Same as Create Payment response.

### 6.3 List Payments

```
GET /v1/payments?page=1&page_size=20&status=CAPTURED&start_date=2025-01-01&end_date=2025-01-31
```

**Query Parameters:**
| Param | Type | Description |
|---|---|---|
| `page` | integer | Page number (default 1) |
| `page_size` | integer | Items per page (max 200) |
| `status` | string | Filter by status |
| `payment_method` | string | CARD, UPI, NETBANKING |
| `start_date` | date | YYYY-MM-DD |
| `end_date` | date | YYYY-MM-DD |
| `order_id` | string | Filter by merchant order ID |

### 6.4 Capture Payment (Pre-Auth)

```
POST /v1/payments/{transaction_id}/capture
```

**Request:**
```json
{
  "amount": 50000
}
```

### 6.5 Cancel Payment

```
POST /v1/payments/{transaction_id}/cancel
```

### 6.6 Payment Events (Audit Trail)

```
GET /v1/payments/{transaction_id}/events
```

**Response:**
```json
[
  {
    "id": 1,
    "transaction_id": "txn_abc123",
    "from_status": null,
    "to_status": "CREATED",
    "triggered_by": "api",
    "message": "Payment created via API",
    "created_at": "2025-01-15T10:29:59Z"
  },
  {
    "id": 2,
    "from_status": "CREATED",
    "to_status": "CAPTURED",
    "triggered_by": "acquirer",
    "message": "Captured by Razorpay",
    "created_at": "2025-01-15T10:30:01Z"
  }
]
```

---

## 7. Card Vault Service (Internal)

> ⚠️ **PCI-DSS CDE Service** — Not publicly routable. Only callable from `payment-service` with `X-Service-Token`.

### 7.1 Tokenize Card

```
POST /vault/tokenize
X-Service-Token: {INTERNAL_SERVICE_TOKEN}
```

**Request:**
```json
{
  "card_number": "4111111111111111",
  "expiry_month": 12,
  "expiry_year": 2026,
  "cardholder_name": "John Doe",
  "merchant_id": "11111111-1111-1111-1111-111111111111"
}
```

**Response (201):**
```json
{
  "token": "tok_7f3a9b2c-...",
  "pan_last4": "1111",
  "pan_first6": "411111",
  "card_network": "VISA",
  "card_category": "CREDIT",
  "issuer_bank": "HDFC Bank",
  "is_domestic": true,
  "expires_at": "2026-12-31"
}
```

> The full PAN is **never** returned. CVV is discarded immediately after validation and never persisted.

### 7.2 Get Card Metadata

```
GET /vault/tokens/{token_id}/metadata
X-Service-Token: {INTERNAL_SERVICE_TOKEN}
```

### 7.3 Delete Token

```
DELETE /vault/tokens/{token_id}
X-Service-Token: {INTERNAL_SERVICE_TOKEN}
```

---

## 8. Merchant Service (port 8012)

### 8.1 Register Merchant

```
POST /v1/merchants/register
Authorization: Bearer {JWT}
```

**Request:**
```json
{
  "business_name": "Acme Payments Pvt Ltd",
  "business_type": "PRIVATE_LIMITED",
  "pan": "ABCDE1234F",
  "gstin": "27ABCDE1234F1Z5",
  "website_url": "https://acmepay.in",
  "support_email": "support@acmepay.in",
  "support_phone": "+919876543210",
  "business_category": "5411"
}
```

**Business Types:** `SOLE_PROPRIETOR`, `PARTNERSHIP`, `PRIVATE_LIMITED`, `PUBLIC_LIMITED`, `LLP`, `TRUST`, `NGO`, `GOVERNMENT`

**Response (201):**
```json
{
  "id": "33333333-3333-3333-3333-333333333333",
  "business_name": "Acme Payments Pvt Ltd",
  "business_type": "PRIVATE_LIMITED",
  "status": "DRAFT",
  "support_email": "su***rt@acmepay.in",
  "support_phone": "+91987***3210",
  "fee_config": {
    "card_mdr_percent": "2.0",
    "upi_flat_fee_paise": 0,
    "netbanking_flat_fee_paise": 1000,
    "gst_percent": "18"
  },
  "onboarding_checklist": {
    "pan_verified": false,
    "gstin_verified": false,
    "bank_account_added": false,
    "bank_verified": false,
    "kyc_docs_uploaded": false,
    "kyc_approved": false
  },
  "created_at": "2025-01-15T10:00:00Z"
}
```

**Merchant Status Flow:**
```
DRAFT → PENDING_KYC → ACTIVE → SUSPENDED → CLOSED
```

### 8.2 Get Merchant

```
GET /v1/merchants/{merchant_id}
Authorization: Bearer {JWT}   (MERCHANT_OWNER or ADMIN)
```

### 8.3 Update Merchant

```
PUT /v1/merchants/{merchant_id}
Authorization: Bearer {JWT}
```

```json
{
  "website_url": "https://new.acmepay.in",
  "display_name": "Acme Pay",
  "logo_url": "https://cdn.acmepay.in/logo.png",
  "business_category": "5812"
}
```

### 8.4 Onboarding Checklist

```
GET /v1/merchants/{merchant_id}/checklist
```

**Response:**
```json
{
  "pan_verified": true,
  "gstin_verified": true,
  "bank_account_added": true,
  "bank_verified": false,
  "kyc_docs_uploaded": true,
  "kyc_approved": false,
  "is_complete": false
}
```

### 8.5 KYC Document Upload

```
POST /v1/merchants/{merchant_id}/kyc/documents
Content-Type: multipart/form-data
```

| Field | Type | Description |
|---|---|---|
| `document_type` | string | `PAN`, `GSTIN`, `CANCELLED_CHEQUE`, `INCORPORATION_CERT`, `BOARD_RESOLUTION` |
| `file` | file | PDF, JPG, or PNG — max 5 MB |

**Response (201):**
```json
{
  "id": "doc_xyz456",
  "document_type": "PAN",
  "status": "PENDING",
  "file_size_bytes": 204800,
  "mime_type": "application/pdf",
  "original_filename": "pan_card.pdf",
  "created_at": "2025-01-15T10:05:00Z"
}
```

> In `ENVIRONMENT=development`, documents are **auto-approved after 3 seconds** via background task.

### 8.6 List KYC Documents

```
GET /v1/merchants/{merchant_id}/kyc/documents
```

### 8.7 Admin: Approve KYC

```
POST /v1/admin/kyc/{doc_id}/approve
Authorization: Bearer {JWT}   (COMPLIANCE_OFFICER or ADMIN)
```

### 8.8 Admin: Reject KYC

```
POST /v1/admin/kyc/{doc_id}/reject
Authorization: Bearer {JWT}   (COMPLIANCE_OFFICER or ADMIN)
```

```json
{
  "rejection_reason": "Document is blurry. Please re-upload a clear scan."
}
```

### 8.9 Add Bank Account

```
POST /v1/merchants/{merchant_id}/bank-accounts
```

```json
{
  "account_holder_name": "Acme Payments Pvt Ltd",
  "account_number": "987654321012",
  "ifsc_code": "HDFC0001234",
  "account_type": "CURRENT"
}
```

**Response (201):**
```json
{
  "id": "ba_xyz789",
  "account_holder_name": "Acme Payments Pvt Ltd",
  "account_number_last4": "1012",
  "ifsc_code": "HDFC0001234",
  "account_type": "CURRENT",
  "is_primary": false,
  "is_verified": false,
  "created_at": "2025-01-15T10:10:00Z"
}
```

### 8.10 Penny Drop (Bank Account Verification)

**Step 1: Initiate**
```
POST /v1/merchants/{merchant_id}/bank-accounts/{ba_id}/penny-drop
```

**Response:**
```json
{
  "status": "initiated",
  "expected_amount_paise": 2,
  "message": "Check your bank statement for a deposit of ₹0.02"
}
```

**Step 2: Verify**
```
POST /v1/merchants/{merchant_id}/bank-accounts/{ba_id}/verify
```

```json
{
  "stated_amount_paise": 2
}
```

**Response:**
```json
{
  "verified": true,
  "message": "Bank account verified successfully"
}
```

### 8.11 Create API Key

```
POST /v1/merchants/{merchant_id}/api-keys
```

```json
{
  "name": "Production Integration Key",
  "environment": "LIVE",
  "permissions": ["payments:read", "payments:write", "refunds:write"]
}
```

**Response (201):**
```json
{
  "id": "key_abc123",
  "name": "Production Integration Key",
  "key_prefix": "sk_live_abc123",
  "full_key": "sk_live_abc123_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "warning": "This key will not be shown again. Store it securely.",
  "environment": "LIVE",
  "permissions": ["payments:read", "payments:write", "refunds:write"],
  "created_at": "2025-01-15T10:15:00Z"
}
```

> ⚠️ **`full_key` is shown exactly once.** Store it in your secrets manager immediately.

### 8.12 List API Keys

```
GET /v1/merchants/{merchant_id}/api-keys
```

Returns list with `key_prefix` only — never the full key.

### 8.13 Revoke API Key

```
DELETE /v1/merchants/{merchant_id}/api-keys/{key_id}
```

### 8.14 Register Webhook

```
POST /v1/merchants/{merchant_id}/webhooks
```

```json
{
  "url": "https://yourshop.com/webhooks/payment",
  "events": ["payment.captured", "payment.failed", "refund.completed"]
}
```

**Response (201):**
```json
{
  "id": "wh_xyz123",
  "url": "https://yourshop.com/webhooks/payment",
  "events": ["payment.captured", "payment.failed", "refund.completed"],
  "webhook_secret": "a1b2c3d4e5f6...(64 hex chars)",
  "warning": "This secret will not be shown again. Store it securely.",
  "is_active": true,
  "created_at": "2025-01-15T10:20:00Z"
}
```

### 8.15 Merchant Dashboard (Quick Stats)

```
GET /v1/merchants/{merchant_id}/dashboard
```

**Response:**
```json
{
  "merchant_id": "11111111-...",
  "today_volume_paise": 2540000,
  "today_count": 47,
  "today_success_rate_pct": 94.68,
  "last_7_days": [
    {"date": "2025-01-15", "volume_paise": 2540000, "count": 47},
    {"date": "2025-01-14", "volume_paise": 3120000, "count": 61}
  ],
  "pending_settlements_paise": 18750000,
  "last_5_transactions": [...]
}
```

---

## 9. Fraud Service (Internal)

> ⚠️ **Called synchronously by payment-service.** p95 response time < 100ms.

### 9.1 Score Transaction

```
POST /v1/score
X-Service-Token: {INTERNAL_SERVICE_TOKEN}
```

**Request:**
```json
{
  "payment_id": "pay_abc123",
  "merchant_id": "11111111-...",
  "merchant_created_at": "2025-01-01T00:00:00Z",
  "merchant_mcc": "5411",
  "amount": 50000,
  "payment_method": "CARD",
  "card_token": "tok_xyz",
  "pan_first6": "411111",
  "ip_address": "27.1.2.3",
  "user_agent": "Mozilla/5.0...",
  "device_fingerprint": "fp_abc123",
  "customer_email_hash": "sha256(email)",
  "customer_phone_hash": "sha256(phone)"
}
```

**Response (200):**
```json
{
  "fraud_score": 0.18,
  "decision": "ALLOW",
  "reasons": [],
  "rule_hits": [],
  "evaluated_at": "2025-01-15T10:30:00.000Z"
}
```

**Decision Values:**
| Decision | Score Range | Action |
|---|---|---|
| `ALLOW` | 0.00–0.29 | Process payment normally |
| `CHALLENGE` | 0.30–0.69 | Require 3DS / additional verification |
| `BLOCK` | 0.70–1.00 | Reject payment immediately |

### 9.2 Admin: Add to Blacklist

```
POST /v1/admin/blacklist/{list_type}
Authorization: Bearer {JWT}   (RISK_ANALYST or ADMIN)
```

`list_type`: `ip`, `card`, `email`

```json
{
  "value": "1.2.3.4"
}
```

### 9.3 Admin: Remove from Blacklist

```
DELETE /v1/admin/blacklist/{list_type}/{value}
```

### 9.4 Admin: List Fraud Rules

```
GET /v1/admin/rules
Authorization: Bearer {JWT}   (RISK_ANALYST or ADMIN)
```

**Response:**
```json
[
  {
    "rule_name": "check_velocity_card",
    "is_active": true,
    "description": "Block if same card used >3 times in 60s",
    "weight": 1.0,
    "hit_count": 47,
    "created_at": "2025-01-01T00:00:00Z"
  }
]
```

### 9.5 Admin: Toggle Rule

```
POST /v1/admin/rules/{rule_name}/toggle
```

---

## 10. UPI Service (port 8014)

### 10.1 Initiate Collect Request

```
POST /v1/upi/collect
Authorization: Bearer {JWT}
```

```json
{
  "payment_id": "pay_abc123",
  "payer_vpa": "customer@hdfc",
  "amount": 50000,
  "description": "Order #1234",
  "expiry_seconds": 300,
  "merchant_vpa": "merchant@hdfc"
}
```

**VPA Format:** `{handle}@{bank}` — must match `^[a-zA-Z0-9._-]+@[a-zA-Z]+$`

**Response (201):**
```json
{
  "our_ref_id": "PG20250115103000123456",
  "npci_txn_id": "NPCI_TXN_XYZ789",
  "status": "PENDING",
  "expires_at": "2025-01-15T10:35:00Z"
}
```

**UPI Status Values:**
| Status | Description |
|---|---|
| `INITIATED` | QR/deep link generated, awaiting customer action |
| `PENDING` | Collect sent to NPCI, awaiting customer approval |
| `SUCCESS` | Payment completed |
| `FAILED` | Payment rejected or failed |
| `EXPIRED` | Collect request expired (default 5 min) |

### 10.2 Generate Intent (QR Code)

```
POST /v1/upi/intent
Authorization: Bearer {JWT}
```

```json
{
  "payment_id": "pay_xyz456",
  "amount": 50000,
  "merchant_vpa": "merchant@hdfc",
  "description": "Order #1235"
}
```

**Response:**
```json
{
  "our_ref_id": "PG20250115103100789012",
  "upi_deep_link": "upi://pay?pa=merchant@hdfc&pn=PaymentGateway&am=500.00&cu=INR&tn=Order+%231235&tr=PG2025...",
  "qr_code_base64": "iVBORw0KGgoAAAANS...",
  "expires_at": "2025-01-15T10:36:00Z"
}
```

### 10.3 Validate VPA

```
GET /v1/upi/vpa/{vpa}/validate
Authorization: Bearer {JWT}
```

**Response:**
```json
{
  "vpa": "customer@hdfc",
  "is_valid": true,
  "account_name": "John Doe",
  "bank_name": "HDFC Bank"
}
```

Cached in Redis for 5 minutes to avoid repeat NPCI calls.

### 10.4 Get Transaction Status

```
GET /v1/upi/transaction/{payment_id}/status
Authorization: Bearer {JWT}
```

**Response:**
```json
{
  "our_ref_id": "PG20250115103000123456",
  "npci_txn_id": "NPCI_TXN_XYZ789",
  "status": "SUCCESS",
  "completed_at": "2025-01-15T10:32:15Z",
  "decline_code": null,
  "decline_reason": null
}
```

### 10.5 NPCI Callback (No Auth — HMAC Validated)

```
POST /upi/callback
X-UPI-Signature: t={timestamp},v1={hmac_sha256}
```

This endpoint receives callbacks from NPCI. It is **not** under `/v1/` and does not require a Bearer token. Requests are validated using HMAC-SHA256.

### 10.6 UPI Mandates (Recurring)

#### Create Mandate
```
POST /v1/upi/mandates
```
```json
{
  "customer_vpa": "customer@hdfc",
  "amount": 99900,
  "frequency": "MONTHLY",
  "start_date": "2025-02-01",
  "end_date": "2026-01-31"
}
```

#### Get Mandate Status
```
GET /v1/upi/mandates/{mandate_id}
```

#### Execute Mandate Debit
```
POST /v1/upi/mandates/{mandate_id}/execute
```
```json
{"amount": 99900, "description": "Monthly subscription"}
```

#### Revoke Mandate
```
DELETE /v1/upi/mandates/{mandate_id}
```

---

## 11. Settlement Service (port 8015)

Handles T+1 batch settlement with automatic payout to merchant bank accounts.

### 11.1 List Settlement Batches

```
GET /v1/settlements?start_date=2025-01-01&end_date=2025-01-31&status=COMPLETED
Authorization: Bearer {JWT}   (MERCHANT_OWNER, FINANCE_OPS, or ADMIN)
```

**Response:**
```json
{
  "items": [
    {
      "id": "batch_abc123",
      "merchant_id": "11111111-...",
      "settlement_date": "2025-01-15",
      "gross_amount": 2540000,
      "fee_amount": 50800,
      "gst_on_fee": 9144,
      "net_amount": 2480056,
      "transaction_count": 47,
      "status": "COMPLETED",
      "created_at": "2025-01-15T17:30:00Z"
    }
  ]
}
```

**Settlement Status:**
| Status | Description |
|---|---|
| `PENDING` | Batch created, awaiting payout |
| `PROCESSING` | Payout in progress |
| `COMPLETED` | Funds transferred to merchant bank |
| `FAILED` | Payout failed — will retry |
| `RECONCILED` | Manually reconciled by finance ops |

### 11.2 Get Settlement Detail

```
GET /v1/settlements/{batch_id}
```

Returns batch + all constituent transactions + payout record with UTR number.

### 11.3 Monthly Summary

```
GET /v1/settlements/summary?year=2025
```

**Response:**
```json
[
  {
    "month": "2025-01",
    "batch_count": 31,
    "total_gross": 78500000,
    "total_fee": 1570000,
    "total_gst": 282600,
    "total_net": 76647400,
    "transaction_count": 1453
  }
]
```

### 11.4 Admin: Manual Trigger

```
POST /v1/admin/settlements/trigger
Authorization: Bearer {JWT}   (FINANCE_OPS or ADMIN)
```

```json
{
  "settlement_date": "2025-01-15"
}
```

**Response (202 Accepted):**
```json
{
  "status": "queued",
  "settlement_date": "2025-01-15"
}
```

### 11.5 Admin: Retry Failed Payout

```
POST /v1/admin/settlements/{batch_id}/retry-payout
```

### 11.6 Admin: RBI Report (CSV)

```
GET /v1/admin/reports/rbi?start_date=2025-01-01&end_date=2025-01-31
Authorization: Bearer {JWT}   (COMPLIANCE_OFFICER, FINANCE_OPS, or ADMIN)
```

Returns a CSV file with settlement details for RBI reporting.

---

## 12. Refund Service (port 8016)

### 12.1 Initiate Refund

```
POST /v1/refunds
Authorization: Bearer {JWT}   (MERCHANT_OWNER or ADMIN)
X-Idempotency-Key: {uuid}
```

```json
{
  "transaction_id": "txn_abc123",
  "amount": 10000,
  "reason": "Customer requested return",
  "refund_type": "PARTIAL",
  "idempotency_key": "refund-uuid-abc123"
}
```

**Rules:**
- `amount` must be ≤ `transaction.amount - transaction.refunded_amount`
- Transaction must be in `CAPTURED` or `SETTLED` status
- Partial refunds are supported (tracked via `refunded_amount`)

**Response (201):**
```json
{
  "id": "ref_xyz789",
  "transaction_id": "txn_abc123",
  "amount": 10000,
  "currency": "INR",
  "refund_type": "PARTIAL",
  "status": "PROCESSING",
  "gateway_refund_id": "RAZORPAY_REF_123",
  "created_at": "2025-01-15T11:00:00Z"
}
```

**Refund Status:**
| Status | Description |
|---|---|
| `INITIATED` | Refund record created |
| `PROCESSING` | Sent to acquirer |
| `SUCCESS` | Refund credited (3–5 business days to appear) |
| `FAILED` | Failed — check `error_message` |
| `REVERSED` | Refund reversed by bank |

### 12.2 Get Refund

```
GET /v1/refunds/{refund_id}
```

### 12.3 List Refunds for Payment

```
GET /v1/payments/{payment_id}/refunds
```

---

## 13. Notification Service (port 8017)

Sends email (via Resend or SMTP) and SMS (via Fast2SMS) on payment events.

Notifications are triggered automatically by Kafka events — you do not call this service directly from your integration.

**Supported Notification Types:**

| Event | Email | SMS |
|---|---|---|
| `payment.captured` | ✅ Payment success email | ✅ SMS to customer |
| `payment.failed` | ✅ Payment failed email | — |
| `refund.initiated` | ✅ Refund initiated email | — |
| `refund.completed` | ✅ Refund credited email | — |
| `settlement.completed` | ✅ Settlement advice to merchant | — |
| `merchant.kyc_completed` | ✅ KYC approved email | ✅ SMS |
| `merchant.kyc_rejected` | ✅ KYC rejected email | ✅ SMS |

### 13.1 Admin: List Notification Logs

```
GET /v1/notifications?status=FAILED&channel=EMAIL&page=1&page_size=20
Authorization: Bearer {JWT}   (ADMIN only)
```

---

## 14. KYC Service (port 8018)

Standalone KYC orchestration. Also accessible via Merchant Service for document uploads.

### 14.1 Initiate KYC Verification

```
POST /v1/kyc/verify
Authorization: Bearer {JWT}
```

```json
{
  "session_type": "PAN",
  "data": {
    "pan_number": "ABCDE1234F",
    "name_on_pan": "John Doe",
    "dob": "1990-01-15"
  },
  "provider": "MOCK"
}
```

**Session Types:** `PAN`, `GSTIN`, `BANK_ACCOUNT`, `AADHAAR`  
**Providers:** `MOCK` (dev), `MANUAL` (human review), `DIGILOCKER` (production)

**Response (201):**
```json
{
  "id": "kyc_abc123",
  "session_type": "PAN",
  "status": "VERIFIED",
  "provider": "MOCK",
  "verified_at": "2025-01-15T10:00:00Z"
}
```

### 14.2 Get KYC Status

```
GET /v1/kyc/verify/{session_id}
```

### 14.3 List KYC Sessions

```
GET /v1/kyc/sessions?merchant_id={id}
```

### 14.4 Admin: Approve / Reject

```
POST /v1/kyc/admin/{session_id}/approve
POST /v1/kyc/admin/{session_id}/reject?reason=Document+expired
```

---

## 15. Netbanking Service (port 8019)

### 15.1 List Supported Banks

```
GET /v1/netbanking/banks
```

**Response:**
```json
{
  "banks": [
    {"code": "HDFC",  "name": "HDFC Bank"},
    {"code": "ICICI", "name": "ICICI Bank"},
    {"code": "SBI",   "name": "State Bank of India"},
    {"code": "AXIS",  "name": "Axis Bank"}
  ],
  "count": 12
}
```

### 15.2 Initiate Netbanking Payment

```
POST /v1/netbanking/initiate
Authorization: Bearer {JWT}
```

```json
{
  "transaction_id": "txn_abc123",
  "bank_code": "HDFC",
  "amount": 50000,
  "return_url": "https://yourshop.com/payment/return",
  "description": "Order #1234"
}
```

**Response (201):**
```json
{
  "session_id": "nbs_xyz789",
  "redirect_url": "https://api.yourdomain.com/v1/netbanking/redirect/nbs_xyz789",
  "bank_code": "HDFC",
  "bank_name": "HDFC Bank",
  "expires_at": "2025-01-15T10:45:00Z"
}
```

**Flow:** Redirect customer to `redirect_url` → Bank handles payment → Bank POSTs to `/v1/netbanking/callback/{session_id}` → Customer returns to `return_url`.

### 15.3 Get Payment Status

```
GET /v1/netbanking/status/{transaction_id}
```

---

## 16. Transaction Service (port 8020)

Read-only query service over all transactions.

### 16.1 List Transactions

```
GET /v1/transactions
Authorization: Bearer {JWT}
```

**Query Parameters:**
| Param | Description |
|---|---|
| `page`, `page_size` | Pagination |
| `status` | Filter by status |
| `payment_method` | CARD, UPI, NETBANKING |
| `start_date`, `end_date` | Date range (YYYY-MM-DD) |
| `order_id` | Filter by merchant order ID |

### 16.2 Get Transaction

```
GET /v1/transactions/{transaction_id}
```

### 16.3 Transaction Stats

```
GET /v1/transactions/stats?period=7d
Authorization: Bearer {JWT}
```

**Period values:** `today`, `7d`, `30d`

**Response:**
```json
{
  "period": "7d",
  "total_count": 342,
  "success_count": 318,
  "failed_count": 24,
  "total_amount_paise": 17340000,
  "success_rate_pct": 92.98,
  "avg_ticket_paise": 50702,
  "by_method": {"CARD": 210, "UPI": 112, "NETBANKING": 20},
  "by_status": {"CAPTURED": 180, "SETTLED": 138, "FAILED": 24}
}
```

---

## 17. Webhook Service (port 8021)

Reliable event delivery to merchant-registered endpoints.

### 17.1 Register Endpoint

```
POST /v1/webhooks/endpoints
Authorization: Bearer {JWT}
```

```json
{
  "url": "https://yourshop.com/webhooks/payment",
  "events": ["payment.captured", "payment.failed", "refund.completed", "settlement.completed"]
}
```

### 17.2 List Endpoints

```
GET /v1/webhooks/endpoints
```

### 17.3 Delete Endpoint

```
DELETE /v1/webhooks/endpoints/{endpoint_id}
```

### 17.4 Delivery History

```
GET /v1/webhooks/deliveries?endpoint_id={id}&page=1&page_size=50
```

### 17.5 Test Endpoint

```
POST /v1/webhooks/endpoints/{endpoint_id}/test
```

**Delivery Retry Schedule:**

| Attempt | Delay |
|---|---|
| 1st retry | 10s |
| 2nd retry | 30s |
| 3rd retry | 2 min |
| 4th retry | 10 min |
| 5th retry | 30 min |
| Abandoned | After 5 failed attempts |

---

## 18. Reporting Service (port 8022)

### 18.1 Dashboard

```
GET /v1/reports/dashboard?merchant_id={id}
Authorization: Bearer {JWT}
```

Returns last 24h metrics.

### 18.2 Daily Summary

```
GET /v1/reports/daily?start_date=2025-01-01&end_date=2025-01-31
Authorization: Bearer {JWT}
```

### 18.3 Settlement Report

```
GET /v1/reports/settlements?start_date=2025-01-01&end_date=2025-01-31
Authorization: Bearer {JWT}
```

### 18.4 Export Transactions (CSV)

```
GET /v1/reports/export?start_date=2025-01-01&end_date=2025-03-31&format=csv
Authorization: Bearer {JWT}   (MERCHANT_OWNER, FINANCE_OPS, or ADMIN)
```

Max 92-day range per export.

### 18.5 GST Report

```
GET /v1/reports/gst?month=2025-01
Authorization: Bearer {JWT}   (FINANCE_OPS or COMPLIANCE_OFFICER)
```

Returns fee amounts, GST collected (18%), and net settlement by merchant.

---

## 19. Audit Service (Internal)

Append-only audit trail of all Kafka events.

### 19.1 List Audit Logs

```
GET /v1/audit/logs?cursor={cursor}&limit=50&service=payment-service&action=payment.captured
Authorization: Bearer {JWT}   (COMPLIANCE_OFFICER or ADMIN)
```

**Query Parameters:**
| Param | Description |
|---|---|
| `cursor` | Opaque pagination cursor |
| `limit` | Max 200 per page |
| `service` | Filter by service name |
| `entity_type` | transaction, merchant, refund, etc. |
| `entity_id` | UUID of specific entity |
| `merchant_id` | Filter by merchant |
| `action` | Kafka topic / action name |
| `start_date`, `end_date` | Date range |

### 19.2 Export Audit Logs (CSV)

```
GET /v1/audit/logs/export?start_date=2025-01-01&end_date=2025-01-31
Authorization: Bearer {JWT}   (COMPLIANCE_OFFICER)
```

Max 31-day range.

### 19.3 Ingest HTTP Access Logs (Internal)

```
POST /v1/internal/kong-access-log
```

Called by Traefik/Kong access log plugin. No auth required (internal network only).

---

## 20. Webhooks — Event Delivery

When a payment event occurs, the gateway POSTs to all registered webhook endpoints.

### 20.1 Signature Verification

Every webhook delivery includes:
```
X-Webhook-Signature: t={timestamp},v1={hmac_sha256_signature}
X-Webhook-Event: payment.captured
X-Webhook-Delivery: {delivery_id}
```

**Verify in Python:**
```python
import hashlib, hmac, time

def verify_webhook(body: bytes, signature_header: str, secret: str) -> bool:
    parts = dict(p.split("=", 1) for p in signature_header.split(","))
    ts = parts.get("t", "")
    sig = parts.get("v1", "")
    
    # Reject if timestamp > 5 minutes old (replay protection)
    if abs(time.time() - int(ts)) > 300:
        return False
    
    expected = hmac.new(
        secret.encode(),
        f"{ts}.{body.decode()}".encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(sig, expected)
```

### 20.2 Event Payloads

**`payment.captured`**
```json
{
  "event": "payment.captured",
  "created_at": "2025-01-15T10:30:00Z",
  "data": {
    "payment_id": "txn_abc123",
    "merchant_id": "11111111-...",
    "amount": 50000,
    "currency": "INR",
    "payment_method": "CARD",
    "order_id": "order_1234",
    "captured_at": "2025-01-15T10:30:01Z"
  }
}
```

**`payment.failed`**
```json
{
  "event": "payment.failed",
  "data": {
    "payment_id": "txn_xyz",
    "error_code": "INSUFFICIENT_FUNDS",
    "error_message": "Card declined by issuing bank"
  }
}
```

**`refund.completed`**
```json
{
  "event": "refund.completed",
  "data": {
    "refund_id": "ref_xyz789",
    "transaction_id": "txn_abc123",
    "amount": 10000,
    "currency": "INR",
    "utr_number": "UTR20250115...",
    "completed_at": "2025-01-17T14:00:00Z"
  }
}
```

**`settlement.completed`**
```json
{
  "event": "settlement.completed",
  "data": {
    "batch_id": "batch_abc",
    "settlement_date": "2025-01-15",
    "net_amount_paise": 2480056,
    "utr_number": "UTR20250116...",
    "bank_account_last4": "1012"
  }
}
```

---

## 21. SDK Examples

### 21.1 Python SDK (httpx)

```python
import httpx
import uuid

class PaymentGatewayClient:
    def __init__(self, api_key: str, base_url: str = "https://api.yourdomain.com"):
        self.client = httpx.Client(
            base_url=base_url,
            headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
            timeout=30,
        )

    def create_payment(self, merchant_id: str, amount: int, **kwargs) -> dict:
        return self.client.post("/v1/payments", json={
            "merchant_id": merchant_id,
            "amount": amount,
            **kwargs
        }, headers={"X-Idempotency-Key": str(uuid.uuid4())}).json()

    def create_refund(self, transaction_id: str, amount: int, reason: str) -> dict:
        return self.client.post("/v1/refunds", json={
            "transaction_id": transaction_id,
            "amount": amount,
            "reason": reason,
            "idempotency_key": str(uuid.uuid4()),
        }).json()

# Usage
client = PaymentGatewayClient("sk_live_your_key_here")
payment = client.create_payment(
    merchant_id="11111111-...",
    amount=50000,
    payment_method="CARD",
    card={"number": "4111111111111111", "expiry_month": 12, "expiry_year": 2026, "cvv": "123"},
)
print(payment["status"])  # CAPTURED
```

### 21.2 JavaScript / Node.js

```javascript
const axios = require('axios');

const client = axios.create({
  baseURL: 'https://api.yourdomain.com',
  headers: { 'X-Api-Key': 'sk_live_your_key_here' },
  timeout: 30000,
});

async function createPayment(merchantId, amount, card) {
  const { data } = await client.post('/v1/payments', {
    merchant_id: merchantId,
    amount,
    payment_method: 'CARD',
    card,
  }, {
    headers: { 'X-Idempotency-Key': crypto.randomUUID() }
  });
  return data;
}
```

### 21.3 cURL Examples

**Create payment:**
```bash
curl -X POST https://api.yourdomain.com/v1/payments \
  -H "X-Api-Key: sk_live_abc123..." \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: $(uuidgen)" \
  -d '{
    "merchant_id": "11111111-1111-1111-1111-111111111111",
    "amount": 50000,
    "currency": "INR",
    "payment_method": "CARD",
    "card": {
      "number": "4111111111111111",
      "expiry_month": 12,
      "expiry_year": 2026,
      "cvv": "123",
      "cardholder_name": "Test User"
    },
    "customer": {"email": "test@example.com", "phone": "+919876543210"},
    "order_id": "order_001"
  }'
```

**UPI collect:**
```bash
curl -X POST https://api.yourdomain.com/v1/upi/collect \
  -H "X-Api-Key: sk_live_abc123..." \
  -H "Content-Type: application/json" \
  -d '{
    "payment_id": "'"$(uuidgen)"'",
    "payer_vpa": "customer@hdfc",
    "amount": 50000,
    "description": "Test UPI",
    "merchant_vpa": "merchant@hdfc"
  }'
```

**Validate VPA:**
```bash
curl https://api.yourdomain.com/v1/upi/vpa/customer@hdfc/validate \
  -H "X-Api-Key: sk_live_abc123..."
```

**Trigger settlement:**
```bash
curl -X POST https://api.yourdomain.com/v1/admin/settlements/trigger \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"settlement_date": "2025-01-15"}'
```

---

## Appendix A — Amount Format

All monetary amounts are in **integer paise** (1 INR = 100 paise).

| INR | Paise |
|---|---|
| ₹1 | 100 |
| ₹100 | 10,000 |
| ₹500 | 50,000 |
| ₹1,000 | 1,00,000 |
| ₹10,000 | 10,00,000 |

**Never use floats for money.** The API rejects non-integer amounts.

---

## Appendix B — Test Card Numbers

| Card Number | Network | Behaviour |
|---|---|---|
| `4111111111111111` | Visa | Always succeeds |
| `5500000000000004` | Mastercard | Always succeeds |
| `4000000000000002` | Visa | Always declined (`INSUFFICIENT_FUNDS`) |
| `4000000000009995` | Visa | Always declined (`FRAUD_DETECTED`) |

## Appendix C — Test UPI VPAs

| VPA | Behaviour |
|---|---|
| `success@upi` | Payment succeeds after 5s |
| `fail@upi` | Payment fails immediately (`U30`) |
| `timeout@upi` | Simulates 6s timeout |
| `invalid@xyz` | VPA resolution fails |
| `*@hdfc`, `*@oksbi`, etc. | Always resolves as valid |

## Appendix D — UPI Decline Codes

| Code | Meaning |
|---|---|
| `U30` | Transaction declined by payer bank |
| `U16` | Payer exceeded permitted per-transaction limit |
| `U68` | Mandate expired |
| `U78` | Invalid UPI PIN entered |
| `U99` | Transaction timed out |
| `ZA` | Payer PSP system error |

---

*Generated: 2025 · Payment Gateway v1.0 · For internal use only*
