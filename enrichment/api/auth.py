import secrets
from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException, status

from config import settings

INTERNAL_API_KEY_HEADER = "X-Enrichment-Api-Key"
ACCOUNT_ID_HEADER = "X-Account-Id"
REQUEST_ID_HEADER = "X-Request-Id"


@dataclass(frozen=True)
class AuthenticatedService:
    name: str = "cnpj-discovery-api"


@dataclass(frozen=True)
class AccountContext:
    account_id: str
    request_id: str | None = None


def is_valid_internal_api_key(provided_key: str | None, expected_key: str) -> bool:
    return bool(provided_key) and bool(expected_key) and secrets.compare_digest(
        provided_key,
        expected_key,
    )


async def require_internal_api_key(
    x_enrichment_api_key: Annotated[str | None, Header(alias=INTERNAL_API_KEY_HEADER)] = None,
) -> AuthenticatedService:
    try:
        settings.validate_runtime_security()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    if not is_valid_internal_api_key(x_enrichment_api_key, settings.enrichment_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid enrichment service credentials",
        )
    return AuthenticatedService()


async def require_account_context(
    x_account_id: Annotated[str | None, Header(alias=ACCOUNT_ID_HEADER)] = None,
    x_request_id: Annotated[str | None, Header(alias=REQUEST_ID_HEADER)] = None,
) -> AccountContext:
    if not x_account_id or not x_account_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Account-Id is required for paid enrichment reads",
        )
    return AccountContext(account_id=x_account_id.strip(), request_id=x_request_id)

