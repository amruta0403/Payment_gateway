#!/usr/bin/env bash
# =============================================================================
# setup_keycloak.sh — Create the payment-gateway realm, client, roles & users
# via the Keycloak Admin REST API.
#
# Usage:
#   ./scripts/setup_keycloak.sh
#   KC_URL=http://localhost:8080 KC_ADMIN=admin KC_PASS=admin ./scripts/setup_keycloak.sh
#
# Prerequisites: curl, jq, a running Keycloak instance
# =============================================================================
set -euo pipefail

# ── Config (override via env vars) ────────────────────────────────────────────
KC_URL="${KC_URL:-http://localhost:8080}"
KC_ADMIN="${KC_ADMIN:-admin}"
KC_PASS="${KC_ADMIN_PASSWORD:-${KC_PASS:-admin}}"
REALM="${KEYCLOAK_REALM:-payment-gateway}"
CLIENT_ID="${KEYCLOAK_CLIENT_ID:-payment-backend}"
CLIENT_SECRET="${KEYCLOAK_CLIENT_SECRET:-change-me-secret}"

# ── Helpers ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
info() { echo -e "${YELLOW}  → $*${NC}"; }
err()  { echo -e "${RED}  ✗ $*${NC}" >&2; }

curl_kc() {
  curl -sf --retry 3 --retry-delay 2 \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    "$@"
}

# ── Wait for Keycloak to be ready ─────────────────────────────────────────────
info "Waiting for Keycloak at $KC_URL ..."
for i in $(seq 1 30); do
  if curl -sf "$KC_URL/health/ready" >/dev/null 2>&1 || \
     curl -sf "$KC_URL/auth/realms/master" >/dev/null 2>&1; then
    ok "Keycloak is ready"
    break
  fi
  if [[ $i -eq 30 ]]; then
    err "Keycloak did not become ready within 60s"
    exit 1
  fi
  sleep 2
done

# ── Get admin token ────────────────────────────────────────────────────────────
info "Obtaining admin token ..."
# Try /auth/realms path (Keycloak with http-relative-path=/auth) first
TOKEN_URL="$KC_URL/auth/realms/master/protocol/openid-connect/token"
if ! curl -sf "$TOKEN_URL" >/dev/null 2>&1; then
  TOKEN_URL="$KC_URL/realms/master/protocol/openid-connect/token"
fi

TOKEN=$(curl -sf -X POST "$TOKEN_URL" \
  -d "client_id=admin-cli" \
  -d "username=$KC_ADMIN" \
  -d "password=$KC_PASS" \
  -d "grant_type=password" | jq -r '.access_token')

if [[ -z "$TOKEN" || "$TOKEN" == "null" ]]; then
  err "Failed to obtain admin token. Check KC_ADMIN / KC_PASS."
  exit 1
fi
ok "Admin token obtained"

# ── Detect admin base URL ─────────────────────────────────────────────────────
ADMIN_BASE="$KC_URL/auth/admin"
if ! curl_kc "$ADMIN_BASE/realms" >/dev/null 2>&1; then
  ADMIN_BASE="$KC_URL/admin"
fi

# ── Create realm ───────────────────────────────────────────────────────────────
info "Creating realm '$REALM' ..."
curl_kc -X POST "$ADMIN_BASE/realms" \
  -d "{
    \"realm\": \"$REALM\",
    \"enabled\": true,
    \"displayName\": \"Payment Gateway\",
    \"sslRequired\": \"external\",
    \"registrationAllowed\": false,
    \"loginWithEmailAllowed\": true,
    \"duplicateEmailsAllowed\": false,
    \"resetPasswordAllowed\": false,
    \"editUsernameAllowed\": false,
    \"accessTokenLifespan\": 3600,
    \"refreshTokenMaxReuse\": 10,
    \"bruteForceProtected\": true
  }" 2>/dev/null && ok "Realm '$REALM' created" || info "Realm '$REALM' already exists"

# ── Create client ──────────────────────────────────────────────────────────────
info "Creating client '$CLIENT_ID' ..."
curl_kc -X POST "$ADMIN_BASE/realms/$REALM/clients" \
  -d "{
    \"clientId\": \"$CLIENT_ID\",
    \"secret\": \"$CLIENT_SECRET\",
    \"enabled\": true,
    \"publicClient\": false,
    \"bearerOnly\": false,
    \"standardFlowEnabled\": true,
    \"directAccessGrantsEnabled\": true,
    \"serviceAccountsEnabled\": true,
    \"authorizationServicesEnabled\": false,
    \"redirectUris\": [\"*\"],
    \"webOrigins\": [\"*\"],
    \"protocol\": \"openid-connect\",
    \"attributes\": {
      \"access.token.lifespan\": \"3600\",
      \"use.refresh.tokens\": \"true\"
    }
  }" 2>/dev/null && ok "Client '$CLIENT_ID' created" || info "Client '$CLIENT_ID' already exists"

