from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.auth import AccountContext, require_account_context, require_internal_api_key
from api.schemas import (
    AccessAuditEvent,
    EnqueueTargetRequest,
    EnqueueTargetResponse,
    EnrichmentDetailResponse,
    EvidenceResponse,
    ServiceStatusResponse,
    normalize_cnpj,
)
from database import get_pool
from repository import (
    enqueue_target,
    fetch_enrichment_detail,
    fetch_evidence,
    insert_access_audit,
)

router = APIRouter()


def _normalize_cnpj_or_422(cnpj: str) -> str:
    try:
        return normalize_cnpj(cnpj)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get(
    "/health",
    response_model=ServiceStatusResponse,
    tags=["health"],
    summary="Health check",
)
async def health() -> ServiceStatusResponse:
    return ServiceStatusResponse(status="ok", version="0.1.0")


@router.get(
    "/status",
    response_model=ServiceStatusResponse,
    tags=["enrichment"],
    summary="Internal service status",
    dependencies=[Depends(require_internal_api_key)],
)
async def service_status() -> ServiceStatusResponse:
    return ServiceStatusResponse(status="ok", version="0.1.0")


@router.post(
    "/enrichment/{cnpj}/enqueue",
    response_model=EnqueueTargetResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["enrichment"],
    summary="Queue a CNPJ for enrichment",
    dependencies=[Depends(require_internal_api_key)],
)
async def queue_enrichment(cnpj: str, payload: EnqueueTargetRequest) -> EnqueueTargetResponse:
    normalized = _normalize_cnpj_or_422(cnpj)
    pool = await get_pool()
    queued_cnpj = await enqueue_target(pool, normalized, payload)
    return EnqueueTargetResponse(
        cnpj=queued_cnpj,
        status="queued",
        reason=payload.reason,
        priority=payload.priority,
    )


@router.get(
    "/enrichment/{cnpj}",
    response_model=EnrichmentDetailResponse,
    tags=["enrichment"],
    summary="Read paid crawler-derived enrichment for a CNPJ",
    dependencies=[Depends(require_internal_api_key)],
)
async def get_enrichment(
    cnpj: str,
    account: AccountContext = Depends(require_account_context),
) -> EnrichmentDetailResponse:
    normalized = _normalize_cnpj_or_422(cnpj)
    pool = await get_pool()
    detail = await fetch_enrichment_detail(pool, normalized)
    await insert_access_audit(
        pool,
        AccessAuditEvent(
            account_id=account.account_id,
            request_id=account.request_id,
            route="/v1/enrichment/{cnpj}",
            action="read",
            cnpj=normalized,
            record_count=len(detail.contacts),
        ),
    )
    return detail


@router.get(
    "/enrichment/{cnpj}/evidence",
    response_model=EvidenceResponse,
    tags=["enrichment"],
    summary="Read paid enrichment evidence for a CNPJ",
    dependencies=[Depends(require_internal_api_key)],
)
async def get_evidence(
    cnpj: str,
    limit: int = Query(default=100, ge=1, le=500),
    account: AccountContext = Depends(require_account_context),
) -> EvidenceResponse:
    normalized = _normalize_cnpj_or_422(cnpj)
    pool = await get_pool()
    evidence = await fetch_evidence(pool, normalized, limit=limit)
    await insert_access_audit(
        pool,
        AccessAuditEvent(
            account_id=account.account_id,
            request_id=account.request_id,
            route="/v1/enrichment/{cnpj}/evidence",
            action="read",
            cnpj=normalized,
            record_count=len(evidence.items),
        ),
    )
    return evidence

