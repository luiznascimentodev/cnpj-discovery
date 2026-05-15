"""Paid enrichment routes protected by server-side entitlements."""
import re
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import Response

from core.config import settings
from core.db import get_pool
from modules.enrichment.schemas import PaidEnrichmentDetail
from modules.enrichment.job_schemas import (
    EnrichmentEstimateRequest,
    EnrichmentEstimateResponse,
    EnrichmentJobCancelResponse,
    EnrichmentJobCreateRequest,
    EnrichmentJobItemsResponse,
    EnrichmentJobListResponse,
    EnrichmentJobResponse,
    EnrichmentJobSummary,
)
from modules.enrichment.client import EnrichmentServiceError, fetch_paid_enrichment
from modules.enrichment.jobs import (
    cancel_enrichment_job,
    create_enrichment_job,
    estimate_enrichment_job,
    export_enrichment_job_csv,
    get_enrichment_job,
    list_enrichment_job_items,
    list_enrichment_jobs,
)
from modules.enrichment.entitlements import has_entitlement

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


async def _require_feature(pool, account_id: str, feature_key: str) -> None:
    allowed = await has_entitlement(pool, account_id, feature_key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Assinatura ativa necessária para acessar dados enriquecidos",
        )


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
    await _require_feature(pool, account_id, settings.paid_contact_feature_key)

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


@router.post(
    "/paid/enrichment/estimate",
    response_model=EnrichmentEstimateResponse,
    tags=["paid_enrichment"],
    summary="Estimar enrichment sob demanda",
)
async def estimate_paid_enrichment_job(
    payload: EnrichmentEstimateRequest,
    x_account_id: Annotated[str | None, Header(alias="X-Account-Id")] = None,
) -> EnrichmentEstimateResponse:
    account_id = _require_account_id(x_account_id)
    pool = await get_pool()
    await _require_feature(pool, account_id, "bulk_enrichment")
    return await estimate_enrichment_job(pool, payload)


@router.post(
    "/paid/enrichment/jobs",
    response_model=EnrichmentJobResponse,
    tags=["paid_enrichment"],
    summary="Criar job de enrichment sob demanda",
)
async def create_paid_enrichment_job(
    payload: EnrichmentJobCreateRequest,
    x_account_id: Annotated[str | None, Header(alias="X-Account-Id")] = None,
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> EnrichmentJobResponse:
    account_id = _require_account_id(x_account_id)
    pool = await get_pool()
    await _require_feature(pool, account_id, "bulk_enrichment")
    return await create_enrichment_job(
        pool,
        account_id=account_id,
        created_by=(x_user_id or account_id).strip(),
        payload=payload,
        idempotency_key=idempotency_key.strip() if idempotency_key else None,
    )


@router.get(
    "/paid/enrichment/jobs",
    response_model=EnrichmentJobListResponse,
    tags=["paid_enrichment"],
    summary="Listar jobs de enrichment",
)
async def list_paid_enrichment_jobs(
    x_account_id: Annotated[str | None, Header(alias="X-Account-Id")] = None,
    limit: int = 20,
) -> EnrichmentJobListResponse:
    account_id = _require_account_id(x_account_id)
    pool = await get_pool()
    await _require_feature(pool, account_id, "bulk_enrichment")
    return await list_enrichment_jobs(pool, account_id=account_id, limit=limit)


@router.get(
    "/paid/enrichment/jobs/{job_id}",
    response_model=EnrichmentJobSummary,
    tags=["paid_enrichment"],
    summary="Detalhar job de enrichment",
)
async def get_paid_enrichment_job(
    job_id: int,
    x_account_id: Annotated[str | None, Header(alias="X-Account-Id")] = None,
) -> EnrichmentJobSummary:
    account_id = _require_account_id(x_account_id)
    pool = await get_pool()
    await _require_feature(pool, account_id, "bulk_enrichment")
    job = await get_enrichment_job(pool, account_id=account_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job não encontrado")
    return job


@router.get(
    "/paid/enrichment/jobs/{job_id}/items",
    response_model=EnrichmentJobItemsResponse,
    tags=["paid_enrichment"],
    summary="Listar itens de um job de enrichment",
)
async def list_paid_enrichment_job_items(
    job_id: int,
    x_account_id: Annotated[str | None, Header(alias="X-Account-Id")] = None,
    limit: int = 100,
    offset: int = 0,
) -> EnrichmentJobItemsResponse:
    account_id = _require_account_id(x_account_id)
    pool = await get_pool()
    await _require_feature(pool, account_id, "bulk_enrichment")
    return await list_enrichment_job_items(
        pool,
        account_id=account_id,
        job_id=job_id,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/paid/enrichment/jobs/{job_id}/cancel",
    response_model=EnrichmentJobCancelResponse,
    tags=["paid_enrichment"],
    summary="Cancelar job de enrichment",
)
async def cancel_paid_enrichment_job(
    job_id: int,
    x_account_id: Annotated[str | None, Header(alias="X-Account-Id")] = None,
) -> EnrichmentJobCancelResponse:
    account_id = _require_account_id(x_account_id)
    pool = await get_pool()
    await _require_feature(pool, account_id, "bulk_enrichment")
    cancelled = await cancel_enrichment_job(pool, account_id=account_id, job_id=job_id)
    return EnrichmentJobCancelResponse(job_id=job_id, cancelled_items=cancelled)


@router.get(
    "/paid/enrichment/jobs/{job_id}/export.csv",
    tags=["paid_enrichment"],
    summary="Exportar resultado parcial de enrichment",
)
async def export_paid_enrichment_job(
    job_id: int,
    x_account_id: Annotated[str | None, Header(alias="X-Account-Id")] = None,
) -> Response:
    account_id = _require_account_id(x_account_id)
    pool = await get_pool()
    await _require_feature(pool, account_id, "crawler_exports")
    csv_body = await export_enrichment_job_csv(pool, account_id=account_id, job_id=job_id)
    return Response(
        content=csv_body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="enrichment-job-{job_id}.csv"'},
    )
