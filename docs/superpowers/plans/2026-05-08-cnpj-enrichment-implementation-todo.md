# CNPJ Enrichment Engine - Master Implementation TODO

**Date:** 2026-05-08  
**Status:** In progress - foundation, paywall boundary and pure enrichment modules implemented  
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
- [ ] Keep every crawler-derived contact tied to evidence and confidence.

---

## Phase A - Foundation

- [x] Commit architecture/spec plan to `develop`.
- [x] Add `db/migrations/010_enrichment.sql`.
- [x] Create `paid_enrichment` schema for crawler-derived data.
- [x] Create `app_private` schema for Stripe billing/entitlement state.
- [x] Create role/grant boundary for public API, paid API, enrichment worker and billing worker.
- [x] Add standalone `enrichment/` service scaffold.
- [x] Add independent `enrichment` OpenAPI app.
- [x] Add internal API-key guard for service-to-service calls.
- [x] Add first coverage gate for `enrichment/`.
- [x] Add docker-compose service for local monorepo execution.

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
- [ ] Use RF values as internal scoring signals for crawler findings.

---

## Phase D - Domain Discovery

- [x] Extract candidate domains from RF corporate email domains.
- [x] Generate brand slugs from legal/fantasy names.
- [ ] Probe HTTPS/HTTP/DNS with bounded HTTPX adapters.
- [ ] Detect parked, directory and weak domains.
- [ ] Store `paid_enrichment.company_domains`.
- [x] Unit test all generation/scoring branches.

---

## Phase E - Static Crawler

- [ ] Add Scrapy settings with robots, AutoThrottle, depth and size limits.
- [ ] Add request loader from `paid_enrichment.crawl_requests`.
- [ ] Add URL canonicalization and same-domain filtering.
- [ ] Add sitemap/contact/about/home URL prioritization.
- [ ] Store `paid_enrichment.crawl_pages`.
- [ ] Add resume/idempotency handling.
- [ ] Enforce 100% test coverage for crawler modules.

---

## Phase F - Extraction And Resolution

- [x] Extract emails from `mailto` and visible text.
- [ ] Extract emails from structured data.
- [x] Extract phones and WhatsApp links.
- [x] Extract social URLs linked from verified domains.
- [x] Normalize contacts.
- [ ] Store raw candidates.
- [ ] Implement domain confidence scoring.
- [x] Implement contact confidence scoring.
- [x] Publish only threshold-approved contacts.
- [x] Enforce 100% test coverage for extraction/resolver modules.

---

## Phase G - Product Hardening

- [ ] Add suppression workflow.
- [ ] Add feedback endpoint.
- [ ] Add paid export jobs with entitlement re-check.
- [ ] Add short-lived account-bound export URLs.
- [ ] Add coverage/cost dashboards.
- [ ] Add Common Crawl adapter.
- [ ] Add low-throughput Playwright fallback.
- [ ] Document repository split steps for `enrichment/`.
