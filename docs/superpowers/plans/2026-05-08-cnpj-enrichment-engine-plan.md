# CNPJ Enrichment Engine - Implementation Plan

**Date:** 2026-05-08  
**Status:** Proposed  
**Primary spec:** `docs/superpowers/specs/2026-05-08-cnpj-enrichment-engine.md`

---

## Goal

Add a continuous enrichment layer on top of the existing RF CNPJ database. The layer discovers official domains, crawls only relevant public pages, extracts business contacts, scores confidence, stores evidence, and exposes enriched contacts through the API.

Non-goal: replace the current ETL or build anti-bot bypass tooling.

Architecture rule: the crawler/enrichment engine must be a standalone REST service inside the monorepo for now. It should have its own package, dependencies, OpenAPI contract, tests and Dockerfile so it can be moved to a separate repository later with minimal churn.

Quality rule: crawler/enrichment code must target 100% automated test coverage, especially scheduling, URL selection, extraction, normalization, scoring, entitlement-safe response shaping and error handling.

---

## Proposed File Structure

```text
enrichment/
  Dockerfile
  requirements.txt
  pyproject.toml
  config.py
  database.py
  main.py
  server.py
  scheduler.py
  tasks.py
  api/
    __init__.py
    routes.py
    schemas.py
    auth.py
  discovery/
    __init__.py
    domain_candidates.py
    dns_probe.py
    website_probe.py
  crawler/
    __init__.py
    settings.py
    spiders/
      company_site.py
    pipelines.py
    request_loader.py
  extraction/
    __init__.py
    emails.py
    phones.py
    social.py
    structured_data.py
    html.py
  resolver/
    __init__.py
    domain_score.py
    contact_score.py
    publisher.py
  observability/
    __init__.py
    metrics.py
    logging.py
  tests/
    test_domain_candidates.py
    test_extract_emails.py
    test_extract_phones.py
    test_domain_score.py
    test_contact_score.py

db/migrations/
  010_enrichment.sql

api/models/
  enrichment.py

api/services/
  enrichment_client.py
```

---

## Phase 0 - Product Rules

- [ ] Define crawler user-agent and public crawler information URL.
- [ ] Define data retention period for raw HTML/page excerpts.
- [ ] Define suppression/removal workflow.
- [ ] Define confidence thresholds for API visibility.
- [ ] Define first target segment, e.g. one UF + active companies + missing email/phone.
- [ ] Define public vs paid route boundary.
- [ ] Define Stripe feature keys: `crawler_contacts`, `crawler_exports`, `bulk_enrichment`.
- [ ] Define crawler/enrichment REST API contract and OpenAPI ownership.
- [ ] Define package-level 100% test coverage requirement for `enrichment/`.

Acceptance:

- The team can explain what data is collected, why it is collected, where it came from, and how to suppress it.
- The team can explain which endpoints are free, which endpoints are paid, and which Stripe entitlement unlocks each paid capability.
- The crawler can be described as a service boundary that can move to another repository later.

---

## Phase 1 - Database Foundation

- [ ] Create `db/migrations/010_enrichment.sql`.
- [ ] Create schema `paid_enrichment` for crawler-derived data.
- [ ] Create schema `app_private` for Stripe billing and entitlement state.
- [ ] Add tables:
  - `app_private.billing_accounts`
  - `app_private.billing_subscriptions`
  - `app_private.billing_entitlements`
  - `paid_enrichment.enrichment_targets`
  - `paid_enrichment.company_domains`
  - `paid_enrichment.crawl_hosts`
  - `paid_enrichment.crawl_requests`
  - `paid_enrichment.crawl_pages`
  - `paid_enrichment.enrichment_evidence`
  - `paid_enrichment.raw_contact_candidates`
  - `paid_enrichment.enriched_contacts`
  - `paid_enrichment.enrichment_access_audit`
