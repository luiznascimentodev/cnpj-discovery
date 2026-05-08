"""Pipeline de descoberta: target → candidatos → company_domains + crawl_requests.

Lê o estabelecimento RF, gera candidatos de domínio, faz probe HTTPS para
descartar parked/dead domains e enfileira URLs prioritárias para o crawler.
Idempotente via `ON CONFLICT DO NOTHING/UPDATE` — a chamada repetida do
mesmo target não duplica linhas.
"""
from dataclasses import dataclass

import httpx

from discovery.website_probe import ProbeResult, probe_domain
from domain_discovery import DomainCandidate, discover_domain_candidates
from rf_baseline import normalize_rf_email

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
           est.cep
    FROM estabelecimentos est
    JOIN empresas e ON e.cnpj_basico = est.cnpj_basico
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

_SQL_INSERT_CRAWL_REQUEST = """
    INSERT INTO paid_enrichment.crawl_requests (
        cnpj_basico, cnpj_ordem, cnpj_dv, url, domain, source, priority, status, depth,
        next_run_at, updated_at
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending', 0, now(), now())
    ON CONFLICT (cnpj_basico, cnpj_ordem, cnpj_dv, url) DO NOTHING
"""


@dataclass(frozen=True)
class DiscoveryOutcome:
    cnpj: str
    domains_seen: int
    crawl_requests_created: int


def _initial_status(probe: ProbeResult) -> str:
    if probe.parked:
        return "rejected"
    return "candidate"


def _initial_confidence(candidate: DomainCandidate, probe: ProbeResult) -> int:
    if probe.parked:
        return min(candidate.confidence, 5)
    if not probe.ok:
        return min(candidate.confidence, 30)
    return candidate.confidence


async def process_target(
    pool,
    *,
    cnpj_basico: str,
    cnpj_ordem: str,
    cnpj_dv: str,
    client: httpx.AsyncClient,
) -> DiscoveryOutcome:
    cnpj = f"{cnpj_basico}{cnpj_ordem}{cnpj_dv}"

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            _SQL_FETCH_ESTABELECIMENTO, cnpj_basico, cnpj_ordem, cnpj_dv
        )

    if not row:
        return DiscoveryOutcome(cnpj=cnpj, domains_seen=0, crawl_requests_created=0)

    candidates = discover_domain_candidates(
        legal_name=row["razao_social"],
        trade_name=row["nome_fantasia"],
        rf_email=normalize_rf_email(row["email"]),
    )

    if not candidates:
        return DiscoveryOutcome(cnpj=cnpj, domains_seen=0, crawl_requests_created=0)

    requests_created = 0
    async with pool.acquire() as conn:
        for candidate in candidates:
            probe = await probe_domain(candidate.domain, client=client)

            homepage_url = probe.final_url if probe.ok else candidate.homepage_url
            await conn.execute(
                _SQL_UPSERT_DOMAIN,
                cnpj_basico,
                cnpj_ordem,
                cnpj_dv,
                candidate.domain,
                homepage_url,
                candidate.source,
                _initial_confidence(candidate, probe),
                _initial_status(probe),
            )

            if probe.ok and not probe.parked:
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

    return DiscoveryOutcome(
        cnpj=cnpj,
        domains_seen=len(candidates),
        crawl_requests_created=requests_created,
    )
