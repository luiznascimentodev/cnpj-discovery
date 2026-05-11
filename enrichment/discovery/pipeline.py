"""Pipeline de descoberta: target → candidatos → company_domains + crawl_requests.

Lê o estabelecimento RF, gera candidatos de domínio, faz probe HTTPS para
descartar parked/dead domains e enfileira URLs prioritárias para o crawler.
Idempotente via `ON CONFLICT DO NOTHING/UPDATE` — a chamada repetida do
mesmo target não duplica linhas.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from discovery.website_probe import ProbeResult, dns_exists, probe_domain
from domain_discovery import DomainCandidate, discover_domain_candidates
from resolver.domain_verifier import DomainScoreResult, score_domain_evidence
from rf_baseline import normalize_rf_email, normalize_rf_phone

if TYPE_CHECKING:  # pragma: no cover
    from discovery.external_search import ExternalSearchClient

PRIORITY_PATHS = (
    "/",
    "/contato",
    "/contact",
    "/sobre",
    "/about",
    "/empresa",
    "/atendimento",
    "/institucional",
)

_SQL_FETCH_ESTABELECIMENTO = """
    SELECT e.razao_social,
           est.nome_fantasia,
           est.email,
           est.uf,
           est.municipio,
           m.descricao AS municipio_descricao,
           est.cep,
           est.ddd1,
           est.telefone1,
           est.ddd2,
           est.telefone2,
           est.bairro,
           est.logradouro,
           est.numero,
           c.descricao AS cnae_descricao
    FROM estabelecimentos est
    JOIN empresas e ON e.cnpj_basico = est.cnpj_basico
    LEFT JOIN municipios m ON m.codigo = est.municipio
    LEFT JOIN cnaes c ON c.codigo = est.cnae_principal
    WHERE est.cnpj_basico = $1 AND est.cnpj_ordem = $2 AND est.cnpj_dv = $3
"""

_SQL_UPSERT_DOMAIN = """
    INSERT INTO paid_enrichment.company_domains (
        cnpj_basico, cnpj_ordem, cnpj_dv, domain, homepage_url, source, confidence, status,
        first_seen, last_seen
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now(), now())
    ON CONFLICT (cnpj_basico, cnpj_ordem, cnpj_dv, domain) DO UPDATE SET
        homepage_url = EXCLUDED.homepage_url,
        source = EXCLUDED.source,
        confidence = GREATEST(EXCLUDED.confidence, paid_enrichment.company_domains.confidence),
        status = CASE
            WHEN paid_enrichment.company_domains.status = 'verified' THEN 'verified'
            ELSE EXCLUDED.status
        END,
        last_seen = now()
"""

_SQL_UPSERT_RF_EMAIL_CONTACT = """
    INSERT INTO paid_enrichment.enriched_contacts (
        cnpj_basico, cnpj_ordem, cnpj_dv, contact_type, value, normalized_value,
        label, source, confidence, status, first_seen, last_seen
    )
    VALUES ($1, $2, $3, 'email', $4, $4, 'Email RF', 'rf_email_direct', 40, 'active', now(), now())
    ON CONFLICT (cnpj_basico, cnpj_ordem, cnpj_dv, contact_type, normalized_value)
    DO UPDATE SET last_seen = now()
"""

_SQL_UPSERT_RF_EMAIL_CONTACT_MEI = """
    INSERT INTO paid_enrichment.enriched_contacts (
        cnpj_basico, cnpj_ordem, cnpj_dv, contact_type, value, normalized_value,
        label, source, confidence, status, first_seen, last_seen
    )
    VALUES ($1, $2, $3, 'email', $4, $4, 'Email MEI', 'rf_email_mei', 65, 'active', now(), now())
    ON CONFLICT (cnpj_basico, cnpj_ordem, cnpj_dv, contact_type, normalized_value)
    DO UPDATE SET last_seen = now()
"""

_SQL_UPSERT_RF_PHONE_CONTACT = """
    INSERT INTO paid_enrichment.enriched_contacts (
        cnpj_basico, cnpj_ordem, cnpj_dv, contact_type, value, normalized_value,
        label, source, confidence, status, first_seen, last_seen
    )
    VALUES ($1, $2, $3, 'phone', $4, $5, $6, $7, $8, 'active', now(), now())
    ON CONFLICT (cnpj_basico, cnpj_ordem, cnpj_dv, contact_type, normalized_value)
    DO UPDATE SET last_seen = now()
