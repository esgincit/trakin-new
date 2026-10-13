#!/usr/bin/env bash
# Recreate a local test database from the migrations (plain Postgres, no Supabase needed).
# Usage: scripts/db-local-reset.sh [database-url]   (default: postgresql://postgres@localhost:5432/mytrakin_test)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="${1:-${TEST_DATABASE_URL:-postgresql://postgres@localhost:5432/mytrakin_test}}"
ADMIN_URL="${URL%/*}/postgres"
DB_NAME="${URL##*/}"; DB_NAME="${DB_NAME%%\?*}"

psql "$ADMIN_URL" -v ON_ERROR_STOP=1 -qc "drop database if exists \"$DB_NAME\" with (force)"
psql "$ADMIN_URL" -v ON_ERROR_STOP=1 -qc "create database \"$DB_NAME\""

psql "$URL" -v ON_ERROR_STOP=1 -q -f "$ROOT/supabase/tests/local_bootstrap.sql"
for f in "$ROOT"/supabase/migrations/*.sql; do
  echo "→ $(basename "$f")"
  psql "$URL" -v ON_ERROR_STOP=1 -q -f "$f"
done
echo "→ seed.sql"
psql "$URL" -v ON_ERROR_STOP=1 -q -f "$ROOT/supabase/seed.sql"
echo "Database ready: $URL"
