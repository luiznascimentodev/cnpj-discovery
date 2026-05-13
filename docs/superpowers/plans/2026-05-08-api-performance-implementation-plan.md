# API Performance Implementation Plan

**Date:** 2026-05-08  
**Status:** Proposed, not implemented  
**Scope:** FastAPI/Postgres/Redis performance for public API search, company detail, status and exports.

Related code:

- `api/database.py`
- `api/cache.py`
- `api/services/query_builder.py`
- `api/routers/prospecting.py`
- `api/routers/empresa.py`
- `api/routers/export.py`
- `api/routers/status.py`
- `db/migrations/004_indexes.sql`
- `db/migrations/005_filters_indexes.sql`
- `db/migrations/009_prospecting_search_indexes.sql`

---

## Goal

Improve API throughput and latency without changing the stack or rewriting the service.

The goal is to make the existing Python/FastAPI API consistently fast by:

1. measuring the real slow queries with `EXPLAIN ANALYZE`;
2. adding only indexes that match observed query plans;
3. using Redis with explicit cache policy and invalidation/versioning;
4. standardizing cursor pagination;
5. moving expensive aggregations to materialized views or summary tables;
6. moving heavy exports to asynchronous jobs;
7. configuring Postgres pooling from environment and optionally PgBouncer.

Non-goal: migrate the API to Laravel, C#, C++ or another stack.

---

## Current State Summary

Already present:

- `asyncpg` pool in `api/database.py`.
- Redis wrapper in `api/cache.py`.
- `/v1/prospecting` cache with 5-minute TTL.
- `/v1/empresa/{cnpj}` cache with 1-hour TTL.
- keyset cursor input fields in `ProspectingFilters`.
- streaming CSV export in `api/routers/export.py`.
- estimated table counts in `/v1/status` using `pg_class.reltuples`.
- several partial indexes for active establishments in `db/migrations/009_prospecting_search_indexes.sql`.
- query monitor/concurrency/memory middleware files.

Main risks:

- Some query shapes may still scan too much before `LIMIT`.
- Complex filters involving `empresas`, `simples`, `bairro`, `capital_social`, `natureza_juridica` and date ranges can change plans drastically.
- `/v1/export/csv` streams long-running DB reads through the HTTP request lifecycle.
- Pool size is fixed in code (`min_size=5`, `max_size=20`, `command_timeout=60`).
- Cache keys exist, but no explicit namespace version, stampede protection, hit/miss metrics, or cache policy matrix.

---

## Performance Principles

- Measure before indexing.
- Prefer keyset pagination over offset pagination.
- Keep expensive exports outside the request/response path.
- Cache stable RF data aggressively, but use versioned cache keys.
- Use materialized views only for repeated aggregations or denormalized read models proven by query plans.
- Keep API responses bounded by default.
- Make every optimization testable and reversible.

---

## Phase 0 - Baseline And Safety

### Tasks

- [ ] Add a benchmark dataset note to docs: current row counts, Postgres version, hardware/container limits, API worker count.
- [ ] Enable or confirm `pg_stat_statements` availability.
- [ ] Add a local performance runbook under `docs/superpowers/runbooks/api-performance.md`.
- [ ] Create a representative query catalog for the API:
  - CNPJ detail lookup.
  - prospecting by UF.
  - prospecting by UF + CNAE.
  - prospecting by municipio.
  - prospecting by bairro.
  - prospecting by data range.
  - prospecting by capital range.
  - prospecting by porte/excluir MEI.
  - prospecting by Simples.
  - prospecting with combined filters.
  - export query equivalent without limit.
- [ ] Capture current latency for each query shape.
- [ ] Store generated plans outside hot code paths, e.g. `docs/superpowers/perf/YYYY-MM-DD/*.json`.

### Suggested helper

Add a script later:

```text
scripts/explain_api_queries.py
```

Responsibilities:

- build queries through `api/services/query_builder.py`;
- run `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`;
- save JSON plans;
- print summary: total time, rows, shared read/hit blocks, sequential scans.

