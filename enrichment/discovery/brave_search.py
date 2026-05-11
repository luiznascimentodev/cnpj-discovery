"""Cliente Brave Search para descoberta de domínio.

search_company_domain — API legada: query simples por nome (mantida por compatibilidade).
search_with_queries   — API nova: recebe lista priorizada de SearchQuery, tenta cada
                        uma até obter candidatos não-diretório, aplicando confidence_bonus.
"""
from __future__ import annotations

import httpx

from discovery.search_queries import SearchQuery
from domain_discovery import DomainCandidate, normalize_domain

_DIRECTORY_DOMAINS = frozenset({
    "receita.fazenda.gov.br",
    "cnpj.info",
    "cnpj.biz",
    "qsa.net.br",
    "jusbrasil.com.br",
    "reclameaqui.com.br",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "tiktok.com",
    "empresas.net.br",
    "infocnpj.com",
    "maps.google.com",
    "google.com",
    "cnpja.com.br",
    "cnpjbrasil.com.br",
    "econodata.com.br",
    "empresasdobrasil.com.br",
})

_BASE_CONFIDENCE = 55
_MAX_RESULTS = 3


def _parse_results(
    data: dict,
    confidence: int,
    *,
    seen: set[str],
) -> list[DomainCandidate]:
    try:
        results = data["web"]["results"]
    except (KeyError, TypeError):
        return []

    candidates: list[DomainCandidate] = []
    for result in results[:_MAX_RESULTS + len(_DIRECTORY_DOMAINS)]:
        domain = normalize_domain(result.get("url", ""))
        if not domain or domain in _DIRECTORY_DOMAINS or domain in seen:
            continue
        seen.add(domain)
        candidates.append(DomainCandidate(
            domain=domain,
            source="brave_search",
            confidence=min(confidence, 100),
            homepage_url=f"https://{domain}",
            reason="found via web search",
        ))
        if len(candidates) >= _MAX_RESULTS:
            break
    return candidates


async def _execute_query(
    query_text: str,
    *,
    client: httpx.AsyncClient,
    api_key: str,
    base_url: str,
    confidence: int,
    seen: set[str],
) -> list[DomainCandidate]:
    try:
        response = await client.get(
            f"{base_url}/res/v1/web/search",
            params={"q": query_text, "count": 5, "country": "BR"},
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
            timeout=httpx.Timeout(10.0),
        )
    except httpx.HTTPError:
        return []

    if response.status_code != 200:
        return []

    try:
        data = response.json()
    except (ValueError, Exception):
        return []

    return _parse_results(data, confidence, seen=seen)


async def search_with_queries(
    queries: list[SearchQuery],
    *,
    client: httpx.AsyncClient,
    api_key: str,
    base_url: str = "https://api.search.brave.com",
) -> list[DomainCandidate]:
    """Tenta cada SearchQuery em ordem até obter candidatos não-diretório.

    O confidence_bonus da query é somado ao _BASE_CONFIDENCE (55), limitado a 100.
    Retorna os candidatos da primeira query com resultados válidos.
    """
    seen: set[str] = set()
    for query in queries:
        confidence = min(_BASE_CONFIDENCE + query.confidence_bonus, 100)
        candidates = await _execute_query(
            query.text,
            client=client,
            api_key=api_key,
            base_url=base_url,
            confidence=confidence,
            seen=seen,
        )
        if candidates:
            return candidates
    return []


async def search_company_domain(
    company_name: str,
    city: str | None,
    *,
    client: httpx.AsyncClient,
    api_key: str,
    base_url: str = "https://api.search.brave.com",
) -> list[DomainCandidate]:
    """API legada — mantida para compatibilidade. Use search_with_queries."""
    query = f'"{company_name}"'
    if city:
        query += f" {city}"
    query += " site oficial"
    seen: set[str] = set()
    return await _execute_query(
        query,
        client=client,
        api_key=api_key,
        base_url=base_url,
        confidence=_BASE_CONFIDENCE,
        seen=seen,
    )
