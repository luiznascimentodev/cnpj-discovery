# CNPJ Enrichment Engine - Master Implementation TODO

**Date:** 2026-05-08  
**Status:** Pipeline funcional — scheduler com resume, descoberta, crawler, publisher, CLI e worker docker prontos com 100% de cobertura.  
**Spec:** `docs/superpowers/specs/2026-05-08-cnpj-enrichment-engine.md`  
**Plan:** `docs/superpowers/plans/2026-05-08-cnpj-enrichment-engine-plan.md`

---

## Working Rules

- [x] Keep RF/public data and crawler-derived paid data physically separated.
- [x] Keep crawler/enrichment as a standalone REST service inside the monorepo.
- [x] Do not import crawler internals from the public API.
- [x] Protect paid crawler data with server-side entitlement checks.
- [x] Keep crawler/extraction/resolver modules at 100% automated test coverage.
- [x] Do not add anti-bot bypass dependencies or behavior.
- [x] Keep every crawler-derived contact tied to evidence and confidence.

---

## Phase A - Foundation

- [x] Commit architecture/spec plan to `develop`.
- [x] Add `db/migrations/010_enrichment.sql`.
- [x] Add `db/migrations/011_enrichment_seed_cursor.sql` (resume cursor).
- [x] Create `paid_enrichment` schema for crawler-derived data.
- [x] Create `app_private` schema for Stripe billing/entitlement state.
- [x] Create role/grant boundary for public API, paid API, enrichment worker and billing worker.
- [x] Add standalone `enrichment/` service scaffold.
- [x] Add independent `enrichment` OpenAPI app.
- [x] Add internal API-key guard for service-to-service calls.
- [x] Add coverage gate for `enrichment/` (100%).
- [x] Add docker-compose service for local monorepo execution.
- [x] Add docker-compose `enrichment-worker` profile (loop autônomo).

---

## Phase B - Paywall And API Boundary

- [ ] Add Stripe webhook receiver.
- [ ] Persist subscription lifecycle events.
- [x] Implement local entitlement lookup.
- [x] Add initial server-side entitlement guard to public API paid routes.
- [x] Add `api/services/enrichment_client.py`.
- [x] Add `GET /v1/paid/empresa/{cnpj}/enrichment`.
- [ ] Add safe public `enrichment_available` flag without paid payload.
- [ ] Add paid read/export audit writes.
- [ ] Add account-bound paid cache keys.
- [ ] Add security regression tests for public vs paid routes.

---

## Phase C - Public RF Baseline

- [x] Implement RF email normalizer.
- [x] Implement RF phone normalizer.
- [x] Classify public-provider and corporate email domains.
- [x] Keep RF-only values public; do not copy them as paid contacts.
- [x] Use RF values as internal scoring signals for crawler findings (via `_baseline_blacklist`).

---

## Phase D - Domain Discovery

- [x] Extract candidate domains from RF corporate email domains.
- [x] Generate brand slugs from legal/fantasy names.
- [x] Probe HTTPS/HTTP/DNS com bounded HTTPX (`discovery/website_probe.py`).
- [x] Detect parked, unreachable e weak domains com confidence ajustada.
- [x] Persistir `paid_enrichment.company_domains` via discovery pipeline.
- [x] Pipeline `discovery/pipeline.py` enfileira URLs prioritárias em `crawl_requests`.
- [x] Unit test all generation/scoring/probe branches.

---

## Phase E - Static Crawler

- [x] Add fila persistente em `paid_enrichment.crawl_requests` com `claim_crawl_requests` (FOR UPDATE SKIP LOCKED + lease).
- [x] Add `crawler/runner.py` com httpx async, robots-aware, hashing, idempotência.
- [x] Add robots fetch + cache local + persistência em `crawl_hosts` (`crawler/robots.py`).
- [x] Add URL canonicalization (via `discovery/website_probe`) e mesma-domínio (gerada pelo discovery pipeline).
- [x] Add resume/idempotency: `crawl_pages` UNIQUE(url, content_hash); leases liberados em `release_stale_requests`.
- [x] Backoff exponencial: 60s · 2^(attempts-1) cap em 1h.
- [x] Bloqueio de host após N falhas consecutivas (BLOCK_AFTER_FAILURES).
- [x] Enforce 100% test coverage for crawler modules.

---

## Phase F - Extraction And Resolution

- [x] Extract emails from `mailto` and visible text.
- [ ] Extract emails from structured data (extruct/JSON-LD) — fallback futuro.
- [x] Extract phones and WhatsApp links.
- [x] Extract social URLs linked from verified domains.
- [x] Normalize contacts.
- [x] Store raw candidates (`paid_enrichment.raw_contact_candidates`).
- [x] Implement domain confidence scoring (`resolver/domain_verifier.py`).
- [x] Implement contact confidence scoring (`resolution.py`).
- [x] Publish only threshold-approved contacts (`PUBLISH_THRESHOLD = 85`).
- [x] Enforce 100% test coverage for extraction/resolver modules.

---

## Phase G - Operational Loop e CLI

- [x] CLI com sub-comandos `seed-targets`, `discovery-tick`, `crawler-tick`, `release-stale`, `worker`.
- [x] Scheduler com cursor de seed persistido (`enrichment_seed_cursor`).
- [x] Worker daemon roda seed → discovery → crawler → release-stale em loop.
- [x] Docker compose com profile `worker` para subir o daemon.

---

## Phase H - Product Hardening (próximos passos)

- [ ] Add suppression workflow.
- [ ] Add feedback endpoint.
- [ ] Add paid export jobs with entitlement re-check.
- [ ] Add short-lived account-bound export URLs.
- [ ] Add coverage/cost dashboards.
- [ ] Add Common Crawl adapter.
- [ ] Add low-throughput Playwright fallback.
- [ ] Document repository split steps for `enrichment/`.

---

## Resume — como funciona, em uma frase por camada

1. **Cursor de seed** (`paid_enrichment.enrichment_seed_cursor`): a cada `seed-targets`, lê de onde parou na varredura de `estabelecimentos` e segue. Nunca volta para o primeiro CNPJ.
2. **Fila persistente** (`enrichment_targets` + `crawl_requests`): `claim_*` usa `FOR UPDATE SKIP LOCKED`. Workers concorrentes não pegam o mesmo registro; itens `done`/`error`/`blocked` nunca são reclamados.
3. **Lease**: `locked_at` (targets) e `updated_at` quando `running` (crawl_requests). `release-stale` libera leases antigos para recuperação após crash.
4. **Idempotência de página**: `crawl_pages` UNIQUE(url, content_hash). Refetch do mesmo conteúdo só atualiza `fetched_at`.

Comando para iniciar o worker:

```bash
docker compose --profile worker up -d enrichment-worker
```

Ou manualmente, etapa a etapa, dentro do container do `enrichment`:

```bash
python cli.py seed-targets --batch-size 1000
python cli.py discovery-tick --batch-size 20
python cli.py crawler-tick --batch-size 20
python cli.py release-stale --lease-seconds 600
```