### Acceptance

- We have baseline timings before any performance migration.
- Slow paths are ranked by actual cost.
- The team can compare before/after plans for every index change.

---

## Phase 1 - Index And Query Plan Hardening

### Tasks

- [ ] Review `EXPLAIN ANALYZE` plans from Phase 0.
- [ ] Add one migration for measured API indexes, e.g. `db/migrations/014_api_performance_indexes.sql`.
- [ ] Use `CREATE INDEX CONCURRENTLY IF NOT EXISTS` for large RF tables.
- [ ] Avoid speculative indexes that duplicate existing ones.
- [ ] Add plan comments in the migration explaining which endpoint/filter each index supports.
- [ ] Run `ANALYZE` after bulk index creation.

### Candidate indexes to validate, not blindly add

Detail lookup is already backed by `PRIMARY KEY (cnpj_basico, cnpj_ordem, cnpj_dv)` on `estabelecimentos` and `PRIMARY KEY (cnpj_basico)` on `empresas`.

Potential filters that may need better compound indexes:

```sql
-- active companies filtered by UF + cursor, when no CNAE filter exists
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_active_uf_cursor
    ON estabelecimentos (uf, cnpj_basico, cnpj_ordem)
    WHERE situacao_cadastral = 2;

-- active companies filtered by UF + municipio + cursor
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_active_uf_municipio_cursor
    ON estabelecimentos (uf, municipio, cnpj_basico, cnpj_ordem)
    WHERE situacao_cadastral = 2;

-- active companies filtered by matriz + UF + cursor
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_active_uf_matriz_cursor
    ON estabelecimentos (uf, matriz_filial, cnpj_basico, cnpj_ordem)
    WHERE situacao_cadastral = 2;

-- company filters that often combine with cursor hydration
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_empresas_porte_cursor
    ON empresas (porte, cnpj_basico);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_empresas_natureza_cursor
    ON empresas (natureza_juridica, cnpj_basico);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_empresas_capital_cursor
    ON empresas (capital_social, cnpj_basico);
```

Important: these are candidates. Add only after plans prove they reduce execution time or buffers.

### Query builder improvements

- [ ] Keep the current `candidate_est AS MATERIALIZED` pattern for establishment-only filters.
- [ ] Add specialized query paths for common filter groups when `EXPLAIN` shows bad plans:
  - establishment-only filters;
  - company-only filters;
  - Simples filters;
  - mixed filters.
- [ ] Avoid joining `empresas`, `cnaes`, `municipios`, `simples` before selecting a bounded candidate set when possible.
- [ ] Add tests that assert important SQL shape choices.

### Acceptance

- Top slow prospecting queries have before/after `EXPLAIN ANALYZE`.
- No new index is added without a measured query it supports.
- Public API behavior remains unchanged.

---

## Phase 2 - Redis Cache Policy

### Current cache

- `api/cache.py` supports `get`, `set`, key hashing and fallback when Redis is unavailable.
- `prospecting` TTL: 300 seconds.
- `empresa detail` TTL: 3600 seconds.

### Tasks

- [ ] Add cache namespace/version setting:

```text
API_CACHE_NAMESPACE=cnpj:v1
RF_DATA_VERSION=2026-05
```

- [ ] Include `RF_DATA_VERSION` in every cache key so a new RF import can invalidate all old results without scanning Redis.
- [ ] Add `cache_get_many`/`cache_set_many` only if detail batching is introduced.
- [ ] Add cache hit/miss structured logs or counters.
- [ ] Add TTL matrix by endpoint.
- [ ] Add negative cache for 404 CNPJ detail lookups with short TTL.
- [ ] Add stampede protection for expensive keys:
  - Redis lock per key;
  - short wait/retry for concurrent requests;
  - stale-while-revalidate later if needed.
- [ ] Compress large cached values only if payload size becomes a Redis memory issue.

### Cache policy matrix

