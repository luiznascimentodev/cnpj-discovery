# CNPJ Enrichment Engine - Technical Product Spec

**Date:** 2026-05-08  
**Status:** Proposed  
**Scope:** Enrich the existing Receita Federal CNPJ database already loaded by this project. This is not a replacement for the RF ETL.

---

## Hard Position

The enrichment product must be fast, cheap, repeatable, observable, and defensible.

That means:

- Use the current RF tables as the seed and identity anchor.
- Do not pay external enrichment APIs.
- Prefer public company websites, sitemaps, structured metadata, archived web data, and deterministic signals.
- Keep evidence and confidence scores for every enriched value.
- Do not build anti-bot evasion, CAPTCHA bypass, fake identities, residential proxy rotation to bypass blocks, login scraping, or "undetected" browser behavior. Those tactics make the product fragile, expensive to operate, and risky to sell.

The crawler should stay "off the radar" in the sustainable sense: small per-host budgets, robots-aware crawling, cache-first strategy, low error rate, clear timeouts, and no aggressive repeated access.

---

## Improved Self-Prompt

> Design a production-grade CNPJ enrichment engine for an existing PostgreSQL database that already contains Receita Federal public CNPJ data. The engine must enrich each company with additional public business contact data such as official website, additional emails, telephones, WhatsApp links, social profile URLs, and source evidence. It must avoid paid third-party enrichment APIs and be suitable to become a standalone product.
>
> The design must cover source discovery, domain verification, crawling, extraction, normalization, entity resolution, confidence scoring, database schema, API changes, worker architecture, observability, compliance posture, crawl politeness, scaling strategy, and an implementation roadmap. It must explicitly avoid anti-bot bypass techniques and instead use stable, lawful, cache-first and robots-aware crawling practices. It should use known open-source tools where useful, including Scrapy, HTTPX, Playwright only as fallback, Common Crawl, sitemaps, extruct, Trafilatura, selectolax, phonenumbers, email-validator, PostgreSQL, Redis, and Celery or an equivalent worker queue.

## Answer To The Prompt

Build an enrichment engine as a separate service family around the current database, not inside the existing RF ETL. The current tables provide identity, address, CNAE, situation, RF email, RF phone and socios. The new product layer adds a second truth table for discovered contacts with source evidence, confidence, first_seen/last_seen, and status.

The winning strategy is not "crawl everything". It is a multi-stage funnel:

1. Normalize what is already in the database.
2. Discover likely official domains from RF email domains, company names, fantasy names, address and existing contacts.
3. Verify domains with evidence before trusting extracted contacts.
4. Crawl only high-value pages per verified domain: home, contact, about, footer links, sitemap-selected pages.
5. Extract contacts with multiple extractors.
6. Score every result and publish only contacts above threshold.
7. Revisit incrementally based on confidence, staleness and customer demand.

The result is a low-cost enrichment graph, not a one-shot scraper.

---

## Enrichment Levels

### L0 - RF Contact Cleanup

Use the current `estabelecimentos` table:

- Normalize RF emails.
- Normalize `ddd1 + telefone1`, `ddd2 + telefone2`, fax.
- Classify fixed/mobile/unknown using `phonenumbers`.
- Detect public email providers (`gmail.com`, `hotmail.com`, `outlook.com`, `uol.com.br`) vs corporate domains.
- Use normalized RF contacts as public baseline and as comparison signals for crawler scoring.

This gives immediate quality lift without crawling, but it does not turn RF contact data into paid crawler data. Existing RF-sourced values remain public according to the current product rules. The paywall applies to crawler-derived contacts and crawler evidence.

### L1 - Domain Discovery From Existing RF Data

High-confidence seeds:

- Corporate email domain from `estabelecimentos.email`.
- Domain candidates from `nome_fantasia` and `razao_social`.
- Domain candidates from common Brazilian patterns:
  - `{brand}.com.br`
  - `{brand}.com`
  - `{brand}.net.br`
  - `{brand}{cidade}.com.br`

Reject or downscore:

- Public email domains.
- Directory/marketplace domains.
- Parked domains.
- Domains with no business identity signal.

### L2 - Official Site Verification

A domain becomes "verified" only after scoring signals:

