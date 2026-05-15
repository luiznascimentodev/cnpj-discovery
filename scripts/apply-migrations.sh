#!/usr/bin/env bash
# Applies db/migrations/*.sql files that haven't been recorded in the
# schema_migrations tracking table yet. Idempotent: re-running is a no-op.
#
# Each migration runs in its own transaction together with the bookkeeping
# INSERT, so a failure rolls the whole file back and the next run will retry it.
#
# Env vars (with defaults matching the docker-compose stack):
#   COMPOSE_FILES   compose -f flags (default: "-f docker-compose.yml -f docker-compose.prod.yml")
#   PG_SERVICE      compose service name (default: postgres)
#   PG_USER         postgres user (default: read from .env POSTGRES_USER)
#   PG_DB           postgres db   (default: read from .env POSTGRES_DB)
#   MIGRATIONS_DIR  path inside the postgres container (default: /docker-entrypoint-initdb.d)

set -euo pipefail

COMPOSE_FILES="${COMPOSE_FILES:--f docker-compose.yml -f docker-compose.prod.yml}"
PG_SERVICE="${PG_SERVICE:-postgres}"
MIGRATIONS_DIR="${MIGRATIONS_DIR:-/docker-entrypoint-initdb.d}"

if [[ -z "${PG_USER:-}" || -z "${PG_DB:-}" ]]; then
  if [[ -f .env ]]; then
    PG_USER="${PG_USER:-$(grep -E '^POSTGRES_USER=' .env | head -1 | cut -d= -f2-)}"
    PG_DB="${PG_DB:-$(grep -E '^POSTGRES_DB=' .env | head -1 | cut -d= -f2-)}"
  fi
fi

if [[ -z "${PG_USER:-}" || -z "${PG_DB:-}" ]]; then
  echo "apply-migrations: PG_USER and PG_DB must be set (or readable from .env)" >&2
  exit 1
fi

# shellcheck disable=SC2086
psql() {
  docker compose ${COMPOSE_FILES} exec -T "${PG_SERVICE}" psql -U "${PG_USER}" -d "${PG_DB}" -v ON_ERROR_STOP=1 "$@"
}

# Wait until postgres accepts connections (deploy-production.sh starts it just
# before us, so the healthcheck may still be settling).
for attempt in {1..30}; do
  if psql -tAc 'SELECT 1' >/dev/null 2>&1; then
    break
  fi
  if [[ ${attempt} -eq 30 ]]; then
    echo "apply-migrations: postgres did not become ready" >&2
    exit 1
  fi
  sleep 1
done

# Bookkeeping table.
psql >/dev/null <<'SQL'
CREATE TABLE IF NOT EXISTS schema_migrations (
  filename    TEXT PRIMARY KEY,
  applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
SQL

mapfile -t already_applied < <(psql -tA -c 'SELECT filename FROM schema_migrations ORDER BY filename' | sed '/^$/d')

is_applied() {
  local target="$1"
  for f in "${already_applied[@]:-}"; do
    [[ "$f" == "$target" ]] && return 0
  done
  return 1
}

# Backfill: any migration whose objects already exist in the live database
# (we adopted tracking mid-flight) gets marked as applied without rerunning.
# Concretely: if there are SQL files that pre-date this script, treat the
# bookkeeping table as the source of truth from this point on.
backfill_existing() {
  local file basename
  # `empresas` is one of the oldest core tables — if it exists and no rows are
  # in schema_migrations yet, assume everything currently on disk is already
  # applied except for the most recent file(s) that an operator may know about.
  if [[ ${#already_applied[@]} -gt 0 ]]; then
    return 0
  fi
  if ! psql -tAc "SELECT to_regclass('public.empresas') IS NOT NULL" | grep -q '^t$'; then
    return 0
  fi
  for file in db/migrations/*.sql; do
    basename="$(basename "$file")"
    psql >/dev/null <<SQL
INSERT INTO schema_migrations (filename) VALUES ('${basename}')
ON CONFLICT (filename) DO NOTHING;
SQL
  done
  echo "apply-migrations: backfilled $(ls db/migrations/*.sql | wc -l) pre-existing migrations"
  mapfile -t already_applied < <(psql -tA -c 'SELECT filename FROM schema_migrations ORDER BY filename' | sed '/^$/d')
}

backfill_existing

applied_count=0
shopt -s nullglob
for file in db/migrations/*.sql; do
  basename="$(basename "$file")"
  if is_applied "$basename"; then
    continue
  fi
  echo "apply-migrations: applying ${basename}"
  psql <<SQL
BEGIN;
\i ${MIGRATIONS_DIR}/${basename}
INSERT INTO schema_migrations (filename) VALUES ('${basename}');
COMMIT;
SQL
  applied_count=$((applied_count + 1))
done
shopt -u nullglob

if [[ ${applied_count} -eq 0 ]]; then
  echo "apply-migrations: no pending migrations"
else
  echo "apply-migrations: applied ${applied_count} migration(s)"
fi