| Endpoint | Key | TTL | Notes |
|---|---:|---:|---|
| `/v1/status` | static status key | 60s | estimated counts change slowly |
| `/v1/empresa/{cnpj}` | normalized CNPJ | 1h-24h | RF data changes monthly |
| `/v1/empresa/{cnpj}` 404 | normalized CNPJ | 5m | avoid repeated misses |
| `/v1/prospecting` first page | normalized filters | 5m-30m | cache small/medium pages |
| `/v1/prospecting` deep cursor pages | normalized filters + cursor | 1m-5m | lower reuse probability |
| `/v1/cnaes`, `/v1/bairros` | filter prefix | 1h-24h | small reference lookups |
| paid enrichment detail | CNPJ + account-safe entitlements | short TTL | never bypass entitlement |

### Paid cache rule

Paid data must never be cached only by CNPJ if account entitlements or suppression state affect response shape.

Safe key components:

- endpoint;
- account id or entitlement hash when needed;
- CNPJ;
- paid feature key;
- RF data version;
- enrichment data version if introduced.

### Acceptance

- Cache can be invalidated by changing one version string.
- Redis outage keeps API functional.
- Tests cover cache hit, miss, set failure, namespace version and negative cache.

---

## Phase 3 - Cursor Pagination Standardization

### Current state

`ProspectingFilters` has:

- `cursor_cnpj_basico`
- `cursor_cnpj_ordem`
- `limit`

The `/v1/prospecting` endpoint returns a raw list, so the client must infer the next cursor from the last row.

### Target response

Add a paginated response model for a new versioned endpoint or optional response mode:

```json
{
  "items": [],
  "next_cursor": {
    "cnpj_basico": "12345678",
    "cnpj_ordem": "0001"
  },
  "has_more": true,
  "limit": 100
}
```

### Tasks

- [ ] Keep old `/v1/prospecting` list response for backward compatibility.
- [ ] Add `/v1/prospecting/page` or `response_mode=page`.
- [ ] Fetch `limit + 1` rows to compute `has_more`.
- [ ] Return `next_cursor` only when more rows exist.
- [ ] Add cursor validation:
  - both cursor fields required together;
  - numeric length checks;
  - cursor ignored only when CNPJ exact lookup is used.
- [ ] Add tests for:
  - first page;
  - next page;
  - no more results;
  - invalid partial cursor;
  - cache key includes cursor.

### Cursor rule

Use the same ordering everywhere:

```sql
ORDER BY est.cnpj_basico, est.cnpj_ordem
WHERE (est.cnpj_basico, est.cnpj_ordem) > ($cursor_basico, $cursor_ordem)
```

For endpoints that need branch-level uniqueness, extend to:

```sql
ORDER BY est.cnpj_basico, est.cnpj_ordem, est.cnpj_dv
WHERE (est.cnpj_basico, est.cnpj_ordem, est.cnpj_dv) > (...)
```

### Acceptance

- No endpoint uses `OFFSET` for large result sets.
- Clients can page deterministically.
- Export no longer depends on visible pagination.

---

## Phase 4 - Materialized Views And Summary Tables

### What should use materialized views

Good candidates:

- status/facet counts;
- available UFs/municipios/bairros/CNAEs;
- counts by UF/CNAE/porte/situacao;
- expensive repeated aggregations for dashboards;
- normalized bairro lookup/counts.

Risky candidates:

- full 70M-row denormalized search view without evidence that joins are the bottleneck.

### Proposed materialized views

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS api_mv_status_counts AS
SELECT
    (SELECT reltuples::bigint FROM pg_class WHERE relname = 'empresas') AS total_empresas,
    (SELECT reltuples::bigint FROM pg_class WHERE relname = 'estabelecimentos') AS total_estabelecimentos,
    now() AS refreshed_at;

CREATE MATERIALIZED VIEW IF NOT EXISTS api_mv_prospecting_facets AS
SELECT
    est.uf,
    est.cnae_principal,
    e.porte,
    est.situacao_cadastral,
    count(*)::bigint AS total