| Signal | Score |
|---|---:|
| Exact CNPJ appears on site | +60 |
| RF corporate email domain matches site domain | +35 |
| Legal name exact or near-exact match | +30 |
| Fantasy name exact or near-exact match | +25 |
| CEP/address/city/UF match | +20 |
| RF phone appears on page | +20 |
| Schema.org Organization/LocalBusiness metadata matches | +15 |
| Social links appear from same verified website | +10 |
| Domain is a directory/marketplace/listing site | -40 |
| Domain is parked or for sale | -60 |
| Only weak name similarity, no other evidence | cap at 45 |

Recommended thresholds:

- `>= 80`: verified official domain.
- `60-79`: likely official, usable for low-risk website/social signals.
- `40-59`: candidate only, do not publish contacts automatically.
- `< 40`: reject.

### L3 - Cache-First Web Enrichment

Use cache and archival sources before live crawling:

- Existing page snapshots stored by our crawler.
- Common Crawl URL index and WARC/WET content for known candidate domains.
- Sitemaps and sitemap indexes.
- HTTP conditional requests with `ETag` and `Last-Modified`.

Common Crawl is not a full-text search engine for arbitrary CNPJ lookup, but it is useful once we know or suspect a domain: it can provide historical pages and URL inventories without touching the live website.

### L4 - Live Crawl

Live crawling should be narrow:

- Per-domain crawl budget, e.g. 5 to 20 pages depending on domain confidence.
- Prioritize URLs containing `contato`, `contact`, `sobre`, `about`, `empresa`, `institucional`, `atendimento`, `loja`, `unidades`, `privacidade`.
- Parse sitemap URLs first.
- Follow only same registered domain unless the link is a known social platform or WhatsApp URL.
- Use static HTTP first.
- Use Playwright only when the static response has no useful content and the page clearly renders contact data through JavaScript.

### L5 - Feedback Loop

Every customer interaction improves the graph:

- User marks contact as valid/invalid.
- Export/open/click events raise priority for similar companies.
- Bounce reports or unreachable phone statuses reduce confidence.
- Manual corrections become first-class evidence with operator and timestamp.

---

## Data To Enrich

Primary fields:

- `website`
- `domain`
- `emails`
- `phones`
- `whatsapp`
- `social_profiles`
- `contact_page_url`
- `evidence_url`
- `confidence`
- `source`
- `first_seen`
- `last_seen`

Do not mix all contact types into the RF tables. RF data is a source. Enrichment data is another source with provenance.

---

## Paid Data Boundary And Stripe Paywall

Crawler-derived data is a paid product surface. It must be physically and logically separated from the public RF data.

Rules:

- RF/public data stays in the existing public tables and public API responses.
- Crawler-derived data goes into a dedicated `paid_enrichment` PostgreSQL schema.
- RF-sourced values may be used to validate and score crawler findings, but RF-only values should not be rebranded as paid enrichment.
- Stripe/billing state goes into a dedicated private schema, e.g. `app_private`.
- The public API role must not have direct `SELECT` permission on `paid_enrichment`.
- The paid API role can read only approved views/functions, not raw crawler tables by default.
- The enrichment worker role can write crawler results but should not be reused by the public API.
- Public endpoints must never accidentally include crawler contacts through shared response models.
- Paid endpoints must enforce server-side entitlement checks. Do not rely on frontend hiding.
- Cache keys for paid payloads must include `account_id`, `plan_code` or entitlement version, and the requested CNPJ/filter. Never share cache entries between public and paid responses.
- Raw HTML, raw crawl pages and low-confidence candidates are internal data. They are not exposed to subscribers.
- Every paid read/export must be auditable with account, route, filter, record count, timestamp and request id.

Recommended API boundary:

- Public RF data: `/v1/empresa/{cnpj}`, `/v1/prospecting`, `/v1/export/csv`
- Paid crawler data: `/v1/paid/empresa/{cnpj}/enrichment`, `/v1/paid/prospecting`, `/v1/paid/export`
- Admin/internal crawler data: `/v1/internal/enrichment/*`

`GET /v1/empresa/{cnpj}` may include an `enrichment_available: true` flag for public users, but must not include paid contacts unless the request passes entitlement middleware.

Stripe integration:

