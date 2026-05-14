#!/usr/bin/env bash
set -euo pipefail

cd /opt/cnpj-discovery

LOG_DIR=/opt/cnpj-discovery/logs
mkdir -p "$LOG_DIR"

if docker ps --format "{{.Names}}" | grep -Eq "^cnpj-etl-(full-load|nightly)"; then
  echo "$(date -Is) ETL already running; skipping" >> "$LOG_DIR/nightly-etl.log"
  exit 0
fi

docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile trickle-worker stop enrichment-trickle-worker >/dev/null 2>&1 || true

set +e
{
  docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile etl run --rm --name cnpj-etl-nightly etl python main.py check-public-data
  CHECK_STATUS=$?
  if [[ "$CHECK_STATUS" -eq 0 ]]; then
    docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile etl run --rm --name cnpj-etl-nightly-refresh etl python main.py refresh-active-only-if-updated
    STATUS=$?
  else
    STATUS="$CHECK_STATUS"
  fi
} >> "$LOG_DIR/nightly-etl.log" 2>&1
set -e

docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile trickle-worker up -d enrichment-trickle-worker >/dev/null 2>&1 || true

exit "$STATUS"
