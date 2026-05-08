"""Paid enrichment routes protected by server-side entitlements."""
import re
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, status

from config import settings
from database import get_pool
from models.enrichment import PaidEnrichmentDetail
from services.enrichment_client import EnrichmentServiceError, fetch_paid_enrichment
from services.entitlements import has_entitlement

router = APIRouter()

_CNPJ_STRIP = re.compile(r"[.\-/\s]")


def _normalize_cnpj(cnpj: str) -> str:
    normalized = _CNPJ_STRIP.sub("", cnpj)
    if len(normalized) != 14 or not normalized.isdigit():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CNPJ deve ter 14 dígitos numéricos",
        )
    return normalized


def _require_account_id(account_id: str | None) -> str:
    if not account_id or not account_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Account-Id é obrigatório para dados pagos",
        )
    return account_id.strip()


@router.get(
    "/paid/empresa/{cnpj}/enrichment",
    response_model=PaidEnrichmentDetail,
    tags=["paid_enrichment"],
    summary="Dados pagos de enriquecimento por CNPJ",
)
async def get_paid_enrichment(
    cnpj: str,
    request: Request,
    x_account_id: Annotated[str | None, Header(alias="X-Account-Id")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> PaidEnrichmentDetail:
    normalized = _normalize_cnpj(cnpj)
    account_id = _require_account_id(x_account_id)

    pool = await get_pool()
    allowed = await has_entitlement(pool, account_id, settings.paid_contact_feature_key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Assinatura ativa necessária para acessar dados enriquecidos",
        )

    request_id = x_request_id or request.headers.get("X-Request-Id")
    try:
        return await fetch_paid_enrichment(
            normalized,
            account_id=account_id,
            request_id=request_id,
        )
    except EnrichmentServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