- Stripe Checkout/Customer Portal owns payment collection.
- Stripe webhooks update local subscription state.
- The API authorizes from local subscription/entitlement tables, not by trusting client-provided plan flags.
- Subscription states should map to access explicitly: `active` and valid trial can read paid data; `past_due`, `canceled`, `incomplete`, `unpaid` cannot, unless the business deliberately grants a grace period.
- Entitlements should be feature-based, e.g. `crawler_contacts`, `crawler_exports`, `bulk_enrichment`, with quotas by plan.

Security controls:

- Central `require_paid_entitlement(feature_key)` dependency/middleware.
- Route-level dependency on every paid endpoint.
- Separate Pydantic response models for public RF data and paid enrichment data.
- Separate query services: `public_query_builder` must not import paid enrichment joins.
- Integration tests proving unauthenticated/unsubscribed users receive 401/403/402 and never see paid fields.
- Export jobs must re-check entitlement at job execution time, not only when queued.
- Signed URLs for exports should be short-lived and account-bound.
- Logs must not print full paid contact payloads.

---

## Source Strategy

### Allowed First-Party And Public Sources

- Current RF database.
- Official company websites.
- Public sitemaps.
- Public metadata embedded in HTML: JSON-LD, Microdata, RDFa, Open Graph, Dublin Core.
- Public pages archived by Common Crawl.
- Public social/profile links found on the verified official website.

### Optional Discovery Sources

Self-hosted SearXNG can be used as a discovery adapter, not as a source of truth. It should only produce candidate URLs, and every URL must go through entity resolution before any contact is trusted.

Direct scraping of Google/Bing/LinkedIn/Instagram search or logged-in experiences should not be part of the product core. It creates blocking, terms, and reliability risk.

### Explicit Non-Sources

- Leaked datasets.
- Login-only pages.
- CAPTCHA-protected content.
- Personal social profiles unless they are explicitly published as business contact on the official company website.
- Brokered data acquired without clear rights.

---

## Architecture

```
PostgreSQL RF tables (public data)
        |
        v
enrichment_scheduler  ->  paid_enrichment.enrichment_targets
        |
        v
domain_discovery_worker  ->  paid_enrichment.company_domains
        |
        v
crawl_request_queue  ->  crawler_service  ->  paid_enrichment.crawl_pages
        |
        v
extractor_pipeline  ->  paid_enrichment.raw_contact_candidates
        |
        v
entity_resolver  ->  paid_enrichment.enriched_contacts + paid_enrichment.enrichment_evidence
        |
        v
FastAPI paid endpoints + Stripe entitlement checks
```

### Service Boundary

The crawler/enrichment engine must be designed as an independent REST service from day one, even while it lives in this monorepo.

Rules:

- Keep it in a separate `enrichment/` package with its own settings, dependencies, tests, Dockerfile and OpenAPI surface.
- The existing public API must call the enrichment service through an HTTP client or a narrow adapter, not by importing crawler internals.
- The enrichment service owns crawler scheduling, crawl requests, extraction, scoring, evidence and paid contact publication.
- The existing API owns authentication, public RF endpoints and user-facing routing, but it must not know crawler implementation details.
- Shared contracts should be explicit JSON schemas/Pydantic models, not shared database joins scattered across services.
- The service should be separable into another repository later with minimal changes: copy `enrichment/`, its migrations, tests, Dockerfile and client contract.
- The crawler package must target 100% automated test coverage. Any untestable network behavior must be isolated behind adapters/mocks.

### Services

`enrichment_scheduler`

- Selects target CNPJs from the current database.
- Prioritizes active companies, missing contacts, stale contacts and ICP filters.
- Writes work into `enrichment_targets`.

`domain_discovery_worker`

- Reads RF email domains and generated brand domains.
- Performs DNS/HTTP checks.
- Stores domain candidates with source and confidence.

`crawler_service`

- Runs Scrapy as a long-lived service for static pages.
- Reads from `crawl_requests`.
- Enforces robots, timeouts, size limits, max depth, per-domain budgets and AutoThrottle.
- Stores page metadata and content hash.

`playwright_render_worker`

- Separate low-throughput fallback.
- Only processes pages that static crawl could not extract.
- Has strict CPU/memory/page-count limits.

`extractor_pipeline`

- Parses HTML with selectolax for fast DOM extraction.
- Uses extruct for JSON-LD/Microdata/RDFa/Open Graph.
- Uses Trafilatura for cleaner metadata/text extraction when needed.
- Extracts `mailto:`, `tel:`, `wa.me`, `api.whatsapp.com/send?phone=`, visible emails, visible phones and social URLs.

