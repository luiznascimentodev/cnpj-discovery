-- CNPJ Discovery - Domain-First Scale Architecture
-- Phase 1: domain_crawl_jobs, domain_pages, domain_contact_candidates,
--          company_domain_signals, worker_heartbeats, crawl_hosts extensions.

-- 1. Extend crawl_hosts with host policy and circuit breaker fields
ALTER TABLE paid_enrichment.crawl_hosts
    ADD COLUMN IF NOT EXISTS min_delay_seconds NUMERIC(8,2) NOT NULL DEFAULT 1.0,
    ADD COLUMN IF NOT EXISTS max_concurrency INT NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS latency_ewma_ms INT,
    ADD COLUMN IF NOT EXISTS last_http_status INT,
    ADD COLUMN IF NOT EXISTS last_retry_after_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS circuit_state TEXT NOT NULL DEFAULT 'closed',
    ADD COLUMN IF NOT EXISTS circuit_opened_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS crawl_budget_per_day INT NOT NULL DEFAULT 25,
    ADD COLUMN IF NOT EXISTS crawl_budget_used INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS crawl_budget_date DATE NOT NULL DEFAULT current_date;

-- 2. Domain-first crawl job queue (unique per domain+url+crawl_profile)
CREATE TABLE IF NOT EXISTS paid_enrichment.domain_crawl_jobs (
    id BIGSERIAL PRIMARY KEY,
    domain TEXT NOT NULL,
    url TEXT NOT NULL,
    crawl_profile TEXT NOT NULL DEFAULT 'static_http',
    source TEXT NOT NULL DEFAULT 'verified_domain',
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

CREATE INDEX IF NOT EXISTS idx_domain_crawl_jobs_due
    ON paid_enrichment.domain_crawl_jobs (status, next_run_at, priority DESC, id);

CREATE INDEX IF NOT EXISTS idx_domain_crawl_jobs_domain_status
    ON paid_enrichment.domain_crawl_jobs (domain, status);

-- 3. Domain pages (unique per domain+url+content_hash for idempotent ingestion)
CREATE TABLE IF NOT EXISTS paid_enrichment.domain_pages (
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

CREATE INDEX IF NOT EXISTS idx_domain_pages_domain
    ON paid_enrichment.domain_pages (domain, fetched_at DESC);

-- 4. Domain contact candidates (extracted once per domain page)
CREATE TABLE IF NOT EXISTS paid_enrichment.domain_contact_candidates (
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

CREATE INDEX IF NOT EXISTS idx_domain_contact_candidates_domain
    ON paid_enrichment.domain_contact_candidates (domain, contact_type, confidence DESC);

-- 5. Company-domain signal audit (explainable scoring)
CREATE TABLE IF NOT EXISTS paid_enrichment.company_domain_signals (
    id BIGSERIAL PRIMARY KEY,
    company_domain_id BIGINT NOT NULL REFERENCES paid_enrichment.company_domains(id),
    signal_key TEXT NOT NULL,
    signal_value TEXT,
    score_delta SMALLINT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_company_domain_signals_cd
    ON paid_enrichment.company_domain_signals (company_domain_id, observed_at DESC);

-- 6. Worker heartbeats (operations visibility)
CREATE TABLE IF NOT EXISTS paid_enrichment.worker_heartbeats (
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

-- Grants for new tables
GRANT SELECT, INSERT, UPDATE, DELETE
    ON paid_enrichment.domain_crawl_jobs TO enrichment_worker;
GRANT USAGE, SELECT
    ON SEQUENCE paid_enrichment.domain_crawl_jobs_id_seq TO enrichment_worker;

GRANT SELECT, INSERT, UPDATE, DELETE
    ON paid_enrichment.domain_pages TO enrichment_worker;
GRANT USAGE, SELECT
    ON SEQUENCE paid_enrichment.domain_pages_id_seq TO enrichment_worker;

GRANT SELECT, INSERT, UPDATE, DELETE
    ON paid_enrichment.domain_contact_candidates TO enrichment_worker;
GRANT USAGE, SELECT
    ON SEQUENCE paid_enrichment.domain_contact_candidates_id_seq TO enrichment_worker;

GRANT SELECT, INSERT, UPDATE, DELETE
    ON paid_enrichment.company_domain_signals TO enrichment_worker;
GRANT USAGE, SELECT
    ON SEQUENCE paid_enrichment.company_domain_signals_id_seq TO enrichment_worker;

GRANT SELECT, INSERT, UPDATE, DELETE
    ON paid_enrichment.worker_heartbeats TO enrichment_worker;