FROM estabelecimentos est
JOIN empresas e ON e.cnpj_basico = est.cnpj_basico
GROUP BY est.uf, est.cnae_principal, e.porte, est.situacao_cadastral;
```

Use `CONCURRENTLY` refresh only when the materialized view has a unique index.

Alternative for very large facets:

- build summary tables during ETL;
- swap table names atomically;
- avoid long refresh locks.

### Tasks

- [ ] Identify repeated aggregation endpoints.
- [ ] Add migration for materialized views or summary tables.
- [ ] Add unique indexes required for concurrent refresh.
- [ ] Add refresh command:

```bash
python manage.py refresh-api-views
```

or use a small `scripts/refresh_api_views.sql` run after ETL.

- [ ] Update `/v1/status` and reference endpoints to use summaries where useful.
- [ ] Keep fallback to current direct queries if view is missing in development.

### Acceptance

- Repeated aggregation endpoints avoid scanning RF base tables.
- Refresh process is documented and safe after monthly RF imports.
- API can report `refreshed_at` for view-backed data.

---

## Phase 5 - Async Export Jobs

### Current state

`/v1/export/csv` streams rows directly from the database through the HTTP response.

This is memory-safe, but operationally fragile:

- one request can hold a DB connection for a long time;
- if DB errors after headers are sent, client gets truncated CSV;
- retrying restarts from zero;
- no durable checkpoint;
- hard to rate-limit per account.

### Target flow

```text
POST /v1/export/jobs
  -> creates export job
  -> returns job_id

GET /v1/export/jobs/{job_id}
  -> status, progress, row_count, error

GET /v1/export/jobs/{job_id}/download
  -> returns file when complete
```

### Database table

```sql
CREATE TABLE app_private.export_jobs (
    id UUID PRIMARY KEY,
    account_id TEXT,
    filters_hash TEXT NOT NULL,
    filters_json JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'pending','running','done','failed','canceled','expired'
    )),
    output_format TEXT NOT NULL CHECK (output_format IN ('csv')),
    output_path TEXT,
    row_count BIGINT NOT NULL DEFAULT 0,
    bytes_written BIGINT NOT NULL DEFAULT 0,
    cursor_cnpj_basico CHAR(8),
    cursor_cnpj_ordem CHAR(4),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ
);

CREATE INDEX idx_export_jobs_status_created
    ON app_private.export_jobs (status, created_at);