`entity_resolver`

- Links candidate contacts to a CNPJ.
- Computes domain confidence and contact confidence.
- Deduplicates normalized values.
- Publishes accepted contacts.

`enrichment_api`

- Runs as the crawler/enrichment REST API.
- Exposes paid-data-safe endpoints consumed by the main FastAPI application.
- Owns its OpenAPI contract.
- Adds filters for "has website", "has enriched email", "has WhatsApp", "confidence >= X".
- Does not expose raw crawler pages, raw candidates or internal scoring traces to public clients.

---

## Recommended Tech Stack

### Keep

- PostgreSQL 16 as source of truth.
- Redis as queue/cache substrate.
- FastAPI for API exposure.
- Polars for offline/batch analytics.

### Add

- FastAPI or another ASGI framework for the standalone enrichment REST API.
- Scrapy for crawling, pipelines, dupe filtering, throttling and JOBDIR persistence.
- Celery for CNPJ/domain task orchestration and retry/backoff.
- HTTPX for lightweight async DNS/HTTP validation and small fetches outside Scrapy.
- Playwright Python only as JS fallback.
- selectolax for fast HTML parsing in extraction hot paths.
- extruct for structured metadata.
- Trafilatura for metadata/text fallback and sitemap/feed utilities.
- phonenumbers for phone parsing/validation.
- email-validator for email syntax and optional deliverability checks.
- publicsuffix2 or tldextract for registered-domain comparison.
- rapidfuzz for company-name/domain-name similarity.

### Why Scrapy + Celery

Scrapy should own web crawling because it already solves crawler-specific concerns: concurrency, downloader middleware, robots, item pipelines, duplicate filtering, feed exports, crawl persistence and AutoThrottle.

Celery should own business-level work orchestration: "enrich this CNPJ", "discover this domain", "revisit stale contacts", "retry transient failure with backoff". Avoid starting a Scrapy process per CNPJ; keep Scrapy as a service consuming crawl requests.

The enrichment REST API should own integration boundaries. The main API should ask it for paid enrichment payloads after entitlement validation, instead of importing crawler modules or joining crawler tables directly.

---

## Database Design

Add migration `010_enrichment.sql`.

All crawler-derived tables live under `paid_enrichment`. Billing and entitlement tables live under `app_private`. The existing RF tables remain in the current schema.