- [ ] Add indexes for target queue, crawl queue, contacts by CNPJ, contacts by normalized value.
- [ ] Add database roles/permissions:
  - public API role cannot read `paid_enrichment`
  - paid API/enrichment service role reads only published paid views
  - enrichment worker role writes crawler tables
  - billing worker role writes `app_private` Stripe state
- [ ] Add migration tests or at least a smoke check against local Postgres.

Acceptance:

- Migration applies cleanly.
- Existing RF tables remain unchanged.
- Query by CNPJ returns active enriched contacts in index-friendly shape through paid schema/views.
- A public database role cannot select crawler-derived contacts.

---

## Phase 1.5 - Paywall And Entitlements

- [ ] Add Stripe webhook receiver for subscription lifecycle events.
- [ ] Store Stripe customer/subscription state in `app_private`.
- [ ] Implement local entitlement lookup by `account_id` and `feature_key`.
- [ ] Implement `require_paid_entitlement(feature_key)` dependency for paid endpoints.
- [ ] Add quota counters for paid export/bulk capabilities.
- [ ] Add paid access audit write path for every read/export.
- [ ] Ensure entitlement is checked before query execution and again before async export delivery.

Acceptance:

- Unauthenticated users receive `401`.
- Authenticated users without entitlement receive `403` or `402`, according to product policy.
- Expired/canceled Stripe subscriptions cannot read paid crawler data.
- No paid payload is authorized from client-provided plan flags.

---

## Phase 2 - Normalize Existing RF Contacts

- [ ] Build email normalizer with `email-validator`.
- [ ] Build phone normalizer with `phonenumbers`, default region `BR`.
- [ ] Normalize existing `estabelecimentos.email`, `telefone1`, `telefone2`, `fax` as a public-safe baseline.
- [ ] Keep RF-only values out of paid crawler contact tables unless copied only as internal comparison signals.
- [ ] Do not rebrand RF-sourced values as paid enrichment.
- [ ] Classify public-provider vs corporate email domains.

Acceptance:

- For a sample CNPJ, API can show RF public contact and paid crawler contact separately.
- Invalid emails/phones are rejected or marked low confidence.
- Corporate email domains are available for domain discovery.
- RF-only values remain available through public RF routes according to current product rules.

---

## Phase 3 - Target Scheduler

- [ ] Implement `enrichment_scheduler`.
- [ ] Select active establishments first: `situacao_cadastral = 2`.
- [ ] Prioritize missing RF email/phone.
- [ ] Prioritize companies matching existing prospecting filters.
- [ ] Use `FOR UPDATE SKIP LOCKED` or equivalent locking for concurrent workers.
- [ ] Add retry state: `pending`, `running`, `retry`, `done`, `blocked`, `error`.

Acceptance:

- Scheduler can enqueue a bounded batch, e.g. 10k CNPJs.
- Re-running scheduler is idempotent.
- Stale/failed targets are retried with backoff, not hot-looped.

---

## Phase 4 - Domain Discovery

- [ ] Extract domain from RF corporate emails.
- [ ] Generate brand slugs from `nome_fantasia` and `razao_social`.
- [ ] Generate candidate domains with `.com.br`, `.com`, `.net.br`.
- [ ] Probe DNS and HTTP/HTTPS with HTTPX.
- [ ] Detect parked pages, directory pages, and obvious non-company domains.
- [ ] Store candidates in `company_domains`.

Acceptance:

- Domain discovery produces candidates without crawling deep pages.
- Public email providers are not treated as official domains.
- Every candidate has a source and confidence.

---

## Phase 5 - Static Crawler MVP

