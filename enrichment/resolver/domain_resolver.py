"""Domain contact resolver.

Maps `domain_contact_candidates` to company CNPJs via verified `company_domains`
and publishes qualified contacts to `enriched_contacts`.

Key rules:
- Only publish from domains with company_domains.status = 'verified'.
- Shared domain guard: when multiple CNPJs share a domain, only publish if the
  domain is specific to exactly one CNPJ (shared_cnpj_count == 1). For shared
  domains, candidates remain as raw evidence only.
- Contact is not suppressed.
- Confidence >= PUBLISH_THRESHOLD.
- Re-running after scoring rule changes does not recrawl — it only re-resolves.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from loguru import logger

PUBLISH_THRESHOLD = 70
SHARED_DOMAIN_MAX_CNPJS = 1  # only publish when domain belongs to exactly 1 CNPJ

_SQL_GET_VERIFIED_DOMAINS_WITH_CANDIDATES = """
    SELECT DISTINCT dcc.domain
    FROM paid_enrichment.domain_contact_candidates dcc
    JOIN paid_enrichment.company_domains cd
        ON cd.domain = dcc.domain
       AND cd.status = 'verified'
    WHERE dcc.id > $1
    ORDER BY dcc.domain
    LIMIT $2
"""

_SQL_COUNT_CNPJS_FOR_DOMAIN = """
    SELECT count(DISTINCT (cnpj_basico, cnpj_ordem, cnpj_dv))
    FROM paid_enrichment.company_domains
    WHERE domain = $1 AND status = 'verified'
"""

_SQL_GET_CNPJS_FOR_DOMAIN = """
    SELECT cnpj_basico, cnpj_ordem, cnpj_dv
    FROM paid_enrichment.company_domains
    WHERE domain = $1 AND status = 'verified'
    ORDER BY cnpj_basico, cnpj_ordem, cnpj_dv
"""

_SQL_GET_CANDIDATES_FOR_DOMAIN = """
    SELECT
        dcc.id,
        dcc.contact_type,
        dcc.raw_value,
        dcc.normalized_value,
        dcc.label,
        dcc.context,
        dcc.confidence,
        dcc.domain_page_id
    FROM paid_enrichment.domain_contact_candidates dcc
    JOIN paid_enrichment.domain_pages dp ON dp.id = dcc.domain_page_id
    WHERE dcc.domain = $1
      AND dcc.normalized_value IS NOT NULL
      AND dcc.confidence >= $2
    ORDER BY dcc.confidence DESC, dcc.id
"""

_SQL_HAS_SUPPRESSION = """
    SELECT 1 FROM paid_enrichment.suppression_requests
    WHERE cnpj_basico = $1 AND cnpj_ordem = $2 AND cnpj_dv = $3
      AND contact_type = $4 AND normalized_value = $5
"""

_SQL_UPSERT_ENRICHED_CONTACT = """
    INSERT INTO paid_enrichment.enriched_contacts (
        cnpj_basico, cnpj_ordem, cnpj_dv, contact_type, value, normalized_value,
        label, source, confidence, status, first_seen, last_seen
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'active', now(), now())
    ON CONFLICT (cnpj_basico, cnpj_ordem, cnpj_dv, contact_type, normalized_value)
    DO UPDATE SET
        confidence = GREATEST(EXCLUDED.confidence,
                               paid_enrichment.enriched_contacts.confidence),
        status = CASE
            WHEN paid_enrichment.enriched_contacts.status = 'suppressed' THEN 'suppressed'
            ELSE 'active'
        END,
        source  = EXCLUDED.source,
        label   = COALESCE(EXCLUDED.label, paid_enrichment.enriched_contacts.label),
        last_seen = now()
    RETURNING id, (xmax = 0) AS inserted
"""


@dataclass(frozen=True)
class ResolveStats:
    domains_processed: int = 0
    domains_shared_skipped: int = 0
    contacts_evaluated: int = 0
    contacts_published: int = 0
    contacts_suppressed: int = 0
    contacts_below_threshold: int = 0


async def _resolve_domain(
    conn,
    domain: str,
    *,
    publish_threshold: int,
) -> tuple[int, int, int, int]:
    """Resolve candidates for one domain. Returns (published, suppressed, below_threshold, shared_skip).

    Returns (0,0,0,1) when domain is shared by multiple CNPJs.
    """
    cnpj_count = await conn.fetchval(_SQL_COUNT_CNPJS_FOR_DOMAIN, domain)
    if (cnpj_count or 0) > SHARED_DOMAIN_MAX_CNPJS:
        logger.info(
            "domain_resolver_shared_skip domain={} cnpj_count={}",
            domain, cnpj_count,
        )
        return 0, 0, 0, 1

    cnpjs = await conn.fetch(_SQL_GET_CNPJS_FOR_DOMAIN, domain)
    if not cnpjs:
        return 0, 0, 0, 0

    candidates = await conn.fetch(_SQL_GET_CANDIDATES_FOR_DOMAIN, domain, 0)
    if not candidates:
        return 0, 0, 0, 0

    published = suppressed = below = 0

    for cnpj in cnpjs:
        basico, ordem, dv = cnpj["cnpj_basico"], cnpj["cnpj_ordem"], cnpj["cnpj_dv"]
        for cand in candidates:
            if cand["confidence"] < publish_threshold:
                below += 1
                continue

            is_suppressed = await conn.fetchval(
                _SQL_HAS_SUPPRESSION,
                basico, ordem, dv,
                cand["contact_type"],
                cand["normalized_value"],
            )
            if is_suppressed:
                suppressed += 1
                continue

            await conn.execute(
                _SQL_UPSERT_ENRICHED_CONTACT,
                basico, ordem, dv,
                cand["contact_type"],
                cand["raw_value"],
                cand["normalized_value"],
                cand["label"],
                f"domain_crawler:{domain}",
                cand["confidence"],
            )
            published += 1

    logger.info(
        "domain_resolver_done domain={} cnpjs={} candidates={} published={} suppressed={} below={}",
        domain, len(cnpjs), len(candidates), published, suppressed, below,
    )
    return published, suppressed, below, 0


async def resolve_domain_contacts(
    pool,
    *,
    batch_size: int = 1000,
    cursor_id: int = 0,
    publish_threshold: int = PUBLISH_THRESHOLD,
) -> ResolveStats:
    """Process one batch of domains with pending candidates. Returns stats."""
    async with pool.acquire() as conn:
        domains = await conn.fetch(
            _SQL_GET_VERIFIED_DOMAINS_WITH_CANDIDATES,
            cursor_id,
            batch_size,
        )

    if not domains:
        return ResolveStats()

    total_published = total_suppressed = total_below = total_shared = domains_processed = 0

    for row in domains:
        domain = row["domain"]
        async with pool.acquire() as conn:
            pub, supp, below, shared = await _resolve_domain(
                conn, domain, publish_threshold=publish_threshold
            )
        total_published += pub
        total_suppressed += supp
        total_below += below
        total_shared += shared
        domains_processed += 1

    stats = ResolveStats(
        domains_processed=domains_processed,
        domains_shared_skipped=total_shared,
        contacts_evaluated=total_published + total_suppressed + total_below,
        contacts_published=total_published,
        contacts_suppressed=total_suppressed,
        contacts_below_threshold=total_below,
    )
    logger.info(
        "resolve_batch_done domains={} shared_skip={} published={} suppressed={} below={}",
        stats.domains_processed,
        stats.domains_shared_skipped,
        stats.contacts_published,
        stats.contacts_suppressed,
        stats.contacts_below_threshold,
    )
    return stats