# ── Create realm roles ─────────────────────────────────────────────────────────
ROLES=(
  "MERCHANT_OWNER:Full access to merchant's own resources"
  "ADMIN:Platform administrator — full access"
  "COMPLIANCE_OFFICER:Read-only access to audit logs and KYC"
  "FINANCE_OPS:Settlement and payout management"
  "RISK_ANALYST:Fraud rules and blacklist management"
  "SUPPORT:Read-only customer support access"
)

info "Creating realm roles ..."
for role_entry in "${ROLES[@]}"; do
  role_name="${role_entry%%:*}"
  role_desc="${role_entry##*:}"
  curl_kc -X POST "$ADMIN_BASE/realms/$REALM/roles" \
    -d "{\"name\": \"$role_name\", \"description\": \"$role_desc\"}" \
    2>/dev/null && ok "  Role: $role_name" || info "  Role $role_name already exists"
done

# ── Helper: create user ────────────────────────────────────────────────────────
create_user_with_role() {
  local username="$1"
  local email="$2"
  local password="$3"
  local role="$4"
  local first_name="$5"
  local last_name="$6"

  info "Creating user '$username' ..."
  local user_id
  user_id=$(curl_kc -X POST "$ADMIN_BASE/realms/$REALM/users" \
    -d "{
      \"username\": \"$username\",
      \"email\": \"$email\",
      \"firstName\": \"$first_name\",
      \"lastName\": \"$last_name\",
      \"enabled\": true,
      \"emailVerified\": true,
      \"credentials\": [{
        \"type\": \"password\",
        \"value\": \"$password\",
        \"temporary\": false
      }]
    }" 2>/dev/null \
    && curl_kc "$ADMIN_BASE/realms/$REALM/users?username=$username" | jq -r '.[0].id' \
    || curl_kc "$ADMIN_BASE/realms/$REALM/users?username=$username" | jq -r '.[0].id')

  if [[ -z "$user_id" || "$user_id" == "null" ]]; then
    err "Could not create or find user $username"
    return 1
  fi

  # Assign role
  local role_id
  role_id=$(curl_kc "$ADMIN_BASE/realms/$REALM/roles/$role" | jq -r '.id')
  curl_kc -X POST "$ADMIN_BASE/realms/$REALM/users/$user_id/role-mappings/realm" \
    -d "[{\"id\": \"$role_id\", \"name\": \"$role\"}]" 2>/dev/null
  ok "  User '$username' created with role '$role'"
}

# ── Create test users ──────────────────────────────────────────────────────────
info "Creating test users ..."
create_user_with_role \
  "test-merchant"      "merchant@example.com"   "Test@1234!" \
  "MERCHANT_OWNER"     "Test" "Merchant"

create_user_with_role \
  "test-admin"         "admin@example.com"      "Admin@1234!" \
  "ADMIN"              "Test" "Admin"

create_user_with_role \
  "test-compliance"    "compliance@example.com" "Compliance@1234!" \
  "COMPLIANCE_OFFICER" "Test" "Compliance"

create_user_with_role \
  "test-finance"       "finance@example.com"    "Finance@1234!" \
  "FINANCE_OPS"        "Test" "Finance"

# ── Print summary ──────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Keycloak setup complete!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo ""
echo "  Realm:           $REALM"
echo "  Client ID:       $CLIENT_ID"
echo "  Client Secret:   $CLIENT_SECRET"
echo ""
echo "  Test users:"
echo "    test-merchant     / Test@1234!    (MERCHANT_OWNER)"
echo "    test-admin        / Admin@1234!   (ADMIN)"
echo "    test-compliance   / Compliance@1234! (COMPLIANCE_OFFICER)"
echo "    test-finance      / Finance@1234! (FINANCE_OPS)"
echo ""
echo "  Admin console: ${KC_URL}/auth/admin"
echo ""

# ── Test token acquisition ─────────────────────────────────────────────────────
info "Testing token acquisition for test-merchant ..."
TEST_TOKEN=$(curl -sf -X POST \
  "$TOKEN_URL" \
  -d "client_id=$CLIENT_ID&client_secret=$CLIENT_SECRET" \
  -d "username=test-merchant&password=Test%401234!" \
  -d "grant_type=password" | jq -r '.access_token // empty')

if [[ -n "$TEST_TOKEN" ]]; then
  ok "Token acquisition works for test-merchant"
else
  err "Token acquisition failed — check client secret and realm config"
fi
