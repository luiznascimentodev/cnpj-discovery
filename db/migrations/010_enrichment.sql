-- CNPJ Discovery - Paid Enrichment Boundary
-- Crawler-derived data is stored separately from Receita Federal public data.

CREATE SCHEMA IF NOT EXISTS paid_enrichment;
CREATE SCHEMA IF NOT EXISTS app_private;

DO $$
BEGIN
    CREATE ROLE api_public NOLOGIN;
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

DO $$
BEGIN
    CREATE ROLE api_paid NOLOGIN;
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

DO $$
BEGIN
    CREATE ROLE enrichment_worker NOLOGIN;
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

DO $$
BEGIN
    CREATE ROLE billing_worker NOLOGIN;
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

CREATE TABLE IF NOT EXISTS app_private.billing_accounts (
    id BIGSERIAL PRIMARY KEY,
    account_id TEXT NOT NULL UNIQUE,
    stripe_customer_id TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_private.billing_subscriptions (
    id BIGSERIAL PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES app_private.billing_accounts(account_id),
    stripe_subscription_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('active','trialing','past_due','canceled','incomplete','incomplete_expired','unpaid','paused')),
    plan_code TEXT NOT NULL,
    current_period_end TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_private.billing_entitlements (
    id BIGSERIAL PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES app_private.billing_accounts(account_id),
    feature_key TEXT NOT NULL CHECK (feature_key IN ('crawler_contacts','crawler_exports','bulk_enrichment')),
    is_enabled BOOLEAN NOT NULL DEFAULT false,
    quota_monthly INT,
    used_this_period INT NOT NULL DEFAULT 0 CHECK (used_this_period >= 0),
    entitlement_version BIGINT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, feature_key)
);

CREATE TABLE IF NOT EXISTS paid_enrichment.enrichment_targets (
    id BIGSERIAL PRIMARY KEY,
    cnpj_basico CHAR(8) NOT NULL,
    cnpj_ordem CHAR(4) NOT NULL,
    cnpj_dv CHAR(2) NOT NULL,
    priority SMALLINT NOT NULL DEFAULT 50 CHECK (priority BETWEEN 0 AND 100),
    status TEXT NOT NULL CHECK (status IN ('pending','running','done','retry','blocked','error')),
    reason TEXT NOT NULL,
    attempts INT NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_run_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_at TIMESTAMPTZ,
    locked_by TEXT,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (cnpj_basico, cnpj_ordem, cnpj_dv, reason)
);

