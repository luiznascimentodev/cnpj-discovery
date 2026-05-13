from typing import Any

import httpx

from config import settings
from models.enrichment import PaidEnrichmentDetail

_TIMEOUT_SECONDS = 10.0


class EnrichmentServiceError(RuntimeError):
    pass


def _service_url(path: str) -> str:
    return f"{settings.enrichment_service_url.rstrip('/')}{path}"


def _headers(account_id: str, request_id: str | None) -> dict[str, str]:
    headers = {
        "X-Enrichment-Api-Key": settings.enrichment_api_key,
        "X-Account-Id": account_id,
    }
    if request_id:
        headers["X-Request-Id"] = request_id
    return headers


async def fetch_paid_enrichment(
    cnpj: str,
    *,
    account_id: str,
    request_id: str | None = None,
) -> PaidEnrichmentDetail:
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        response = await client.get(
            _service_url(f"/v1/enrichment/{cnpj}"),
            headers=_headers(account_id, request_id),
        )

    if response.status_code >= 500:
        raise EnrichmentServiceError("Enrichment service is unavailable")

    if response.status_code >= 400:
        raise EnrichmentServiceError("Enrichment service rejected the request")

    payload: Any = response.json()
    return PaidEnrichmentDetail.model_validate(payload)