- [ ] Add standalone enrichment REST service under `enrichment/server.py`.
- [ ] Expose internal OpenAPI endpoints for enqueue, status, detail enrichment and evidence lookup.
- [ ] Keep the service decoupled from `api/` and `etl/`; no imports from crawler internals into the public API.
- [ ] Add Scrapy project under `enrichment/crawler`.
- [ ] Implement request loader that reads `crawl_requests` from Postgres.
- [ ] Enable `ROBOTSTXT_OBEY`.
- [ ] Enable AutoThrottle.
- [ ] Set depth, timeout, content-size and redirect limits.
- [ ] Store `crawl_pages` with content hash, title, status and source URL.
- [ ] Queue only same-domain contact/about/home/sitemap URLs.
- [ ] Add unit/integration tests for crawler request selection, robots decisions, URL dedupe, persistence and error handling.
- [ ] Enforce 100% coverage for `enrichment/crawler`.

Acceptance:

- Crawler can process a small domain batch without duplicate URL loops.
- 403/429/robots blocked pages stop domain expansion.
- Same input can resume or safely rerun without duplicate records.
- Public API can interact with the crawler only through the enrichment REST client/contract.
- Crawler coverage report reaches 100%.

---

## Phase 6 - Extraction Pipeline

- [ ] Implement email extraction:
  - `mailto:`
  - visible text regex
  - JSON-LD/Microdata/RDFa via extruct
- [ ] Implement phone extraction:
  - `tel:`
  - visible text
  - JSON-LD telephone
  - WhatsApp URL patterns
- [ ] Implement social URL extraction from anchors.
- [ ] Implement website canonicalization.
- [ ] Store raw candidates before scoring.
- [ ] Mock all network and parser boundaries in tests.
- [ ] Enforce 100% coverage for extraction modules.

Acceptance:

- Unit tests cover Brazilian phone formats, WhatsApp links, invalid placeholders, duplicate emails and social URLs.
- Extractors return normalized values and context.
- No candidate is published without evidence.
- Coverage report for extraction modules reaches 100%.

---

## Phase 7 - Entity Resolution And Scoring

- [ ] Implement domain score.
- [ ] Implement contact score.
- [ ] Add exact CNPJ detection.
- [ ] Add legal/fantasy name fuzzy match with `rapidfuzz`.
- [ ] Add address/CEP/city/UF matching.
- [ ] Downscore directories and weak domains.
- [ ] Publish only contacts above configured threshold.
- [ ] Mark conflicting values instead of overwriting silently.
- [ ] Enforce 100% coverage for scoring and publisher modules.

Acceptance:

- A contact from a verified official domain is published.
- A contact from a directory with weak evidence is held as candidate.
- Same contact found twice updates `last_seen` and confidence, not a duplicate row.
- Coverage report for resolver modules reaches 100%.

---

## Phase 8 - API Integration

- [ ] Add `api/models/enrichment.py`.
- [ ] Add `api/services/enrichment_client.py` that calls the standalone enrichment REST service.
- [ ] Keep public `GET /v1/empresa/{cnpj}` free of crawler contacts by default.
- [ ] Add safe public flag: `enrichment_available`.
- [ ] Add paid route `GET /v1/paid/empresa/{cnpj}/enrichment`.
- [ ] Protect paid routes with `require_paid_entitlement("crawler_contacts")`.
- [ ] Add prospecting filters:
  - `has_website`
  - `has_enriched_email`
  - `has_enriched_phone`
  - `has_whatsapp`
  - `min_contact_confidence`
  - `enrichment_status`
- [ ] Keep RF fields in existing response for backward compatibility.
- [ ] Ensure paid cache keys include account/entitlement context.
- [ ] Insert paid access audit rows for detail, search and export reads.

Acceptance:

- Existing frontend/API consumers do not break.
- New enrichment fields are nullable and cacheable.
- Query builder remains parameterized and index-aware.
- Public endpoints never leak paid crawler fields.
- Paid endpoints fail closed when Stripe entitlement is missing or expired.
- The main API does not import crawler internals.

---

## Phase 9 - Observability

- [ ] Add structured logging with `cnpj`, `domain`, `url`, `task_id`, `decision`.
- [ ] Add metrics counters:
  - targets processed
  - crawl pages fetched
  - HTTP status classes
  - robots blocked
  - contacts extracted
  - contacts published
  - source yield
  - queue lag