"""

_SQL_HAS_VERIFIED_DOMAIN = """
    SELECT 1 FROM paid_enrichment.company_domains
    WHERE cnpj_basico = $1 AND cnpj_ordem = $2 AND cnpj_dv = $3 AND status = 'verified'
    LIMIT 1
"""

_SQL_INSERT_CRAWL_REQUEST = """
    INSERT INTO paid_enrichment.crawl_requests (
        cnpj_basico, cnpj_ordem, cnpj_dv, url, domain, source, priority, status, depth,
        next_run_at, updated_at
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending', 0, now(), now())
    ON CONFLICT (cnpj_basico, cnpj_ordem, cnpj_dv, url) DO NOTHING
"""

_SQL_FETCH_SOCIOS = """
    SELECT nome_socio
    FROM socios
    WHERE cnpj_basico = $1
    ORDER BY data_entrada DESC NULLS LAST
    LIMIT 5
"""

_SQL_FETCH_MATRIX_DOMAIN = """
    SELECT domain, homepage_url, confidence
    FROM paid_enrichment.company_domains
    WHERE cnpj_basico = $1 AND cnpj_ordem = '0001' AND status = 'verified'
    ORDER BY confidence DESC
    LIMIT 1
"""

_SQL_IS_MEI = """
    SELECT opcao_mei FROM simples WHERE cnpj_basico = $1
"""


@dataclass(frozen=True)
class DiscoveryOutcome:
    cnpj: str
    domains_seen: int
    crawl_requests_created: int
    rf_contacts_saved: int = 0


def _initial_status(probe: ProbeResult, score: DomainScoreResult | None = None) -> str:
    if probe.parked:
        return "rejected"
    if score is not None:
        return score.status
    return "candidate"


def _initial_confidence(
    candidate: DomainCandidate,
    probe: ProbeResult,
    score: DomainScoreResult | None = None,
) -> int:
    if probe.parked:
        return min(candidate.confidence, 5)
    if not probe.ok:
        return min(candidate.confidence, 30)
    if score is not None:
        return score.score
    return candidate.confidence


def _rf_email_domain(email) -> str | None:
    if not email or email.classification != "corporate_domain":
        return None
    return email.normalized_value.rsplit("@", 1)[1]


def _strong_identity_signals(score: DomainScoreResult) -> bool:
    return any(
        signal in score.signals
        for signal in {
            "cnpj_exact",
            "legal_exact",
            "legal_all_tokens",
            "fantasy_exact",
            "fantasy_all_tokens",
            "rf_phone_match",
        }
    )


def _should_enqueue_crawl(score: DomainScoreResult) -> bool:
    if score.status == "verified":
        return True
    return score.score >= 60 and _strong_identity_signals(score)


def _row_value(row, key: str):
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return None


async def _upsert_matrix_domain(
    pool, cnpj_basico: str, cnpj_ordem: str, cnpj_dv: str, matrix_row
) -> None:
    """Copies verified domain from parent company to branch."""
    async with pool.acquire() as conn:
        await conn.execute(
            _SQL_UPSERT_DOMAIN,
            cnpj_basico,
            cnpj_ordem,
            cnpj_dv,
            matrix_row["domain"],
            matrix_row["homepage_url"],
            "matrix_resolution",
            matrix_row["confidence"],
            "verified",
        )


async def process_target(
    pool,
    *,
    cnpj_basico: str,
    cnpj_ordem: str,
    cnpj_dv: str,
    client: httpx.AsyncClient,
    external_search: ExternalSearchClient | None = None,
    dns_only: bool = False,
) -> DiscoveryOutcome:
    cnpj = f"{cnpj_basico}{cnpj_ordem}{cnpj_dv}"

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            _SQL_FETCH_ESTABELECIMENTO, cnpj_basico, cnpj_ordem, cnpj_dv
        )

    if not row:
        return DiscoveryOutcome(cnpj=cnpj, domains_seen=0, crawl_requests_created=0)

    async with pool.acquire() as conn:
        socios_rows = await conn.fetch(_SQL_FETCH_SOCIOS, cnpj_basico)
    partner_names = [row["nome_socio"] for row in socios_rows if row["nome_socio"]]

    rf_email = normalize_rf_email(_row_value(row, "email"))
    rf_phone1 = normalize_rf_phone(_row_value(row, "ddd1"), _row_value(row, "telefone1"))
    rf_phone2 = normalize_rf_phone(_row_value(row, "ddd2"), _row_value(row, "telefone2"))
    rf_phone = rf_phone1 or rf_phone2

    # MEI companies (simples.opcao_mei='S') skip brand_slug — social search only
    async with pool.acquire() as conn:
        simples_row = await conn.fetchrow(_SQL_IS_MEI, cnpj_basico)
    is_mei = bool(simples_row and simples_row.get("opcao_mei") == "S")

    rf_contacts_saved = 0
    if not is_mei and rf_email and rf_email.classification == "public_provider":
        async with pool.acquire() as conn:
            await conn.execute(
                _SQL_UPSERT_RF_EMAIL_CONTACT,
                cnpj_basico, cnpj_ordem, cnpj_dv,
                rf_email.normalized_value,
            )
        rf_contacts_saved = 1

    # Branches inherit domain from parent company when available
    if cnpj_ordem != "0001":
        async with pool.acquire() as conn:
            matrix_row = await conn.fetchrow(
                _SQL_FETCH_MATRIX_DOMAIN, cnpj_basico
            )
        if matrix_row:
            await _upsert_matrix_domain(
                pool, cnpj_basico, cnpj_ordem, cnpj_dv, matrix_row
            )
            return DiscoveryOutcome(
                cnpj=cnpj,
                domains_seen=1,
                crawl_requests_created=0,
                rf_contacts_saved=rf_contacts_saved,
            )

    requests_created = 0
    candidates: list[DomainCandidate] = []

    if is_mei:
        async with pool.acquire() as conn:
            if rf_email and rf_email.classification in ("public_provider", "corporate_domain"):
                await conn.execute(
                    _SQL_UPSERT_RF_EMAIL_CONTACT_MEI,
                    cnpj_basico, cnpj_ordem, cnpj_dv,
                    rf_email.normalized_value,
                )
                rf_contacts_saved += 1
            if rf_phone1:
                await conn.execute(
                    _SQL_UPSERT_RF_PHONE_CONTACT,
                    cnpj_basico, cnpj_ordem, cnpj_dv,
                    rf_phone1.value, rf_phone1.normalized_value,
                    "Telefone MEI", "rf_phone_mei", 75,
                )
                rf_contacts_saved += 1
            if rf_phone2 and rf_phone2.normalized_value != (rf_phone1.normalized_value if rf_phone1 else None):
                await conn.execute(
                    _SQL_UPSERT_RF_PHONE_CONTACT,
                    cnpj_basico, cnpj_ordem, cnpj_dv,
                    rf_phone2.value, rf_phone2.normalized_value,
                    "Telefone MEI 2", "rf_phone_mei", 70,
                )
                rf_contacts_saved += 1
        if dns_only:
            return DiscoveryOutcome(
                cnpj=cnpj, domains_seen=0, crawl_requests_created=0,
                rf_contacts_saved=rf_contacts_saved,
            )
        candidates = []
    else:
        candidates = discover_domain_candidates(
            legal_name=_row_value(row, "razao_social"),
            trade_name=_row_value(row, "nome_fantasia"),
            rf_email=rf_email,
        )

        if not candidates:
            return DiscoveryOutcome(
                cnpj=cnpj, domains_seen=0, crawl_requests_created=0,
                rf_contacts_saved=rf_contacts_saved,
            )

    if candidates:
        async with pool.acquire() as conn:
            for candidate in candidates:
                # DNS pre-check: brand_slug domains are 98% non-existent — skip HTTP if DNS fails
                if candidate.source == "brand_slug" and not await dns_exists(candidate.domain):
                    await conn.execute(
                        _SQL_UPSERT_DOMAIN,
                        cnpj_basico, cnpj_ordem, cnpj_dv,
                        candidate.domain, f"https://{candidate.domain}/",
                        candidate.source, 5, "rejected",
                    )
                    continue
                probe = await probe_domain(candidate.domain, client=client)
                score = score_domain_evidence(
                    probe.body,
                    domain=candidate.domain,
                    cnpj=cnpj,
                    legal_name=_row_value(row, "razao_social"),
                    fantasy_name=_row_value(row, "nome_fantasia"),
                    rf_email_domain=_rf_email_domain(rf_email),
                    rf_phone_normalized=rf_phone.normalized_value if rf_phone else None,
                    cep=_row_value(row, "cep"),
                    city=_row_value(row, "municipio_descricao"),
                    uf=_row_value(row, "uf"),
                    bairro=_row_value(row, "bairro"),
                    logradouro=_row_value(row, "logradouro"),
                    numero=_row_value(row, "numero"),
                    cnae_description=_row_value(row, "cnae_descricao"),
                    partner_names=partner_names,
                    is_parked=probe.parked,
                )

                homepage_url = probe.final_url if probe.ok else candidate.homepage_url
                await conn.execute(
                    _SQL_UPSERT_DOMAIN,
                    cnpj_basico,
                    cnpj_ordem,
                    cnpj_dv,
                    candidate.domain,
                    homepage_url,
                    candidate.source,
                    _initial_confidence(candidate, probe, score),
                    _initial_status(probe, score),
                )

                if probe.ok and not probe.parked and _should_enqueue_crawl(score):
                    for path in PRIORITY_PATHS:
                        url = f"https://{candidate.domain}{path}"
                        await conn.execute(
                            _SQL_INSERT_CRAWL_REQUEST,
                            cnpj_basico,
                            cnpj_ordem,
                            cnpj_dv,
                            url,
                            candidate.domain,
                            candidate.source,
                            candidate.confidence,
                        )
                        requests_created += 1

    if external_search is not None and not dns_only:
        async with pool.acquire() as conn:
            already_verified = await conn.fetchval(
                _SQL_HAS_VERIFIED_DOMAIN, cnpj_basico, cnpj_ordem, cnpj_dv
            )
        if not already_verified:
            extra_candidates = await external_search.enrich_candidates(
                cnpj14=cnpj,
                legal_name=_row_value(row, "razao_social"),
                trade_name=_row_value(row, "nome_fantasia"),
                city=_row_value(row, "municipio_descricao"),
                partner_names=partner_names,
                client=client,
            )
            async with pool.acquire() as conn:
                for candidate in extra_candidates:
                    probe = await probe_domain(candidate.domain, client=client)
                    score = score_domain_evidence(
                        probe.body,
                        domain=candidate.domain,
                        cnpj=cnpj,
                        legal_name=_row_value(row, "razao_social"),
                        fantasy_name=_row_value(row, "nome_fantasia"),
                        rf_email_domain=_rf_email_domain(rf_email),
                        rf_phone_normalized=rf_phone.normalized_value if rf_phone else None,
                        cep=_row_value(row, "cep"),
                        city=_row_value(row, "municipio_descricao"),
                        uf=_row_value(row, "uf"),
                        bairro=_row_value(row, "bairro"),
                        logradouro=_row_value(row, "logradouro"),
                        numero=_row_value(row, "numero"),
                        cnae_description=_row_value(row, "cnae_descricao"),
                        partner_names=partner_names,
                        is_parked=probe.parked,
                    )
                    homepage_url = probe.final_url if probe.ok else candidate.homepage_url
                    await conn.execute(
                        _SQL_UPSERT_DOMAIN,
                        cnpj_basico, cnpj_ordem, cnpj_dv,
                        candidate.domain, homepage_url,
                        candidate.source,
                        _initial_confidence(candidate, probe, score),
                        _initial_status(probe, score),
                    )
                    if probe.ok and not probe.parked and _should_enqueue_crawl(score):
                        for path in PRIORITY_PATHS:
                            url = f"https://{candidate.domain}{path}"
                            await conn.execute(
                                _SQL_INSERT_CRAWL_REQUEST,
                                cnpj_basico, cnpj_ordem, cnpj_dv,
                                url, candidate.domain,
                                candidate.source, candidate.confidence,
                            )
                            requests_created += 1

    return DiscoveryOutcome(
        cnpj=cnpj,
        domains_seen=len(candidates),
        crawl_requests_created=requests_created,
        rf_contacts_saved=rf_contacts_saved,
    )