```

### Worker behavior

- Claims pending export jobs with `FOR UPDATE SKIP LOCKED`.
- Writes CSV in chunks.
- Updates cursor checkpoint after every chunk.
- Can resume a failed/stale job from the last cursor.
- Stores output in local volume first; object storage later if needed.
- Rechecks paid entitlement before final download for paid exports.

### API behavior

- Keep `/v1/export/csv` for small/dev exports only.
- Add guardrails:
  - direct stream maximum row estimate;
  - otherwise return `202 Accepted` pointing to async job endpoint.
- Add per-account export quota.

### Acceptance

- Long export does not hold an HTTP connection.
- Export can resume after worker crash.
- Client can poll progress.
- Partial/truncated files are not served as complete.

---

## Phase 6 - Postgres Pooling And Connection Management

### Current state

`api/database.py` uses fixed values:

```python
min_size=5
max_size=20
command_timeout=60
statement_cache_size=0
```

### Tasks

- [ ] Move pool settings to environment:

```text
API_DB_POOL_MIN_SIZE=5
API_DB_POOL_MAX_SIZE=20
API_DB_COMMAND_TIMEOUT=60
API_DB_STATEMENT_CACHE_SIZE=0
API_DB_MAX_INACTIVE_CONNECTION_LIFETIME=300
```

- [ ] Add connection init settings:
  - `application_name='cnpj-api'`;
  - safe `statement_timeout` for API reads;
  - optional `idle_in_transaction_session_timeout`.
- [ ] Add pool metrics:
  - acquired connections;
  - idle connections;
  - max size;
  - wait time to acquire connection.
- [ ] Add a request timeout policy by route class:
  - detail: short;
  - prospecting: medium;
  - direct export: limited;
  - async export worker: longer.
- [ ] Evaluate PgBouncer transaction pooling if API/container count grows.

### PgBouncer rule

If using PgBouncer transaction pooling:

- keep `statement_cache_size=0`;
- avoid session-level state in API queries;
- set pool sizes based on total app replicas, not one container.

### Sizing starting point

For one API container:

```text
max_size=20
uvicorn_workers=1-2
```

For multiple containers:

```text
total_api_connections = replicas * API_DB_POOL_MAX_SIZE
```

Keep total API connections comfortably below Postgres `max_connections`, reserving capacity for:

- ETL;
- enrichment workers;
- export workers;
- admin sessions;
- autovacuum.

### Acceptance

- Pool settings are configurable without code change.
- API does not exhaust Postgres connections when scaled.
- Slow query timeout prevents indefinite request hangs.

---

## Phase 7 - Observability And Regression Budgets

### Metrics

Add or expose:

- request latency by route;
- DB query count per request;
- slow query log events;
- cache hit/miss by prefix;
- Redis failures;
- pool acquire wait time;
- export job duration/rows/bytes;
- materialized view refresh time.

### Performance budgets

Initial targets for local/prod-like hardware should be measured and then set. Example structure:

| Path | Target p95 | Notes |
|---|---:|---|
| `/v1/health` | < 50ms | no DB |
| `/v1/status` | < 100ms | view/cache backed |
| `/v1/empresa/{cnpj}` cached | < 50ms | Redis hit |
| `/v1/empresa/{cnpj}` DB | < 250ms | includes socios/simples |
| `/v1/prospecting` common filters | < 500ms | first page |
| `/v1/prospecting` complex filters | < 1500ms | first page |
| async export creation | < 200ms | job creation only |

### Tests

- Unit tests for cache keys and TTL policy.
- Unit tests for paginated response model.
- Query-builder SQL shape tests.
- Integration smoke test for materialized view availability.
- Export job state-machine tests.
- Pool config tests.

### Acceptance

- Performance regressions are visible before production rollout.
- Tests cover behavior, not just implementation details.

---

## Implementation Order

1. **Baseline first**
   - Add query catalog and `EXPLAIN ANALYZE` runbook/script.
   - Capture plans for current queries.

2. **Pool config**
   - Move hardcoded pool values to settings.
   - Add application name and timeouts.

3. **Cache hardening**
   - Add namespace/version.
   - Add cache metrics/logs.
   - Add negative cache for CNPJ detail.

4. **Pagination**
   - Add `/v1/prospecting/page`.
   - Keep existing list endpoint stable.

5. **Measured indexes**
   - Add `014_api_performance_indexes.sql` only after baseline.
   - Re-run plans after each index group.

6. **Materialized views**
   - Start with status/facets only.
   - Avoid massive denormalized views until measured.

7. **Async export jobs**
   - Add DB table.
   - Add worker and job API.
   - Keep direct streaming only for small/dev usage.

8. **PgBouncer evaluation**
   - Add only when API replicas/connection count justify it.

---

## Rollout Strategy

### Local

- Run tests.
- Run representative `EXPLAIN ANALYZE`.
- Verify cache behavior with Redis up/down.
- Verify direct endpoint compatibility.

### Staging/prod-like

- Apply index migrations one group at a time.
- Run `ANALYZE`.
- Compare query plans.
- Enable new paginated endpoint.
- Enable cache namespace versioning.
- Start async export worker with low concurrency.

### Production

- Keep old endpoints available.
- Roll out new cache namespace.
- Monitor cache hit rate and slow queries.
- Route heavy exports to async jobs.
- Scale API only after pool sizing is validated.

---

## Done Criteria

- Baseline plans exist for main API query shapes.
- Pool settings are environment-driven.
- Redis cache has versioning and observability.
- Cursor pagination returns explicit `next_cursor`.
- Repeated aggregation endpoints use summary/materialized data.
- Heavy exports run through durable jobs with checkpoints.
- Slow query rate decreases without increasing false positives or stale data.
- All changed API tests pass.

