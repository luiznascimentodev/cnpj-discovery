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

# Recreate nginx after upstream containers are running so Docker DNS is resolved
# against the current container IPs after every deploy.
docker compose "${COMPOSE_FILES[@]}" "${PROFILES[@]}" up -d --force-recreate nginx

docker compose "${COMPOSE_FILES[@]}" "${PROFILES[@]}" ps
