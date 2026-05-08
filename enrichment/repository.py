from api.schemas import (
    AccessAuditEvent,
    EnqueueTargetRequest,
    EnrichmentContact,
    EnrichmentDetailResponse,
    EnrichmentDomain,
    EvidenceItem,
    EvidenceResponse,
    normalize_cnpj,
    split_cnpj,
)

_SQL_ENQUEUE_TARGET = """
    INSERT INTO paid_enrichment.enrichment_targets (
        cnpj_basico, cnpj_ordem, cnpj_dv, priority, status, reason, next_run_at, updated_at
    )
    VALUES ($1, $2, $3, $4, 'pending', $5, now(), now())
    ON CONFLICT (cnpj_basico, cnpj_ordem, cnpj_dv, reason)
    DO UPDATE SET
        priority = EXCLUDED.priority,
        status = 'pending',
        next_run_at = now(),
        updated_at = now()
"""

_SQL_FETCH_DOMAINS = """
    SELECT domain, homepage_url, source, confidence, status, first_seen, last_seen
    FROM paid_enrichment.company_domains
    WHERE cnpj_basico = $1 AND cnpj_ordem = $2 AND cnpj_dv = $3
      AND status IN ('candidate', 'verified')
    ORDER BY confidence DESC, domain
"""

_SQL_FETCH_CONTACTS = """
    SELECT
        contact_type, value, normalized_value, label, source, confidence,
        evidence_url, source_domain, first_seen, last_seen
    FROM paid_enrichment.published_contacts
    WHERE cnpj_basico = $1 AND cnpj_ordem = $2 AND cnpj_dv = $3
    ORDER BY confidence DESC, contact_type, value
"""

_SQL_FETCH_EVIDENCE = """
    SELECT id, source, source_url, source_domain, extractor, evidence_excerpt, observed_at
    FROM paid_enrichment.enrichment_evidence
    WHERE cnpj_basico = $1 AND cnpj_ordem = $2 AND cnpj_dv = $3
    ORDER BY observed_at DESC, id DESC
    LIMIT $4
"""

_SQL_INSERT_AUDIT_WITH_CNPJ = """
    INSERT INTO paid_enrichment.enrichment_access_audit (
        account_id, request_id, route, action, cnpj_basico, cnpj_ordem, cnpj_dv, filter_hash, record_count
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
"""

_SQL_INSERT_AUDIT_WITHOUT_CNPJ = """
    INSERT INTO paid_enrichment.enrichment_access_audit (
        account_id, request_id, route, action, filter_hash, record_count
    )
    VALUES ($1, $2, $3, $4, $5, $6)
"""


def _rows_to_dicts(rows) -> list[dict]:
    return [dict(row) for row in rows]


async def enqueue_target(pool, cnpj: str, payload: EnqueueTargetRequest) -> str:
    normalized = normalize_cnpj(cnpj)
    cnpj_basico, cnpj_ordem, cnpj_dv = split_cnpj(normalized)
    async with pool.acquire() as conn:
        await conn.execute(
            _SQL_ENQUEUE_TARGET,
            cnpj_basico,
            cnpj_ordem,
            cnpj_dv,
            payload.priority,
            payload.reason,
        )
    return normalized


async def fetch_enrichment_detail(pool, cnpj: str) -> EnrichmentDetailResponse:
    normalized = normalize_cnpj(cnpj)
    cnpj_basico, cnpj_ordem, cnpj_dv = split_cnpj(normalized)
    async with pool.acquire() as conn:
        domain_rows = await conn.fetch(_SQL_FETCH_DOMAINS, cnpj_basico, cnpj_ordem, cnpj_dv)
        contact_rows = await conn.fetch(_SQL_FETCH_CONTACTS, cnpj_basico, cnpj_ordem, cnpj_dv)

    domains = [EnrichmentDomain(**row) for row in _rows_to_dicts(domain_rows)]
    contacts = [EnrichmentContact(**row) for row in _rows_to_dicts(contact_rows)]
    status = "done" if domains or contacts else "not_enriched"
    return EnrichmentDetailResponse(
        cnpj=normalized,
        status=status,
        domains=domains,
        contacts=contacts,
    )


async def fetch_evidence(pool, cnpj: str, *, limit: int = 100) -> EvidenceResponse:
    normalized = normalize_cnpj(cnpj)
    cnpj_basico, cnpj_ordem, cnpj_dv = split_cnpj(normalized)
    bounded_limit = max(1, min(limit, 500))
    async with pool.acquire() as conn:
        evidence_rows = await conn.fetch(
            _SQL_FETCH_EVIDENCE,
            cnpj_basico,
            cnpj_ordem,
            cnpj_dv,
            bounded_limit,
        )
    return EvidenceResponse(
        cnpj=normalized,
        items=[EvidenceItem(**row) for row in _rows_to_dicts(evidence_rows)],
    )


async def insert_access_audit(pool, event: AccessAuditEvent) -> None:
    async with pool.acquire() as conn:
        if event.cnpj:
            cnpj_basico, cnpj_ordem, cnpj_dv = split_cnpj(event.cnpj)
            await conn.execute(
                _SQL_INSERT_AUDIT_WITH_CNPJ,
                event.account_id,
                event.request_id,
                event.route,
                event.action,
                cnpj_basico,
                cnpj_ordem,
                cnpj_dv,
                event.filter_hash,
                event.record_count,
            )
            return

        await conn.execute(
            _SQL_INSERT_AUDIT_WITHOUT_CNPJ,
            event.account_id,
            event.request_id,
            event.route,
            event.action,
            event.filter_hash,
            event.record_count,
        )

