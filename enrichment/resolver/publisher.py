"""Persistência de contatos resolvidos em `paid_enrichment.enriched_contacts`.

Usa upsert por chave natural `(cnpj, contact_type, normalized_value)` para
manter idempotência: re-rodar o crawler sobre as mesmas páginas atualiza
`last_seen` e a confiança, sem duplicar linhas. Também grava as evidências
brutas e os candidatos não publicados para auditoria.
"""
from dataclasses import dataclass
from typing import Optional

from resolution import ResolvedContact

PUBLISH_THRESHOLD = 85
ACTIVE_STATUS = "active"
CANDIDATE_STATUS = "rejected"  # mantém raw_candidates; enriched_contacts só recebe ativos

_SQL_INSERT_EVIDENCE = """
    INSERT INTO paid_enrichment.enrichment_evidence (
        cnpj_basico, cnpj_ordem, cnpj_dv, source, source_url, source_domain,
        crawl_page_id, extractor, evidence_hash, evidence_excerpt
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    RETURNING id
"""

_SQL_INSERT_RAW_CANDIDATE = """
    INSERT INTO paid_enrichment.raw_contact_candidates (
        evidence_id, contact_type, raw_value, normalized_value, label, context, confidence
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7)
"""

_SQL_HAS_SUPPRESSION = """
    SELECT 1 FROM paid_enrichment.suppression_requests
    WHERE cnpj_basico = $1 AND cnpj_ordem = $2 AND cnpj_dv = $3
      AND contact_type = $4 AND normalized_value = $5
"""

_SQL_UPSERT_ENRICHED_CONTACT = """
    INSERT INTO paid_enrichment.enriched_contacts (
        cnpj_basico, cnpj_ordem, cnpj_dv, contact_type, value, normalized_value,
        label, source, confidence, status, evidence_id, first_seen, last_seen
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, now(), now())
    ON CONFLICT (cnpj_basico, cnpj_ordem, cnpj_dv, contact_type, normalized_value)
    DO UPDATE SET
        confidence = GREATEST(EXCLUDED.confidence, paid_enrichment.enriched_contacts.confidence),
        status = CASE
            WHEN paid_enrichment.enriched_contacts.status = 'suppressed' THEN 'suppressed'
            ELSE EXCLUDED.status
        END,
        source = EXCLUDED.source,
        label = COALESCE(EXCLUDED.label, paid_enrichment.enriched_contacts.label),
        evidence_id = EXCLUDED.evidence_id,
        last_seen = now()
"""


@dataclass(frozen=True)
class PublishStats:
    evidence_written: int
    raw_candidates_written: int
    contacts_published: int


async def publish_resolved_contacts(
    conn,
    *,
    cnpj_basico: str,
    cnpj_ordem: str,
    cnpj_dv: str,
    crawl_page_id: Optional[int],
    contacts: list[ResolvedContact],
    publish_threshold: int = PUBLISH_THRESHOLD,
) -> PublishStats:
    """Persiste os contatos no DB. Aceita uma `conn` já aberta para que
    o caller decida sobre transação. Retorna estatísticas.
    """
    if not contacts:
        return PublishStats(0, 0, 0)

    evidence_written = 0
    raw_written = 0
    published = 0

    for contact in contacts:
        evidence_id = await conn.fetchval(
            _SQL_INSERT_EVIDENCE,
            cnpj_basico,
            cnpj_ordem,
            cnpj_dv,
            contact.source,
            contact.evidence_url,
            contact.source_domain,
            crawl_page_id,
            "resolver",
            f"{contact.contact_type}:{contact.normalized_value}",
            (contact.label or "")[:500],
        )
        evidence_written += 1

        await conn.execute(
            _SQL_INSERT_RAW_CANDIDATE,
            evidence_id,
            contact.contact_type,
            contact.value,
            contact.normalized_value,
            contact.label,
            contact.label,
            contact.confidence,
        )
        raw_written += 1

        if contact.confidence >= publish_threshold:
            suppressed = await conn.fetchval(
                _SQL_HAS_SUPPRESSION,
                cnpj_basico,
                cnpj_ordem,
                cnpj_dv,
                contact.contact_type,
                contact.normalized_value,
            )
            if suppressed:
                continue
            await conn.execute(
                _SQL_UPSERT_ENRICHED_CONTACT,
                cnpj_basico,
                cnpj_ordem,
                cnpj_dv,
                contact.contact_type,
                contact.value,
                contact.normalized_value,
                contact.label,
                contact.source,
                contact.confidence,
                ACTIVE_STATUS,
                evidence_id,
            )
            published += 1

    return PublishStats(
        evidence_written=evidence_written,
        raw_candidates_written=raw_written,
        contacts_published=published,
    )
