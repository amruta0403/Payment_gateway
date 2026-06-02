#!/usr/bin/env bash
# Creates additional databases needed by keycloak, infisical, and glitchtip.
# Runs automatically on first postgres-main container start.
set -euo pipefail

POSTGRES_BINARY="psql --username=${POSTGRES_USER} --dbname=${POSTGRES_DB}"

for db in keycloak infisical glitchtip; do
    echo "==> Creating database: ${db}"
    ${POSTGRES_BINARY} <<-EOSQL
        SELECT 'CREATE DATABASE "${db}"'
        WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${db}')
        \gexec
EOSQL
    echo "    ✓ ${db}"
done

echo "==> All auxiliary databases ready."
