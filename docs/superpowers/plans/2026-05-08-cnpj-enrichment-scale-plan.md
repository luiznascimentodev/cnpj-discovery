# CNPJ Enrichment Scale Plan

**Date:** 2026-05-08  
**Status:** Proposed, not implemented  
**Related docs:**
- `docs/superpowers/specs/2026-05-08-cnpj-enrichment-engine.md`
- `docs/superpowers/plans/2026-05-08-cnpj-enrichment-engine-plan.md`
- `docs/superpowers/plans/2026-05-08-cnpj-enrichment-implementation-todo.md`

---

## Goal

Scale the enrichment crawler from manual/small batches to millions of CNPJs without restarting from zero, without repeatedly crawling the same website, and without increasing false positives or unnecessary blocks.

The core architecture change is:

```text
current: CNPJ -> candidate domains -> crawl pages -> publish contacts
target:  CNPJ -> verified domain link -> unique domain crawl -> domain contacts -> CNPJ resolver/publication
```

This is the highest-leverage change because millions of CNPJs do not mean millions of unique official domains, and many CNPJs either share a domain, have no usable site, or only have weak/generic signals.

---

## Non-Goals And Safety Rules

- Do not build bypass logic to evade robots.txt, 403, 429, captchas, or explicit blocks.
- Do not rotate IPs to keep hitting a domain that is refusing traffic.
- Do not use stealth browser libraries as a default crawler mode.
- Do not publish contacts from unverified domains.
- Do not crawl every possible brand-slug domain for every CNPJ.
- Do not delete raw evidence without a retention policy.

Allowed outbound/network techniques:

- Use stable, documented egress IPs for reliability, observability and reputation management.
- Use a clear user agent with contact URL.
- Use per-domain budgets across all workers and all egress IPs.
- Use proxies only as controlled egress infrastructure, not as block evasion.
- Stop or slow down on robots disallow, 403, 429, Retry-After, timeout clusters, or captcha signals.

Reasoning: the fastest sustainable crawler is not the one that can hit a site the hardest. It is the one that avoids bad requests, reuses work, respects backpressure, and publishes only high-confidence results.

---

## External Technique Review

### Scrapy AutoThrottle

Reference: https://docs.scrapy.org/en/latest/topics/autothrottle.html

Useful idea to copy even if we keep the current `httpx` runner:

- Dynamic delay per remote website based on latency.
- Non-200 responses must not reduce delay.
- Hard caps still apply through per-domain concurrency.
- Target concurrency is a suggestion, not permission to burst.

Recommendation:

- Do not migrate the whole crawler to Scrapy immediately.
- Implement the same policy in the existing DB-backed queue first because we already have Postgres leases, evidence tables and tests.
- Keep Scrapy as a future backend candidate if the in-house runner becomes too costly to maintain.

### Crawlee for Python

References:
- https://crawlee.dev/python/docs/next/guides/architecture-overview
- https://crawlee.dev/python/docs/next/guides/scaling-crawlers
- https://crawlee.dev/python/api/0.6/class/AutoscaledPool

Useful features:

- HTTP and Playwright crawler families.
- Autoscaled pool based on CPU/memory pressure.
- Built-in retries, crawling lifecycle and browser fallback patterns.

Recommendation:

- Evaluate Crawlee as a Phase 6 optional backend, not Phase 1.
- The current product needs database checkpoints, CNPJ/domain resolution and strict evidence publishing more than a framework swap.
- If adopted, use Crawlee inside our worker as a page-fetch engine while Postgres remains the source of truth for queue state.

### Playwright

References:
- https://playwright.dev/python/docs/browser-contexts
- https://playwright.dev/python/docs/api/class-browsercontext

Useful feature:

- Isolated browser contexts are cheap compared to launching one browser per page.
- Good fallback for JS-heavy pages where static HTML does not expose contacts.

Recommendation:

- Add a low-throughput Playwright fallback queue after static crawling.
- Use it only for verified domains where static crawl found no contacts and the page looks JS-rendered.
- Apply strict budgets: e.g. max 1-2 browser pages per domain, low global concurrency, no infinite scrolling, no login, no captcha solving.

### AIHawk Repository Lessons