```sql
CREATE SCHEMA IF NOT EXISTS paid_enrichment;
CREATE SCHEMA IF NOT EXISTS app_private;

CREATE TABLE app_private.billing_accounts (
    id BIGSERIAL PRIMARY KEY,
    account_id TEXT NOT NULL UNIQUE,
    stripe_customer_id TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE app_private.billing_subscriptions (
    id BIGSERIAL PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES app_private.billing_accounts(account_id),
    stripe_subscription_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    plan_code TEXT NOT NULL,
    current_period_end TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE app_private.billing_entitlements (
    id BIGSERIAL PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES app_private.billing_accounts(account_id),
    feature_key TEXT NOT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT false,
    quota_monthly INT,
    used_this_period INT NOT NULL DEFAULT 0,
    entitlement_version BIGINT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, feature_key)
);

CREATE TABLE paid_enrichment.enrichment_targets (
    id BIGSERIAL PRIMARY KEY,
    cnpj_basico CHAR(8) NOT NULL,
    cnpj_ordem CHAR(4) NOT NULL,
    cnpj_dv CHAR(2) NOT NULL,
    priority SMALLINT NOT NULL DEFAULT 50,
    status TEXT NOT NULL CHECK (status IN ('pending','running','done','retry','blocked','error')),
    reason TEXT NOT NULL,
    attempts INT NOT NULL DEFAULT 0,
    next_run_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_at TIMESTAMPTZ,
    locked_by TEXT,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (cnpj_basico, cnpj_ordem, cnpj_dv, reason)
);

CREATE TABLE paid_enrichment.company_domains (
    id BIGSERIAL PRIMARY KEY,
    cnpj_basico CHAR(8) NOT NULL,
    cnpj_ordem CHAR(4) NOT NULL,
    cnpj_dv CHAR(2) NOT NULL,
    domain TEXT NOT NULL,
    homepage_url TEXT,
    source TEXT NOT NULL,
    confidence SMALLINT NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    status TEXT NOT NULL CHECK (status IN ('candidate','verified','rejected','stale')),
    evidence_id BIGINT,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (cnpj_basico, cnpj_ordem, cnpj_dv, domain)
);

CREATE TABLE paid_enrichment.crawl_hosts (
    domain TEXT PRIMARY KEY,
    robots_status TEXT,
    robots_checked_at TIMESTAMPTZ,
    crawl_delay_seconds NUMERIC(8,2),
    max_pages_per_run INT NOT NULL DEFAULT 10,
    consecutive_failures INT NOT NULL DEFAULT 0,
    blocked_until TIMESTAMPTZ,
    last_fetch_at TIMESTAMPTZ
);

CREATE TABLE paid_enrichment.crawl_requests (
    id BIGSERIAL PRIMARY KEY,
    cnpj_basico CHAR(8) NOT NULL,
    cnpj_ordem CHAR(4) NOT NULL,
    cnpj_dv CHAR(2) NOT NULL,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    source TEXT NOT NULL,
    priority SMALLINT NOT NULL DEFAULT 50,
    status TEXT NOT NULL CHECK (status IN ('pending','running','done','retry','skipped','blocked','error')),
    depth SMALLINT NOT NULL DEFAULT 0,
    attempts INT NOT NULL DEFAULT 0,
    next_run_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    content_hash TEXT,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (cnpj_basico, cnpj_ordem, cnpj_dv, url)
);

CREATE TABLE paid_enrichment.crawl_pages (
    id BIGSERIAL PRIMARY KEY,
    crawl_request_id BIGINT REFERENCES paid_enrichment.crawl_requests(id),
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    http_status INT,
    content_type TEXT,
    content_hash TEXT NOT NULL,
    title TEXT,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    html_excerpt TEXT,
    raw_storage_key TEXT,
    UNIQUE (url, content_hash)
);

CREATE TABLE paid_enrichment.enrichment_evidence (
    id BIGSERIAL PRIMARY KEY,
    cnpj_basico CHAR(8) NOT NULL,
    cnpj_ordem CHAR(4) NOT NULL,
    cnpj_dv CHAR(2) NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT,
    source_domain TEXT,
    crawl_page_id BIGINT REFERENCES paid_enrichment.crawl_pages(id),
    extractor TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    evidence_excerpt TEXT,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE paid_enrichment.raw_contact_candidates (
    id BIGSERIAL PRIMARY KEY,
    evidence_id BIGINT NOT NULL REFERENCES paid_enrichment.enrichment_evidence(id),
    contact_type TEXT NOT NULL CHECK (contact_type IN ('email','phone','whatsapp','website','social')),
    raw_value TEXT NOT NULL,
    normalized_value TEXT,
    label TEXT,
    context TEXT,
    confidence SMALLINT NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE paid_enrichment.enriched_contacts (
    id BIGSERIAL PRIMARY KEY,
    cnpj_basico CHAR(8) NOT NULL,
    cnpj_ordem CHAR(4) NOT NULL,
    cnpj_dv CHAR(2) NOT NULL,
    contact_type TEXT NOT NULL CHECK (contact_type IN ('email','phone','whatsapp','website','social')),
    value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    label TEXT,
    source TEXT NOT NULL,
    confidence SMALLINT NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    status TEXT NOT NULL CHECK (status IN ('active','conflicted','stale','suppressed','rejected')),
    evidence_id BIGINT REFERENCES paid_enrichment.enrichment_evidence(id),
    first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (cnpj_basico, cnpj_ordem, cnpj_dv, contact_type, normalized_value)
);

CREATE TABLE paid_enrichment.enrichment_access_audit (
    id BIGSERIAL PRIMARY KEY,
    account_id TEXT NOT NULL,
    request_id TEXT,
    route TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('read','export','feedback','admin')),
    cnpj_basico CHAR(8),
    cnpj_ordem CHAR(4),
    cnpj_dv CHAR(2),
    filter_hash TEXT,
    record_count INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Indexes:

```sql
CREATE INDEX idx_enrichment_targets_status_next
    ON paid_enrichment.enrichment_targets (status, next_run_at, priority DESC);

CREATE INDEX idx_company_domains_cnpj
    ON paid_enrichment.company_domains (cnpj_basico, cnpj_ordem, cnpj_dv, confidence DESC);

