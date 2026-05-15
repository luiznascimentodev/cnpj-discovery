#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/cnpj-discovery}"
COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.prod.yml)
PROFILES=(--profile demand-worker --profile domain-crawler)

cd "$APP_DIR"

if [[ ! -f .env ]]; then
  echo "Missing $APP_DIR/.env. Create production secrets on the VPS before deploying." >&2
  exit 1
fi

docker compose "${COMPOSE_FILES[@]}" "${PROFILES[@]}" config >/tmp/cnpj-discovery-compose.yml
docker compose "${COMPOSE_FILES[@]}" --profile etl build etl
docker compose "${COMPOSE_FILES[@]}" "${PROFILES[@]}" up -d --build \
  postgres \
  redis \
  api \
  enrichment \
  frontend \
  nginx \
  enrichment-demand-worker \
  domain-crawler-worker \
  domain-resolver-worker

# Apply any pending SQL migrations. Postgres' docker-entrypoint-initdb.d only
# runs on first volume init, so without this step new migrations added after
# the initial provisioning are silently skipped.
COMPOSE_FILES="${COMPOSE_FILES[*]}" scripts/apply-migrations.sh

# Recreate nginx after upstream containers are running so Docker DNS is resolved
# against the current container IPs after every deploy.
docker compose "${COMPOSE_FILES[@]}" "${PROFILES[@]}" up -d --force-recreate nginx

install -m 0755 scripts/nightly-etl.sh /usr/local/bin/cnpj-nightly-etl
cat >/etc/cron.d/cnpj-discovery <<'CRON'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
15 3 * * * root /usr/local/bin/cnpj-nightly-etl
CRON

docker compose "${COMPOSE_FILES[@]}" "${PROFILES[@]}" ps