Local repo inspected: `/home/luife/projetos/Jobs_Applier_AI_Agent_AIHawk`

Useful ideas to adapt:

- Suitability gate before action: AIHawk scores whether a job is worth applying to. For us, score whether a domain is worth crawling/publishing before spending network budget.
- Apply once per company: map to "crawl once per official domain" and reuse results for linked CNPJs.
- Rate-limit handling: AIHawk reads retry headers for LLM calls and waits before retrying. For us, respect `Retry-After` from websites and persist `next_run_at`.
- Browser automation is expensive: AIHawk uses Selenium for pages that need a browser. For us, browser crawling is fallback only, not the default.
- Logging matters: keep structured logs for claim, request start, robots, retry, blocked, extraction and publication.

Not useful or not acceptable:

- Browser flags intended to weaken browser security are not appropriate for the crawler.
- There is no reusable anti-blocking strategy in AIHawk that should be copied into this product.

---

## Target Architecture

```text
RF tables
  |
  v
Seed strategies with persistent cursors
  |
  v
company_domain_links / company_domains
  |
  v
Domain verifier
  |
  v
domain_crawl_jobs  -----> crawl_host_policies
  |                         |
  v                         v
Static HTTP crawler  <--- global + per-host budgets
  |
  v
domain_pages -> domain_contact_candidates
  |
  v
Company resolver/publisher
  |
  v
enriched_contacts / published_contacts
```

Key principles:

- Postgres is the durable source of truth.
- Redis can accelerate rate limits and distributed semaphores, but Postgres must be enough to recover after Redis loss.
- Queue claims are at-least-once; writes must be idempotent.
- Every long-running stage has a checkpoint.
- Every published contact has evidence and a verified domain relation.

---

## Database Plan

### 1. Domain crawl jobs

Create a domain-first queue that is unique by `domain + url + crawl_profile`.

Suggested table:

```sql
CREATE TABLE paid_enrichment.domain_crawl_jobs (
    id BIGSERIAL PRIMARY KEY,
    domain TEXT NOT NULL,
    url TEXT NOT NULL,
    crawl_profile TEXT NOT NULL,
    source TEXT NOT NULL,
    priority SMALLINT NOT NULL DEFAULT 50 CHECK (priority BETWEEN 0 AND 100),
    status TEXT NOT NULL CHECK (status IN (
        'pending','running','done','retry','blocked','skipped','error'
    )),
    depth SMALLINT NOT NULL DEFAULT 0,
    attempts INT NOT NULL DEFAULT 0,
    next_run_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_at TIMESTAMPTZ,
    locked_by TEXT,
    last_http_status INT,
    last_error TEXT,
    last_content_hash TEXT,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (domain, url, crawl_profile)
);
```

Indexes:

```sql
CREATE INDEX idx_domain_crawl_jobs_due
    ON paid_enrichment.domain_crawl_jobs (status, next_run_at, priority DESC, id);

CREATE INDEX idx_domain_crawl_jobs_domain_status
    ON paid_enrichment.domain_crawl_jobs (domain, status);
```

Why:

- Current `crawl_requests` is CNPJ-scoped, so the same domain can be crawled repeatedly.
- This table lets many CNPJs share one domain crawl result.

### 2. Domain pages

Create domain pages independent of CNPJ.

Suggested table:

```sql
CREATE TABLE paid_enrichment.domain_pages (
    id BIGSERIAL PRIMARY KEY,
    domain_crawl_job_id BIGINT REFERENCES paid_enrichment.domain_crawl_jobs(id),
    domain TEXT NOT NULL,
    url TEXT NOT NULL,
    canonical_url TEXT,
    http_status INT CHECK (http_status IS NULL OR (http_status BETWEEN 100 AND 599)),
    content_type TEXT,
    content_hash TEXT NOT NULL,
    title TEXT,
    html_excerpt TEXT,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_storage_key TEXT,
    etag TEXT,
    last_modified TEXT,
    UNIQUE (domain, url, content_hash)
);
```

Why:

- Re-fetching unchanged pages should not create duplicate work.
- `etag` and `last_modified` prepare future conditional requests.

### 3. Domain contact candidates