- [ ] Add daily SQL reports for coverage and precision sampling.

Acceptance:

- Operator can answer: "How many contacts did we add today, from which source, with what confidence, and at what crawl cost?"

---

## Phase 10 - Playwright Fallback

- [ ] Add separate low-concurrency Playwright worker.
- [ ] Queue only pages where static extraction failed and domain confidence is high.
- [ ] Block images/fonts/media to reduce cost.
- [ ] Hard-limit CPU, memory, timeout and pages per domain.
- [ ] Feed rendered HTML back into the same extraction pipeline.

Acceptance:

- Playwright handles a minority of pages.
- Static crawler performance is not affected.
- JS fallback has clear cost/yield metrics.

---

## Phase 11 - Common Crawl Adapter

- [ ] Add adapter for known candidate domains.
- [ ] Query URL inventories for candidate domain patterns.
- [ ] Retrieve only selected archived pages likely to contain contact data.
- [ ] Mark source as `common_crawl`.
- [ ] Downscore stale archive data unless confirmed live.

Acceptance:

- Adapter can enrich or verify a known domain without touching live site.
- Archive-only contacts are visible only if confidence and recency rules pass.

---

## Phase 12 - Product Hardening

- [ ] Add suppression table and admin workflow.
- [ ] Add contact feedback endpoint.
- [ ] Add export fields for enrichment source/confidence.
- [ ] Put paid exports behind `crawler_exports` entitlement.
- [ ] Generate short-lived account-bound export URLs.
- [ ] Add sampling QA workflow.
- [ ] Add dashboard for coverage by UF/CNAE/porte.
- [ ] Add incremental revisit schedule.
- [ ] Add security regression tests for public vs paid route separation.
- [ ] Add coverage gate for the full `enrichment/` package.
- [ ] Document repo-split checklist for moving `enrichment/` into its own repository later.

Acceptance:

- The engine can run continuously.
- Bad contacts can be suppressed.
- Operators can audit source evidence.
- The product is ready for limited commercial validation.
- Paid data cannot be retrieved without active entitlement.
- `enrichment/` remains independently buildable/testable inside the monorepo.

---

## First Build Slice

The smallest useful implementation is:

1. `010_enrichment.sql`
2. RF contact normalizer
3. Domain discovery from RF email domains
4. Standalone enrichment REST service boundary
5. Static crawl of homepage + contact page
6. Email/phone/WhatsApp extraction
7. Scoring and `paid_enrichment.enriched_contacts`
8. Stripe entitlement check for paid enrichment route
9. API detail enrichment client/paid route

Do not implement search discovery, Playwright or Common Crawl in the first slice. They are scale and coverage tools, not required to prove the model.

---

## Validation Checklist

- [ ] Unit tests for normalizers.
- [ ] Unit tests for extractors.
- [ ] Unit tests for score thresholds.
- [ ] 100% coverage gate for `enrichment/crawler`.
- [ ] 100% coverage gate for extraction and resolver modules that publish crawler-derived contacts.
- [ ] Migration smoke test.
- [ ] Crawler dry run on 20 known domains.
- [ ] Manual precision audit on 100 published contacts.
- [ ] No raw HTML exposed through public API.
- [ ] No crawler-derived contacts exposed through public RF routes.
- [ ] Paid detail/search/export routes require server-side Stripe entitlement.
- [ ] Paid cache keys are account-bound and entitlement-aware.
- [ ] Export jobs re-check entitlement at execution and delivery time.
- [ ] Access audit row is written for each paid read/export.
- [ ] No anti-bot bypass dependencies added.
- [ ] API backward compatibility verified.
- [ ] Main API integration uses `enrichment_client.py`; it does not import crawler internals.
- [ ] `enrichment/` can run tests and service startup independently inside the monorepo.
