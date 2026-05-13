"""SearXNG self-hosted metasearch client.

Roteia queries por Google, Bing, DuckDuckGo simultaneamente sem API key nem quota.
Requer instância SearXNG local (docker service 'searxng') em SEARXNG_URL.

Vantagem sobre Brave/Google CSE:
  - Sem limite de requisições
  - Multi-engine simultâneo: cada query bate em 3 buscadores ao mesmo tempo
  - Gratuito e auto-hospedado
"""
from __future__ import annotations

import httpx

from discovery.brave_search import _DIRECTORY_DOMAINS
from discovery.errors import SearchRateLimitError, SearchTimeoutError, SearchUnavailableError
from discovery.search_queries import SearchQuery
from domain_discovery import DomainCandidate, normalize_domain

_MAX_RESULTS = 3
_BASE_CONFIDENCE = 55


async def search_searxng(
    query: SearchQuery,
    *,
    client: httpx.AsyncClient,
    base_url: str = "http://searxng:8080",
) -> list[DomainCandidate]:
    """Busca via SearXNG local.

    Raises:
        SearchRateLimitError: HTTP 429.
        SearchTimeoutError: request timed out.
        SearchUnavailableError: connection error, 5xx, or unparseable response.
    """
    try:
        response = await client.get(
            f"{base_url}/search",
            params={
                "q": query.text,
                "format": "json",
                "language": "pt-BR",
                "categories": "general",
                "engines": "google,bing,duckduckgo,brave",
            },
            timeout=httpx.Timeout(15.0),
        )
    except httpx.TimeoutException:
        raise SearchTimeoutError("searxng")
    except httpx.HTTPError as exc:
        raise SearchUnavailableError("searxng", 0) from exc

    if response.status_code == 429:
        raise SearchRateLimitError("searxng", retry_after=30)
    if response.status_code != 200:
        raise SearchUnavailableError("searxng", response.status_code)

    try:
        data = response.json()
    except Exception as exc:
        raise SearchUnavailableError("searxng", response.status_code) from exc

    results = data.get("results") or []
    if not results:
        return []

    confidence = min(_BASE_CONFIDENCE + query.confidence_bonus, 100)
    candidates: list[DomainCandidate] = []
    seen: set[str] = set()

    for result in results:
        url = result.get("url", "") or result.get("href", "")
        domain = normalize_domain(url)
        if not domain or domain in _DIRECTORY_DOMAINS or domain in seen:
            continue
        seen.add(domain)
        candidates.append(DomainCandidate(
            domain=domain,
            source="searxng",
            confidence=confidence,
            homepage_url=f"https://{domain}",
            reason="found via SearXNG",
        ))
        if len(candidates) >= _MAX_RESULTS:
            break

    return candidates