Store extracted contacts once per domain evidence.

Suggested table:

```sql
CREATE TABLE paid_enrichment.domain_contact_candidates (
    id BIGSERIAL PRIMARY KEY,
    domain_page_id BIGINT NOT NULL REFERENCES paid_enrichment.domain_pages(id),
    domain TEXT NOT NULL,
    contact_type TEXT NOT NULL CHECK (contact_type IN (
        'email','phone','whatsapp','website','social'
    )),
    raw_value TEXT NOT NULL,
    normalized_value TEXT,
    label TEXT,
    context TEXT,
    confidence SMALLINT NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    extractor TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (domain, contact_type, normalized_value, domain_page_id)
);
```

Why:

- Separates "what the domain exposes" from "which CNPJ should receive it".
- Makes re-resolution cheap when scoring rules improve.

### 4. Company-domain relation audit

Keep using `company_domains`, but add fields or a side table for explainability.

Preferred additive table:

```sql
CREATE TABLE paid_enrichment.company_domain_signals (
    id BIGSERIAL PRIMARY KEY,
    company_domain_id BIGINT NOT NULL REFERENCES paid_enrichment.company_domains(id),
    signal_key TEXT NOT NULL,
    signal_value TEXT,
    score_delta SMALLINT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Examples:

- `rf_email_domain_match`
- `cnpj_exact_match`
- `legal_name_match`
- `fantasy_name_match`
- `phone_match`
- `cep_city_uf_match`
- `parked_page_penalty`
- `generic_directory_penalty`

Why:

- False positives need explainable debugging.
- Later we can show why a domain was accepted or rejected.

### 5. Host policy and checkpoint table

Evolve or extend `crawl_hosts`.

Suggested fields:

```sql
ALTER TABLE paid_enrichment.crawl_hosts
    ADD COLUMN IF NOT EXISTS min_delay_seconds NUMERIC(8,2) DEFAULT 1.0,
    ADD COLUMN IF NOT EXISTS max_concurrency INT DEFAULT 1,
    ADD COLUMN IF NOT EXISTS latency_ewma_ms INT,
    ADD COLUMN IF NOT EXISTS last_http_status INT,
    ADD COLUMN IF NOT EXISTS last_retry_after_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS circuit_state TEXT DEFAULT 'closed',
    ADD COLUMN IF NOT EXISTS circuit_opened_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS crawl_budget_per_day INT DEFAULT 25,
    ADD COLUMN IF NOT EXISTS crawl_budget_used INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS crawl_budget_date DATE DEFAULT current_date;