CREATE TABLE IF NOT EXISTS paid_enrichment.company_domains (
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

CREATE TABLE IF NOT EXISTS paid_enrichment.crawl_hosts (
    domain TEXT PRIMARY KEY,
    robots_status TEXT,
    robots_checked_at TIMESTAMPTZ,
    crawl_delay_seconds NUMERIC(8,2),
    max_pages_per_run INT NOT NULL DEFAULT 10 CHECK (max_pages_per_run > 0),
    consecutive_failures INT NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
    blocked_until TIMESTAMPTZ,
    last_fetch_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS paid_enrichment.crawl_requests (
    id BIGSERIAL PRIMARY KEY,
    cnpj_basico CHAR(8) NOT NULL,
    cnpj_ordem CHAR(4) NOT NULL,
    cnpj_dv CHAR(2) NOT NULL,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    source TEXT NOT NULL,
    priority SMALLINT NOT NULL DEFAULT 50 CHECK (priority BETWEEN 0 AND 100),
    status TEXT NOT NULL CHECK (status IN ('pending','running','done','retry','skipped','blocked','error')),
    depth SMALLINT NOT NULL DEFAULT 0 CHECK (depth >= 0),
    attempts INT NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_run_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    content_hash TEXT,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (cnpj_basico, cnpj_ordem, cnpj_dv, url)
);

CREATE TABLE IF NOT EXISTS paid_enrichment.crawl_pages (
    id BIGSERIAL PRIMARY KEY,
    crawl_request_id BIGINT REFERENCES paid_enrichment.crawl_requests(id),
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    http_status INT CHECK (http_status IS NULL OR (http_status >= 100 AND http_status <= 599)),
    content_type TEXT,
    content_hash TEXT NOT NULL,
    title TEXT,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    html_excerpt TEXT,
    raw_storage_key TEXT,
    UNIQUE (url, content_hash)
);

CREATE TABLE IF NOT EXISTS paid_enrichment.enrichment_evidence (
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

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'company_domains_evidence_fk'
    ) THEN
        ALTER TABLE paid_enrichment.company_domains
            ADD CONSTRAINT company_domains_evidence_fk
            FOREIGN KEY (evidence_id) REFERENCES paid_enrichment.enrichment_evidence(id)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS paid_enrichment.raw_contact_candidates (
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

CREATE TABLE IF NOT EXISTS paid_enrichment.enriched_contacts (
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

CREATE TABLE IF NOT EXISTS paid_enrichment.enrichment_access_audit (
    id BIGSERIAL PRIMARY KEY,
    account_id TEXT NOT NULL,
    request_id TEXT,
    route TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('read','export','feedback','admin')),
    cnpj_basico CHAR(8),
    cnpj_ordem CHAR(4),
    cnpj_dv CHAR(2),
    filter_hash TEXT,
    record_count INT CHECK (record_count IS NULL OR record_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE VIEW paid_enrichment.published_contacts AS
SELECT
    ec.id,
    ec.cnpj_basico,
    ec.cnpj_ordem,
    ec.cnpj_dv,
    ec.contact_type,
    ec.value,
    ec.normalized_value,
    ec.label,
    ec.source,
    ec.confidence,
    ec.evidence_id,
    ev.source_url AS evidence_url,
    ev.source_domain,
    ec.first_seen,
    ec.last_seen
FROM paid_enrichment.enriched_contacts ec
LEFT JOIN paid_enrichment.enrichment_evidence ev ON ev.id = ec.evidence_id
WHERE ec.status = 'active';

CREATE OR REPLACE VIEW app_private.active_entitlements AS
SELECT
    be.account_id,
    be.feature_key,
    be.quota_monthly,
    be.used_this_period,
    be.entitlement_version,
    bs.plan_code,
    bs.status AS subscription_status,
    bs.current_period_end
FROM app_private.billing_entitlements be
JOIN app_private.billing_subscriptions bs ON bs.account_id = be.account_id
WHERE be.is_enabled = true
  AND bs.status IN ('active','trialing')
  AND (bs.current_period_end IS NULL OR bs.current_period_end > now());

CREATE INDEX IF NOT EXISTS idx_enrichment_targets_status_next
    ON paid_enrichment.enrichment_targets (status, next_run_at, priority DESC);

CREATE INDEX IF NOT EXISTS idx_company_domains_cnpj
    ON paid_enrichment.company_domains (cnpj_basico, cnpj_ordem, cnpj_dv, confidence DESC);

CREATE INDEX IF NOT EXISTS idx_enriched_contacts_cnpj_type
    ON paid_enrichment.enriched_contacts (cnpj_basico, cnpj_ordem, cnpj_dv, contact_type, confidence DESC)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_enriched_contacts_type_value
    ON paid_enrichment.enriched_contacts (contact_type, normalized_value);

CREATE INDEX IF NOT EXISTS idx_crawl_requests_status_next
    ON paid_enrichment.crawl_requests (status, next_run_at, priority DESC);

CREATE INDEX IF NOT EXISTS idx_billing_entitlements_account_feature
    ON app_private.billing_entitlements (account_id, feature_key, is_enabled);

CREATE INDEX IF NOT EXISTS idx_enrichment_access_audit_account_created
    ON paid_enrichment.enrichment_access_audit (account_id, created_at DESC);

REVOKE ALL ON SCHEMA paid_enrichment FROM PUBLIC;
REVOKE ALL ON SCHEMA app_private FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA paid_enrichment FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA app_private FROM PUBLIC;

GRANT USAGE ON SCHEMA paid_enrichment TO api_paid, enrichment_worker;
GRANT USAGE ON SCHEMA app_private TO api_paid, billing_worker;

GRANT SELECT ON paid_enrichment.published_contacts TO api_paid;
GRANT INSERT ON paid_enrichment.enrichment_access_audit TO api_paid;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA paid_enrichment TO api_paid;

GRANT SELECT ON app_private.active_entitlements TO api_paid;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA paid_enrichment TO enrichment_worker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA paid_enrichment TO enrichment_worker;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app_private TO billing_worker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app_private TO billing_worker;
