"""Cliente Google Custom Search Engine para descoberta de domínio.

Requer GOOGLE_CSE_API_KEY e GOOGLE_CSE_CX configurados.
Free tier: 100 queries/dia. Retorna [] em qualquer erro.
"""
from __future__ import annotations

import httpx

from discovery.brave_search import _DIRECTORY_DOMAINS
from discovery.errors import SearchRateLimitError, SearchTimeoutError, SearchUnavailableError
from discovery.search_queries import SearchQuery
from domain_discovery import DomainCandidate, normalize_domain

_BASE_CONFIDENCE = 55
_MAX_RESULTS = 3


async def search_google_cse(
    query: SearchQuery,
    *,
    client: httpx.AsyncClient,
    api_key: str,
    cx: str,
    base_url: str = "https://www.googleapis.com/customsearch/v1",
) -> list[DomainCandidate]:
    """Busca um único SearchQuery via Google CSE. Retorna [] em qualquer erro."""
    try:
        response = await client.get(
            base_url,
            params={
                "key": api_key,
                "cx": cx,
                "q": query.text,
                "num": 5,
                "gl": "br",
                "lr": "lang_pt",
            },
            timeout=httpx.Timeout(10.0),
        )
    except httpx.TimeoutException:
        raise SearchTimeoutError("google_cse")
    except httpx.HTTPError as exc:
        raise SearchUnavailableError("google_cse", 0) from exc

    if response.status_code == 429:
        raise SearchRateLimitError("google_cse", retry_after=3600)
    if response.status_code != 200:
        raise SearchUnavailableError("google_cse", response.status_code)

    try:
        data = response.json()
    except Exception as exc:
        raise SearchUnavailableError("google_cse", response.status_code) from exc

    items = data.get("items") or []
    if not items:
        return []

    confidence = min(_BASE_CONFIDENCE + query.confidence_bonus, 100)
    candidates: list[DomainCandidate] = []
    seen: set[str] = set()

    for item in items:
        domain = normalize_domain(item.get("link", ""))
        if not domain or domain in _DIRECTORY_DOMAINS or domain in seen:
            continue
        seen.add(domain)
        candidates.append(DomainCandidate(
            domain=domain,
            source="google_cse",
            confidence=confidence,
            homepage_url=f"https://{domain}",
            reason="found via Google CSE",
        ))
        if len(candidates) >= _MAX_RESULTS:
            break

    return candidates
