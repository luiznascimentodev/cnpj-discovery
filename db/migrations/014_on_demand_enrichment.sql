-- CNPJ Discovery - On-demand enrichment jobs and ETL dataset manifests.

CREATE TABLE IF NOT EXISTS app_private.enrichment_jobs (
    id BIGSERIAL PRIMARY KEY,
    account_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('selection','filter')),
    filter_hash TEXT NOT NULL,
    filters_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL CHECK (status IN (
        'draft','estimating','queued','running','completed',
        'completed_with_errors','cancelled','failed'
    )),
    priority SMALLINT NOT NULL DEFAULT 1000 CHECK (priority BETWEEN 0 AND 1000),
    plan_key TEXT NOT NULL DEFAULT 'default',
    requested_count INT NOT NULL DEFAULT 0 CHECK (requested_count >= 0),
    accepted_count INT NOT NULL DEFAULT 0 CHECK (accepted_count >= 0),
    cache_hit_count INT NOT NULL DEFAULT 0 CHECK (cache_hit_count >= 0),
    skipped_count INT NOT NULL DEFAULT 0 CHECK (skipped_count >= 0),
    failed_count INT NOT NULL DEFAULT 0 CHECK (failed_count >= 0),
    ready_count INT NOT NULL DEFAULT 0 CHECK (ready_count >= 0),
    cost_credits INT NOT NULL DEFAULT 0 CHECK (cost_credits >= 0),
    idempotency_key TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS app_private.enrichment_job_items (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES app_private.enrichment_jobs(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL,
    cnpj_basico CHAR(8) NOT NULL,
    cnpj_ordem CHAR(4) NOT NULL,
    cnpj_dv CHAR(2) NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'pending','leased','cache_hit','enriched','no_public_contact',
        'skipped_inactive','failed_retryable','failed_terminal','cancelled'
    )),
    priority SMALLINT NOT NULL DEFAULT 1000 CHECK (priority BETWEEN 0 AND 1000),
    attempts INT NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    locked_by TEXT,
    locked_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    result_source TEXT CHECK (result_source IS NULL OR result_source IN ('cache','fresh_crawl','rf_only','none')),
    cache_fresh_until TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (job_id, cnpj_basico, cnpj_ordem, cnpj_dv)
);

CREATE TABLE IF NOT EXISTS app_private.enrichment_credit_ledger (
    id BIGSERIAL PRIMARY KEY,
    account_id TEXT NOT NULL,
    job_id BIGINT REFERENCES app_private.enrichment_jobs(id),
    amount INT NOT NULL,
    reason TEXT NOT NULL CHECK (reason IN ('reserve','debit','refund','adjustment')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_private.etl_dataset_snapshots (
    id BIGSERIAL PRIMARY KEY,
    snapshot_key TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('discovered','pending_load','loading','loaded','failed','ignored')),
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    selected_at TIMESTAMPTZ,
    loaded_at TIMESTAMPTZ,
    manifest_hash TEXT NOT NULL,
    file_count INT NOT NULL CHECK (file_count >= 0),
    total_size_bytes BIGINT NOT NULL DEFAULT 0 CHECK (total_size_bytes >= 0),
    last_modified_max TIMESTAMPTZ,
    last_error TEXT,
    UNIQUE (source_name, snapshot_key)
);

CREATE TABLE IF NOT EXISTS app_private.etl_dataset_files (
    id BIGSERIAL PRIMARY KEY,
    snapshot_id BIGINT NOT NULL REFERENCES app_private.etl_dataset_snapshots(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    url TEXT NOT NULL,
    size_bytes BIGINT NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
    etag TEXT,
    last_modified TIMESTAMPTZ,
    sha256 TEXT,
    UNIQUE (snapshot_id, file_name)
);

CREATE INDEX IF NOT EXISTS idx_enrichment_jobs_account_created
    ON app_private.enrichment_jobs (account_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_enrichment_jobs_status_priority
    ON app_private.enrichment_jobs (status, priority DESC, created_at);

CREATE INDEX IF NOT EXISTS idx_enrichment_job_items_claim
    ON app_private.enrichment_job_items (status, priority DESC, lease_expires_at, id)
    WHERE status IN ('pending','failed_retryable');

CREATE INDEX IF NOT EXISTS idx_enrichment_job_items_account_job
    ON app_private.enrichment_job_items (account_id, job_id, id);

CREATE INDEX IF NOT EXISTS idx_etl_dataset_snapshots_status
    ON app_private.etl_dataset_snapshots (status, discovered_at DESC);

GRANT SELECT, INSERT, UPDATE, DELETE
    ON app_private.enrichment_jobs,
       app_private.enrichment_job_items,
       app_private.enrichment_credit_ledger,
       app_private.etl_dataset_snapshots,
       app_private.etl_dataset_files
    TO api_paid, enrichment_worker, billing_worker;

GRANT USAGE, SELECT
    ON ALL SEQUENCES IN SCHEMA app_private
    TO api_paid, enrichment_worker, billing_worker;