CREATE INDEX idx_enriched_contacts_cnpj_type
    ON paid_enrichment.enriched_contacts (cnpj_basico, cnpj_ordem, cnpj_dv, contact_type, confidence DESC)
    WHERE status = 'active';

CREATE INDEX idx_enriched_contacts_type_value
    ON paid_enrichment.enriched_contacts (contact_type, normalized_value);

CREATE INDEX idx_crawl_requests_status_next
    ON paid_enrichment.crawl_requests (status, next_run_at, priority DESC);

CREATE INDEX idx_billing_entitlements_account_feature
    ON app_private.billing_entitlements (account_id, feature_key, is_enabled);

CREATE INDEX idx_enrichment_access_audit_account_created
    ON paid_enrichment.enrichment_access_audit (account_id, created_at DESC);
```

Role policy:

```sql
-- Names are illustrative. Apply with least privilege in real migrations.
REVOKE ALL ON SCHEMA paid_enrichment FROM PUBLIC;
REVOKE ALL ON SCHEMA app_private FROM PUBLIC;

-- api_public can read only RF/public tables and must not read paid_enrichment.
-- api_paid can read published contacts/views and insert access audit rows.
-- enrichment_worker can write crawler tables.
-- billing_worker can write app_private billing tables from Stripe webhooks.
```

---

## Crawl Policy

Default settings:

```python
ROBOTSTXT_OBEY = True
CONCURRENT_REQUESTS = 128
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_TIMEOUT = 12
DOWNLOAD_MAXSIZE = 2_000_000
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 0.5
AUTOTHROTTLE_MAX_DELAY = 30
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
DEPTH_LIMIT = 2
REDIRECT_MAX_TIMES = 4
COOKIES_ENABLED = False
```

Use a real user agent that identifies the crawler and includes a contact URL/email, for example:

```text
CNPJDiscoveryBot/1.0 (+https://your-domain.example/crawler)
```

Per-company crawl budget:

- Domain candidate: 1 to 2 pages.
- Likely domain: 5 pages.
- Verified domain: 10 to 20 pages.
- JS fallback: max 1 to 3 pages only.

Stop conditions:

- Contact found with high confidence.
- Robots disallow.
- HTTP 401/403/429.
- Too many redirects.
- Content too large.
- Non-HTML content except sitemap/feed.
- Domain-level failure threshold reached.

---

## Extraction Techniques

### Emails

Sources:

- `mailto:` links.
- Visible text emails.
- JSON-LD `email`.
- Microdata/RDFa organization fields.
- Footer/contact pages.

Normalize:

- Lowercase domain.
- Validate syntax with `email-validator`.
- Optional MX deliverability check with cached DNS.
- Reject placeholders: `email@email.com`, `teste@`, `example@`, `seuemail@`, image-only OCR not in MVP.

Confidence:

- Email on verified domain contact page: high.
- Email domain equals verified company domain: high.
- Public provider email: medium unless CNPJ/name appears on same page.
- Email from unverified directory: low.

### Phones And WhatsApp

Sources:

- `tel:` links.
- Visible phone patterns.
- `wa.me/{number}`.
- `api.whatsapp.com/send?phone={number}`.
- JSON-LD `telephone`.

Normalize:

- Parse as Brazil (`BR`) using `phonenumbers`.
- Store E.164 when possible.
- Classify mobile/fixed/unknown.
- Compare DDD with RF address/DDD when available.

Confidence:

- WhatsApp link on verified domain: high.
- Phone in JSON-LD on verified domain: high.
- Phone matching RF phone: very high and confirms domain.
- Random phone on low-confidence page: do not publish automatically.

### Websites

Normalize:

- Store registered domain and canonical homepage.
- Prefer HTTPS.
- Strip tracking parameters.
- Canonicalize trailing slash and redirects.

Reject:

- Directories.
- Social-only pages as website unless no domain exists; then store as social/profile, not website.
- Parked domains.

### Social Profiles

Accepted only when linked from verified domain or when the page itself has strong identity evidence.

Supported:

- Instagram
- Facebook
- LinkedIn company page
- YouTube
- TikTok
- X/Twitter
- WhatsApp links
- Linktree/beacons style profile pages, only if linked from verified domain.

Do not scrape logged-in social pages. Store the URL; do not attempt to extract private or personal data.

---

## Confidence Model

Contact confidence should combine:

```text
contact_confidence =
  source_weight
  + domain_confidence_weight
  + page_type_weight
  + extractor_weight
  + recency_weight
  + cross_match_weight
  - risk_penalties
```

Suggested rules:

| Condition | Score Impact |
|---|---:|
| Official verified domain >= 80 | +30 |
| Exact CNPJ on same page | +30 |
| Contact/about page | +15 |
| JSON-LD Organization field | +15 |
| mailto/tel explicit link | +10 |
| Visible regex only | +5 |
| Same value appears in RF | +25 |
| Same value appears across multiple pages | +10 |
| Page older than 18 months from archive | -10 |
| Directory/aggregator source | -25 |
| No entity match beyond fuzzy name | -30 |

Publish thresholds:

- `>= 85`: publish as active.
- `70-84`: publish but mark as medium confidence.
- `50-69`: store as candidate, not default visible.
- `< 50`: reject or keep raw only for audit.

---

## API Changes

Public `GET /v1/empresa/{cnpj}` must remain safe for non-subscribers. It may return RF fields and an availability flag, but paid crawler contacts should be served through paid routes.

Preferred paid route: `GET /v1/paid/empresa/{cnpj}/enrichment`.

```json
{
  "enrichment": {
    "status": "done",
    "last_enriched_at": "2026-05-08T10:00:00Z",
    "domains": [
      {
        "domain": "empresa.com.br",
        "homepage_url": "https://empresa.com.br/",
        "confidence": 92,
        "status": "verified"
      }
    ],
    "contacts": [
      {
        "type": "email",
        "value": "contato@empresa.com.br",
        "confidence": 94,
        "source": "official_site",
        "evidence_url": "https://empresa.com.br/contato"
      }
    ]
  }
}
```

For public users, the equivalent safe shape is:

```json
{
  "enrichment_available": true,
  "enrichment_required_feature": "crawler_contacts"
}
```

Extend prospecting filters:

- `has_enriched_email`
- `has_enriched_phone`
- `has_whatsapp`
- `has_website`
- `min_contact_confidence`
- `enrichment_status`
- `enriched_after`
- `contact_type`

Add paid/internal/admin endpoints:

- `GET /v1/paid/empresa/{cnpj}/enrichment`
- `GET /v1/paid/enrichment/{cnpj}/evidence`
- `POST /v1/paid/enrichment/contact/{id}/feedback`
- `POST /v1/paid/export`
- `POST /v1/internal/enrichment/{cnpj}/enqueue`

Required route behavior:

- Missing authentication: `401`.
- Authenticated but no paid entitlement: `403` or `402`, chosen consistently by product policy.
- Expired/canceled Stripe subscription: no paid fields and no export generation.
- Entitlement must be checked before query execution and again before async export delivery.
- Every successful paid read/export inserts `paid_enrichment.enrichment_access_audit`.

---

## White-Label Product Shape

This engine can become a white-label enrichment product if the enrichment layer is treated as its own bounded system.

Product modules:

- `Enrichment API`: lookup by CNPJ, domain, email, phone, segment or export job.
- `Evidence API`: show source URL, confidence, first seen, last seen and extractor.
- `Batch API`: submit CNPJ lists and receive enriched output asynchronously.
- `Webhook publisher`: notify when a batch is done or when new high-confidence contacts are found.
- `Tenant policy`: per-customer quotas, allowed contact types, export limits and suppression rules.
- `Source adapter registry`: each source has a name, version, terms/risk note, parser and scoring rules.
- `Feedback loop`: customers can mark contact valid, invalid, bounced, not company, or suppressed.

Feature parity target versus paid tools:

| Paid-tool capability | Own implementation path |
|---|---|
| Company website | Domain discovery + entity resolution |
| Corporate email | Official-site extraction + RF email-domain inference |
| Phone/WhatsApp | Official-site extraction + phone normalization |
| Social URLs | Links from verified official website |
| Confidence score | Evidence-based scoring model |
| Freshness | `first_seen`, `last_seen`, revisit scheduler |
| Auditability | Evidence URL and extractor metadata |
| Bulk enrichment | Batch API + async workers |

Do not try to beat paid data brokers on person-level contacts in the first product. Win on transparent company-level contacts, provenance, Brazilian CNPJ identity resolution, and low operating cost.

---

## Observability

Metrics:

- Targets queued/running/done/error.
- Crawl requests per domain.
- HTTP status distribution.
- Robots disallowed count.
- 429/403 rate.
- Pages fetched per accepted contact.
- Contact yield by source.
- Precision audit sample by source.
- Median enrichment latency.
- Queue lag.
- Playwright fallback rate.
- Contacts accepted/rejected/conflicted.

Logs:

- Structured logs with `cnpj`, `domain`, `url`, `task_id`, `source`, `confidence`, `decision`.

Dashboards:

- Daily enrichment coverage.
- Contacts by confidence bucket.
- Top failing domains.
- Source yield and precision.
- Cost proxy: requests/contact and CPU/contact.

---

## Compliance And Product Risk

CNPJ and company registration data are not automatically personal data, but emails, phone numbers, social profiles, and names can identify natural persons. Treat enriched contacts as potentially personal data when the value is tied to a person or sole proprietor.

Required product controls:

- Source provenance for every contact.
- Suppression table for removal requests.
- Public crawler information page.
- Data retention policy for raw HTML.
- Do not expose raw page dumps in the API.
- Do not expose crawler-derived contact data in public RF endpoints.
- Stripe entitlement checks must happen server-side before reading `paid_enrichment`.
- Paid export files must be short-lived, account-bound and regenerated only for active subscribers.
- Audit trail for contact changes.
- Audit trail for paid reads and exports.
- Ability to delete/suppress enriched contacts independently of RF records.
- Legitimate-interest assessment before commercial outreach features.
- Clear distinction between company contact and person contact.

---

## Performance Model

Avoid thinking in "CNPJs per second". Think in "domains verified per day" and "pages per accepted contact".

Suggested MVP budgets:

- 1 to 2 pages for domain candidate validation.
- 5 pages for likely domains.
- 10 pages for verified domains.
- Playwright below 5% of total pages.
- Revisit high-confidence contacts every 90 to 180 days.
- Revisit low-confidence or missing-contact companies faster only when they match active customer filters.

Expected bottlenecks:

- Domain discovery quality.
- DNS and failed domains.
- Sites without static contact data.
- Duplicate companies sharing the same domain.
- Branches/franchises using one national website.

Optimization order:

1. Improve target priority.
2. Improve domain verification precision.
3. Use sitemaps and URL heuristics to reduce pages/domain.
4. Improve extraction/normalization.
5. Add Common Crawl cache path.
6. Add Playwright fallback last.

---

## MVP Definition

The first production-worthy MVP should enrich only:

- Website/domain.
- Additional email.
- Additional phone.
- WhatsApp.
- Social URLs linked from official website.

MVP target:

- Run on a filtered batch of active companies.
- Publish only contacts `confidence >= 85`.
- Store medium-confidence candidates but hide them by default.
- Keep evidence URL for every published contact.
- Provide operational dashboard metrics.

Do not start with all 50M establishments. Start with a segment:

- Active companies.
- One UF or one CNAE group.
- Missing RF email or phone.
- High commercial value.
- 10k to 100k companies for first validation.

---

## Research Sources

- Scrapy settings, robots and concurrency: https://docs.scrapy.org/en/latest/topics/settings.html
- Scrapy AutoThrottle: https://docs.scrapy.org/en/master/topics/autothrottle.html
- Scrapy crawl persistence/JOBDIR: https://docs.scrapy.org/en/master/topics/jobs.html
- HTTPX async client and resource limits: https://www.python-httpx.org/async/ and https://www.python-httpx.org/advanced/resource-limits/
- Playwright Python fallback rendering: https://playwright.dev/python/docs/intro
- Common Crawl Columnar Index: https://commoncrawl.org/columnar-index
- Robots Exclusion Protocol RFC 9309: https://www.rfc-editor.org/rfc/rfc9309
- Sitemaps protocol: https://www.sitemaps.org/protocol.html
- Trafilatura docs: https://trafilatura.readthedocs.io/
- extruct metadata extraction: https://pypi.org/project/extruct/
- SearXNG self-hosted metasearch reference: https://docs.searxng.org/
- phonenumbers: https://pypi.org/project/phonenumbers/
- email-validator: https://pypi.org/project/email-validator/