```

Why:

- Rate limit and blocking policy must survive worker restarts.
- Budget is per host/domain, not per worker.

### 6. Worker heartbeat

Suggested table:

```sql
CREATE TABLE paid_enrichment.worker_heartbeats (
    worker_id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    hostname TEXT,
    pid INT,
    current_stage TEXT,
    current_job_id BIGINT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

Why:

- Makes stuck workers visible.
- Gives operations a reliable way to know whether a worker is alive.

---

## Checkpoint And Resume Model

This system must assume crashes, deploy restarts, network timeouts and partial writes.

### Seed checkpoint

Use one cursor per seed strategy:

- `missing_contacts`
- `rf_corporate_email_domain`
- `verified_domain_recheck`
- `high_value_segments`
- `manual_batch`

Rules:

- Cursor advances by `(cnpj_basico, cnpj_ordem, cnpj_dv)`.
- Never use `ORDER BY random()` on RF tables.
- Each strategy can be paused/resumed independently.
- Cursor stores `rows_seen`, `rows_inserted`, `last_run_at`, `last_error`.

### Discovery checkpoint

Each `enrichment_targets` row is already a checkpoint.

Improve it by:

- keeping `attempts`, `last_error`, `next_run_at`;
- adding explicit terminal reasons: `no_candidate_domain`, `weak_domain`, `verified_domain_linked`;
- never reprocessing `done` unless a reverify reason is enqueued.

### Domain crawl checkpoint

Each `domain_crawl_jobs` row is a checkpoint.

Rules:

- `pending` and `retry` are claimable.
- `running` gets a lease.
- stale `running` jobs are released by `release-stale`.
- `done`, `blocked`, `skipped`, `error` are terminal unless explicitly reset.
- retry always sets `next_run_at`.
- `Retry-After` overrides generic backoff.

### Page checkpoint

Each fetched page is idempotent by `(domain, url, content_hash)`.

Rules:

- Same page body should not duplicate extraction.
- Same contact from same domain should not duplicate.
- Publishing to `enriched_contacts` remains idempotent by existing unique key.

### Resolver checkpoint

Domain contacts can be re-resolved without refetching pages.

Rules:

- When scoring changes, enqueue a `resolve_domain_contacts` job.
- Do not recrawl just because resolver rules changed.
- Keep active/rejected/suppressed status history.

### Operational recovery

On restart:

1. Run `release-stale`.
2. Resume seed cursors.
3. Claim due discovery jobs.
4. Claim due domain crawl jobs.
5. Re-run resolver for domains with new candidates.

Expected semantics:

- Not exactly-once.
- At-least-once execution with idempotent writes.
- No need to restart from the first CNPJ.

---

## Queue And Worker Design

### Worker roles

Split into separate roles so scaling is controlled:

- `seed-worker`: scans RF tables and creates target rows.
- `discovery-worker`: verifies domains and creates domain jobs.
- `domain-crawler-worker`: fetches pages and extracts domain contacts.
- `resolver-worker`: maps domain contacts to CNPJs and publishes.
- `maintenance-worker`: releases stale leases, expires budgets, recomputes stats.

Why:

- Crawling is network-bound.
- Seeding is DB-bound.
- Resolving is CPU/DB-bound.
- Scaling them together wastes resources.

### Claim pattern

Use the existing pattern everywhere:

```sql
WITH due AS (
    SELECT id
    FROM paid_enrichment.domain_crawl_jobs
    WHERE status IN ('pending', 'retry')
      AND next_run_at <= now()
      AND (locked_at IS NULL OR locked_at < now() - make_interval(secs => $lease_seconds))
    ORDER BY priority DESC, next_run_at, id
    LIMIT $batch_size
    FOR UPDATE SKIP LOCKED
)
UPDATE paid_enrichment.domain_crawl_jobs job
SET status = 'running',
    locked_at = now(),
    locked_by = $worker_id,
    attempts = job.attempts + 1,
    updated_at = now()
FROM due
WHERE job.id = due.id
RETURNING job.*;
```

### Horizontal scaling

Run multiple worker containers:

```bash
docker compose --profile worker up -d --scale enrichment-worker=4
```

But after roles are split, prefer:

```bash
docker compose up -d --scale domain-crawler-worker=8 --scale discovery-worker=2 --scale resolver-worker=2
```

Each worker must have:

- `WORKER_ROLE`
- `WORKER_ID`
- `GLOBAL_CONCURRENCY`
- `MAX_CONCURRENCY_PER_HOST`
- `LEASE_SECONDS`
- `BATCH_SIZE`

---

## Rate Limit, Backpressure And Blocking Policy

### Global limit

Controls total outbound pressure per worker.

Initial default:

- `GLOBAL_CONCURRENCY=20` for static HTTP per worker.
- `GLOBAL_CONCURRENCY=2` for Playwright fallback per whole deployment.

### Per-host limit

Initial default:

- `MAX_CONCURRENCY_PER_HOST=1`
- `MIN_DELAY_SECONDS=1.0`
- `MAX_PAGES_PER_DOMAIN_PER_RUN=5`
- `MAX_PAGES_PER_DOMAIN_PER_DAY=25`

Increase only for known-safe domains after metrics prove low error rate.

### Adaptive delay

Maintain EWMA latency per host.

Suggested rule:

```text
target_delay = max(
  robots_crawl_delay,
  configured_min_delay,
  latency_ewma_seconds / target_concurrency
)
```

Non-200 responses:

- Can increase delay.
- Must never decrease delay.

### Retry/backoff

Use status-specific backoff:

| Signal | Action |
|---|---|
| 200 | mark done, reset consecutive failures |
| 301/302 | follow bounded redirects, canonicalize |
| 304 | mark unchanged, skip extraction |
| 400/404/410 | mark error or skipped, no hot retry |
| 401/403 | open circuit for host, retry only after long delay |
| 408/425/429 | respect Retry-After; otherwise exponential backoff |
| 500/502/503/504 | exponential backoff with jitter |
| timeout/connect error | retry with backoff; open circuit after threshold |
| SSL hostname mismatch | retry HTTP fallback once if policy allows, then block host |
| captcha/interstitial | blocked, no bypass |
| robots disallow | skipped/blocked, no bypass |

### Circuit breaker

Per host states:

- `closed`: normal.
- `open`: no requests until `blocked_until`.
- `half_open`: allow one test request.

Open circuit when:

- 5 consecutive network failures.
- 3 consecutive 403/429.
- robots disallow for target paths.
- captcha/interstitial detected.

### Jitter

Always add jitter to retry delays.

Example:

```text
retry_delay = base_delay * 2^(attempts - 1)
retry_delay = min(retry_delay, max_delay)
retry_delay = retry_delay * random(0.8, 1.2)
```

Why:

- Prevents many workers from retrying the same host at the same second.

---

## Domain-First Enrichment Flow

### Step 1: Seed CNPJs cheaply

Priority order:

1. active matriz CNPJs with corporate RF email domain;
2. active companies with strong fantasy/legal name;
3. active companies missing RF contact data;
4. paid/customer-requested segments;
5. weak/generic names last.

Do not start with brand slugs for every CNPJ.

### Step 2: Generate domain candidates

Sources:

- RF email domain.
- Exact CNPJ found on a page.
- Existing verified domain from previous run.
- Strong brand slug only when name is not generic.
- Optional public search adapter later, with strict result scoring.

### Step 3: Verify domain before crawling

Domain status:

- `verified`: enough evidence to crawl and publish from.
- `candidate`: needs more evidence, not publishable.
- `rejected`: not official or too weak.
- `stale`: previously verified but needs refresh.

Recommended verified threshold:

- exact CNPJ on site: verify;
- RF corporate email domain + legal/fantasy identity: verify;
- RF phone + city/UF + identity: verify;
- brand slug only: do not verify alone.

### Step 4: Enqueue domain jobs once

For verified domains, enqueue only canonical high-yield paths:

- `/`
- `/contato`
- `/contact`
- `/sobre`
- `/about`
- `/empresa`
- `/institucional`
- `/atendimento`
- `sitemap.xml` only if robots permits and domain is high confidence.

Unique key prevents duplicate crawling.

### Step 5: Extract domain contacts

Static extraction first:

- `mailto:`
- visible e-mail text with strict validation;
- `tel:`;
- WhatsApp links;
- official social profile URLs only;
- JSON-LD/schema.org Organization/LocalBusiness;
- microdata/RDFa later if needed.

### Step 6: Resolve domain contacts to companies

A contact from a domain can be published to a CNPJ only when:

- `company_domains.status = 'verified'`;
- contact source domain equals the verified domain;
- contact is not RF baseline-only;
- contact is not suppressed;
- confidence >= publication threshold.

For shared domains:

- publish generic domain contacts only when the domain is specific to one company;
- for group/prefeitura/conglomerate domains, require page-level evidence for the exact company/branch;
- otherwise keep as raw candidate, not active publication.

---

## False Positive Controls

### Negative domain classifiers

Reject or downscore:

- public email providers;
- accounting office domains when RF email domain belongs to contador;
- website builders and parked domains;
- marketplaces/directories/catalogs;
- social profile-only domains;
- municipal/government umbrella domains unless page identifies the exact entity;
- white-label templates with no company-specific identity;
- generic slugs from weak names.

### Positive evidence

Boost:

- exact CNPJ text;
- exact RF phone;
- RF email domain;
- legal/fantasy token match;
- address/CEP/city/UF match;
- JSON-LD organization name/telephone/email/address match;
- official social profile linked from verified domain.

### Publication guardrail

Never publish if:

- domain is only `candidate`;
- contact is from an external social/content URL not linked from the official site;
- contact is from a post/reel/feed/watch URL;
- domain is shared and page does not identify the target company.

---

## Performance Strategy

### Biggest speed win

Avoid network requests.

Order of gains:

1. dedupe by domain;
2. reject weak domains before crawl;
3. crawl high-yield paths only;
4. cache pages by hash/ETag/Last-Modified;
5. re-resolve without recrawling;
6. scale workers horizontally.

### Initial production-safe defaults

```text
seed_batch_size=10_000
discovery_workers=2
discovery_batch_size=100
domain_crawler_workers=4
domain_crawler_global_concurrency=20
max_concurrency_per_host=1
max_pages_per_domain_per_run=5
max_pages_per_domain_per_day=25
resolver_workers=2
playwright_global_concurrency=1
```

### Tuning method

Increase only one knob at a time:

1. raise crawler workers;
2. then raise global worker concurrency;
3. then raise per-host concurrency for safe high-capacity domains only;
4. never raise all at once.

Watch:

- 2xx rate;
- 403/429 rate;
- timeout rate;
- average contacts per verified domain;
- false positive review rate;
- domains crawled per hour;
- pages fetched per hour;
- active contacts published per hour.

---

## Observability Plan

### Logs

Keep structured events:

- `seed_batch_start`
- `seed_batch_done`
- `domain_verification_start`
- `domain_verification_done`
- `domain_job_claimed`
- `host_budget_wait`
- `host_circuit_opened`
- `crawler_request_start`
- `crawler_request_done`
- `crawler_request_retry`
- `crawler_request_blocked`
- `crawler_request_error`
- `domain_contacts_extracted`
- `company_contacts_resolved`
- `company_contacts_published`

Required fields:

- `worker_id`
- `job_id`
- `domain`
- `url`
- `cnpj` when applicable
- `attempt`
- `status_code`
- `elapsed_ms`
- `bytes`
- `content_hash`
- `retry_in_seconds`
- `blocked_until`
- `contacts_extracted`
- `contacts_published`

### Metrics

Expose or periodically persist:

- queue depth by status;
- jobs claimed/minute;
- requests/minute;
- pages/minute;
- contacts extracted/minute;
- contacts published/minute;
- false-positive review outcomes;
- average latency by host;
- circuit breaker opens by host;
- top error domains;
- stale leases released;
- duplicate page skips;
- domain dedupe ratio;
- CNPJs resolved per domain.

### Dashboards

Minimum panels:

- backlog by stage;
- throughput by stage;
- publication funnel: CNPJ seeded -> candidate domain -> verified domain -> crawled domain -> contact candidate -> active publication;
- block/error rate by host;
- worker heartbeats;
- slowest domains;
- most productive domain sources.

---

## Library And Framework Decision

### Phase 1 decision

Keep the current `httpx` async runner and add domain-first queue, adaptive throttling and host policies.

Why:

- It already integrates with Postgres queue leases.
- It already has tests.
- It already writes project-specific evidence tables.
- The bottleneck is architecture and dedupe, not lack of a crawler framework.

### Phase 2 candidate

Add optional Crawlee backend behind an internal interface:

```python
class PageFetcher:
    async def fetch(self, job: DomainCrawlJob) -> FetchResult:
        ...
```

Implementations:

- `HttpxPageFetcher`
- `CrawleeHttpPageFetcher` later
- `PlaywrightPageFetcher` fallback

### Phase 3 candidate

If we need a mature spider framework for link expansion:

- evaluate Scrapy with AutoThrottle;
- keep Postgres as source of queue truth;
- do not let Scrapy manage publication state outside our DB.

---

## Implementation Phases

### Phase 0 - Freeze and protect current behavior

- [ ] Keep `enrichment-worker` stopped while changing scale architecture.
- [ ] Add regression tests for current false-positive fixes.
- [ ] Save current small dataset summary.
- [ ] Add feature flag `DOMAIN_FIRST_CRAWLER_ENABLED=false`.

Acceptance:

- Current enrichment tests pass.
- Existing paid API keeps working.
- No background worker starts the old backlog unexpectedly.

### Phase 1 - Domain queue migration

- [ ] Add migration for `domain_crawl_jobs`.
- [ ] Add migration for `domain_pages`.
- [ ] Add migration for `domain_contact_candidates`.
- [ ] Add migration for `company_domain_signals`.
- [ ] Add migration for `worker_heartbeats`.
- [ ] Extend `crawl_hosts` into a real host policy table.
- [ ] Add indexes and grants.
- [ ] Add migration smoke tests.

Acceptance:

- Migration applies cleanly.
- Existing tables and views still work.
- No data is lost.

### Phase 2 - Domain-first scheduler

- [ ] Add `domain_queue.py`.
- [ ] Add `claim_domain_crawl_jobs`.
- [ ] Add `complete_domain_crawl_job`.
- [ ] Add `retry_domain_crawl_job`.
- [ ] Add `release_stale_domain_jobs`.
- [ ] Add idempotent enqueue from verified `company_domains`.
- [ ] Add seed strategy cursors for corporate email domains and manual batches.

Acceptance:

- Same verified domain from many CNPJs creates one job per URL.
- Multiple workers cannot claim the same job.
- Stale jobs resume.

### Phase 3 - Host policy and adaptive throttle

- [ ] Implement per-host budget lookup.
- [ ] Implement per-host circuit breaker.
- [ ] Implement Retry-After handling.
- [ ] Implement EWMA latency update.
- [ ] Implement jittered exponential backoff.
- [ ] Implement Redis semaphore/token bucket as optional accelerator.
- [ ] Persist all decisions in Postgres.

Acceptance:

- 429/403 slows or blocks host.
- Non-200 responses cannot make a host faster.
- Worker restart preserves blocked host state.

### Phase 4 - Domain crawler

- [ ] Add `domain_runner.py`.
- [ ] Fetch domain jobs, not CNPJ jobs.
- [ ] Persist `domain_pages`.
- [ ] Extract into `domain_contact_candidates`.
- [ ] Keep current CNPJ crawler path behind a legacy flag.
- [ ] Add CLI command `domain-crawler-tick`.
- [ ] Add worker role `domain-crawler`.

Acceptance:

- A verified domain can be crawled once.
- Contacts are extracted once per domain page.
- Re-running does not duplicate pages or candidates.

### Phase 5 - Resolver from domain contacts

- [ ] Add resolver that maps `domain_contact_candidates` to verified `company_domains`.
- [ ] Add shared-domain guard.
- [ ] Add exact company/page evidence checks for government/group domains.
- [ ] Publish to existing `enriched_contacts`.
- [ ] Add `resolve-domain-tick` CLI command.

Acceptance:

- Existing paid API still reads `published_contacts`.
- Unverified candidate domains never publish.
- Re-running resolver after rule changes does not recrawl pages.

### Phase 6 - Browser fallback

- [ ] Add `playwright_domain_crawl_jobs` profile or `crawl_profile='playwright_contact_probe'`.
- [ ] Use Playwright browser contexts.
- [ ] Limit to verified domains with zero static contacts.
- [ ] Add strict page/time/request budgets.
- [ ] Add JS-rendered contact extraction only.

Acceptance:

- Browser fallback never becomes the default path.
- A blocked/captcha page is marked blocked, not bypassed.
- Static crawler throughput is not affected by browser jobs.

### Phase 7 - Scale-out compose and operations

- [ ] Split worker commands/services by role.
- [ ] Add env vars for concurrency, batch and budget.
- [ ] Add healthchecks per role.
- [ ] Add dashboard queries.
- [ ] Add runbook for pause/resume.
- [ ] Add emergency stop command.

Acceptance:

- Operators can scale crawler workers without scaling seed workers.
- Operators can pause one host or one role.
- Operators can see backlog and progress.

### Phase 8 - Optional framework experiment

- [ ] Implement `PageFetcher` interface.
- [ ] Add experimental Crawlee HTTP fetcher behind feature flag.
- [ ] Compare against `httpx` runner on a fixed domain sample.
- [ ] Measure throughput, error rate, memory, CPU, publication quality.
- [ ] Keep only if it improves operational results.

Acceptance:

- No framework migration without measured improvement.
- Postgres remains source of truth.

---

## Pause, Resume And Reprocess Commands

Target commands to add:

```bash
python cli.py seed-targets --reason rf_corporate_email_domain --batch-size 10000
python cli.py discovery-tick --reason rf_corporate_email_domain --batch-size 100
python cli.py enqueue-domain-jobs --batch-size 1000
python cli.py domain-crawler-tick --batch-size 100 --concurrency 20
python cli.py resolve-domain-tick --batch-size 1000
python cli.py release-stale --lease-seconds 600
```

Operational queries:

```sql
SELECT status, count(*)
FROM paid_enrichment.domain_crawl_jobs
GROUP BY status
ORDER BY status;

SELECT domain, circuit_state, blocked_until, consecutive_failures
FROM paid_enrichment.crawl_hosts
WHERE circuit_state <> 'closed'
ORDER BY blocked_until DESC;

SELECT worker_id, role, current_stage, heartbeat_at
FROM paid_enrichment.worker_heartbeats
ORDER BY heartbeat_at DESC;
```

Emergency stop:

```bash
docker compose stop domain-crawler-worker
```

Safe resume:

```bash
python cli.py release-stale --lease-seconds 600
docker compose up -d domain-crawler-worker
```

---

## Review Workflow For False Positives

Add a review loop before large-scale publication:

1. Sample every 1,000th active publication.
2. Always sample domains with shared/government/group patterns.
3. Store review result as `accepted`, `false_positive`, `needs_rule`.
4. Feed negative patterns into domain/contact scoring.
5. Re-run resolver only; do not recrawl.

Useful review query:

```sql
SELECT
    pc.cnpj_basico || pc.cnpj_ordem || pc.cnpj_dv AS cnpj,
    cd.domain,
    pc.contact_type,
    pc.normalized_value,
    pc.evidence_url,
    pc.confidence
FROM paid_enrichment.published_contacts pc
JOIN paid_enrichment.company_domains cd
  ON cd.cnpj_basico = pc.cnpj_basico
 AND cd.cnpj_ordem = pc.cnpj_ordem
 AND cd.cnpj_dv = pc.cnpj_dv
 AND cd.domain = pc.source_domain
WHERE cd.status = 'verified'
ORDER BY random()
LIMIT 100;
```

For production, replace `ORDER BY random()` with an indexed sampling table or precomputed review queue.

---

## Rollout Plan

### Small batch

- 1,000 CNPJs.
- Corporate email domains only.
- 1 crawler worker.
- Manual review sample: 100%.

### Medium batch

- 100,000 CNPJs.
- Corporate email domains plus strong fantasy names.
- 2 discovery workers.
- 4 crawler workers.
- Review sample: at least 1,000 publications.

### Large batch

- Millions of CNPJs.
- All seed strategies with priorities.
- Separate worker roles.
- Dashboards required.
- Review sample continuous.

Promotion gate:

- false positive rate below agreed threshold;
- 429/403 below safe threshold;
- no host hot loops;
- no stale running jobs older than lease after release-stale;
- resolver can reprocess without recrawling.

---

## Success Metrics

Technical:

- domain dedupe ratio above 1.5x at minimum, expected much higher;
- stale leases recover automatically;
- no duplicate pages for identical content hash;
- domain crawl queue can be paused/resumed without data loss;
- all crawler modules keep 100% test coverage.

Business/data:

- verified domains per hour;
- active contacts per hour;
- false positive rate from review;
- percentage of CNPJs enriched by RF email-domain path;
- contacts per verified domain;
- cost per active contact.

Safety:

- 403/429 trend stable or decreasing;
- circuit breaker opens visible in dashboard;
- no crawler behavior that bypasses robots, captcha or explicit blocks.

---

## First Implementation Slice

The first slice should be small and shippable:

1. Add migrations for `domain_crawl_jobs`, `domain_pages`, `domain_contact_candidates`, `company_domain_signals`, `worker_heartbeats`.
2. Add queue module and tests for claim/complete/retry/release.
3. Add CLI command to enqueue domain jobs from verified `company_domains`.
4. Add CLI command to process domain jobs with current `httpx` fetcher.
5. Add resolver that republishes existing `published_contacts` path from domain contacts.
6. Run on the same 10-company simple batch.
7. Compare:
   - old CNPJ-scoped requests;
   - new domain-scoped requests;
   - contacts published;
   - false positives.

Only after this slice passes should we scale worker counts.

