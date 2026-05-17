"""Router for pipeline card endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from core.cache import get_redis
from core.csrf import csrf_dependency
from core.middleware.auth import get_current_user
from core.rate_limit import RateLimiter
from modules.auth.schemas import UserRecord
from modules.pipeline.cards.csv_import import ImportResult, import_cards
from modules.pipeline.cards.repository import CardRepository
from modules.pipeline.cards.schemas import (
    CardCreate,
    CardInPipelineSummary,
    CardMove,
    CardPatch,
    CardRecord,
    CardWithCompany,
    ImportRowRecord,
)
from modules.pipeline.cards.service import (
    cards_by_cnpj,
    create_card,
    delete_card,
    list_cards,
    move_card,
    update_card,
)
from modules.pipeline.dependencies import get_card_repo, owned_card, owned_pipeline
from modules.pipeline.pipelines.schemas import PipelineRecord

router = APIRouter(tags=["pipeline_cards"])


async def _limit(request: Request, key: str, *, window: int, max_count: int) -> None:
    redis = get_redis()
    result = await RateLimiter(
        redis,
        bucket_key=f"rate:{key}",
        window=window,
        max_count=max_count,
    ).try_acquire()
    if not result.ok:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas. Tente novamente mais tarde.",
            headers={"Retry-After": str(result.retry_after)},
        )


@router.get("/pipelines/cards/by-cnpj/{cnpj_basico}", response_model=list[CardInPipelineSummary])
async def cards_by_cnpj_endpoint(
    cnpj_basico: str,
    user: UserRecord = Depends(get_current_user),
    repo: CardRepository = Depends(get_card_repo),
) -> list[CardInPipelineSummary]:
    return await cards_by_cnpj(repo, owner_user_id=user.id, cnpj_basico=cnpj_basico)


@router.get("/pipelines/{pipeline_id}/cards", response_model=list[CardWithCompany])
async def list_cards_endpoint(
    pipeline: PipelineRecord = Depends(owned_pipeline),
    repo: CardRepository = Depends(get_card_repo),
) -> list[CardWithCompany]:
    return await list_cards(repo, pipeline.id)


@router.post(
    "/pipelines/{pipeline_id}/cards",
    response_model=CardRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(csrf_dependency)],
)
async def create_card_endpoint(
    payload: CardCreate,
    request: Request,
    user: UserRecord = Depends(get_current_user),
    pipeline: PipelineRecord = Depends(owned_pipeline),
    repo: CardRepository = Depends(get_card_repo),
) -> CardRecord:
    await _limit(request, f"pipeline_cards:create:{user.id}", window=3600, max_count=600)
    return await create_card(
        repo,
        pipeline_id=pipeline.id,
        payload=payload,
        current_user_id=user.id,
    )


@router.get("/pipelines/{pipeline_id}/cards/{card_id}", response_model=CardRecord)
async def get_card_endpoint(
    card: CardRecord = Depends(owned_card),
) -> CardRecord:
    return card


@router.get(
    "/pipelines/{pipeline_id}/cards/{card_id}/import-metadata",
    response_model=list[ImportRowRecord],
)
async def get_card_import_metadata_endpoint(
    card: CardRecord = Depends(owned_card),
    repo: CardRepository = Depends(get_card_repo),
) -> list[ImportRowRecord]:
    return await repo.list_import_rows_for_card(card.id)


@router.patch(
    "/pipelines/{pipeline_id}/cards/{card_id}",
    response_model=CardRecord,
    dependencies=[Depends(csrf_dependency)],
)
async def update_card_endpoint(
    payload: CardPatch,
    card: CardRecord = Depends(owned_card),
    repo: CardRepository = Depends(get_card_repo),
) -> CardRecord:
    return await update_card(repo, card=card, payload=payload)


@router.post(
    "/pipelines/{pipeline_id}/cards/{card_id}/move",
    response_model=CardRecord,
    dependencies=[Depends(csrf_dependency)],
)
async def move_card_endpoint(
    payload: CardMove,
    user: UserRecord = Depends(get_current_user),
    card: CardRecord = Depends(owned_card),
    repo: CardRepository = Depends(get_card_repo),
) -> CardRecord:
    return await move_card(repo, card=card, payload=payload, current_user_id=user.id)


@router.delete(
    "/pipelines/{pipeline_id}/cards/{card_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Depends(csrf_dependency)],
)
async def delete_card_endpoint(
    card: CardRecord = Depends(owned_card),
    repo: CardRepository = Depends(get_card_repo),
) -> None:
    await delete_card(repo, card_id=card.id)


@router.post(
    "/pipelines/{pipeline_id}/cards/import",
    response_model=ImportResult,
    dependencies=[Depends(csrf_dependency)],
)
async def import_cards_endpoint(
    request: Request,
    stage_id: UUID = Form(...),
    file: UploadFile = File(...),
    user: UserRecord = Depends(get_current_user),
    pipeline: PipelineRecord = Depends(owned_pipeline),
    repo: CardRepository = Depends(get_card_repo),
) -> ImportResult:
    await _limit(request, f"pipeline_cards:import:{user.id}", window=3600, max_count=10)
    raw_content = await file.read()
    try:
        content = raw_content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Arquivo CSV deve estar em UTF-8.",
        ) from exc
    return await import_cards(
        repo,
        pipeline_id=pipeline.id,
        stage_id=stage_id,
        current_user_id=user.id,
        filename=file.filename or "import.csv",
        file_size_bytes=len(raw_content),
        content=content,
    )
