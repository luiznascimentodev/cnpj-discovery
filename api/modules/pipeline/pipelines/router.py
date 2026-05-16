"""Router for /pipelines endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from core.cache import get_redis
from core.csrf import csrf_dependency
from core.middleware.auth import get_current_user
from core.rate_limit import RateLimiter
from modules.auth.schemas import UserRecord
from modules.pipeline.cards.repository import CardRepository
from modules.pipeline.dependencies import (
    get_card_repo,
    get_pipeline_repo,
    get_stage_repo,
    owned_pipeline,
)
from modules.pipeline.pipelines.repository import PipelineRepository
from modules.pipeline.pipelines.schemas import (
    PipelineCreate,
    PipelineDetail,
    PipelinePatch,
    PipelineRecord,
)
from modules.pipeline.pipelines.service import (
    archive_pipeline,
    create_pipeline,
    delete_pipeline,
    get_pipeline_detail,
    unarchive_pipeline,
    update_pipeline,
)
from modules.pipeline.stages.repository import StageRepository

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


async def _limit(request: Request, key: str, *, window: int, max_count: int) -> None:
    from fastapi import HTTPException

    redis = get_redis()
    result = await RateLimiter(
        redis,
        bucket_key=f"rate:{key}",
        window=window,
        max_count=max_count,
    ).try_acquire()
    if not result.ok:
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas. Tente novamente mais tarde.",
            headers={"Retry-After": str(result.retry_after)},
        )


@router.get("", response_model=list[PipelineRecord])
async def list_pipelines(
    archived: bool = False,
    user: UserRecord = Depends(get_current_user),
    repo: PipelineRepository = Depends(get_pipeline_repo),
) -> list[PipelineRecord]:
    return await repo.list_for_owner(user.id, include_archived=archived)


@router.post(
    "",
    response_model=PipelineRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(csrf_dependency)],
)
async def create_pipeline_endpoint(
    payload: PipelineCreate,
    request: Request,
    user: UserRecord = Depends(get_current_user),
    repo: PipelineRepository = Depends(get_pipeline_repo),
    stage_repo: StageRepository = Depends(get_stage_repo),
) -> PipelineRecord:
    await _limit(request, f"pipelines:create:{user.id}", window=3600, max_count=30)
    return await create_pipeline(repo, stage_repo, owner_user_id=user.id, payload=payload)


@router.get("/{pipeline_id}", response_model=PipelineDetail)
async def get_pipeline(
    pipeline: PipelineRecord = Depends(owned_pipeline),
    stage_repo: StageRepository = Depends(get_stage_repo),
    card_repo: CardRepository = Depends(get_card_repo),
) -> PipelineDetail:
    return await get_pipeline_detail(
        pipeline._repo if hasattr(pipeline, "_repo") else None,  # not used
        stage_repo,
        card_repo,
        pipeline=pipeline,
    )


@router.patch(
    "/{pipeline_id}",
    response_model=PipelineRecord,
    dependencies=[Depends(csrf_dependency)],
)
async def update_pipeline_endpoint(
    payload: PipelinePatch,
    pipeline: PipelineRecord = Depends(owned_pipeline),
    repo: PipelineRepository = Depends(get_pipeline_repo),
) -> PipelineRecord:
    return await update_pipeline(repo, pipeline_id=pipeline.id, payload=payload)


@router.post(
    "/{pipeline_id}/archive",
    response_model=PipelineRecord,
    dependencies=[Depends(csrf_dependency)],
)
async def archive_pipeline_endpoint(
    pipeline: PipelineRecord = Depends(owned_pipeline),
    repo: PipelineRepository = Depends(get_pipeline_repo),
) -> PipelineRecord:
    return await archive_pipeline(repo, pipeline)


@router.post(
    "/{pipeline_id}/unarchive",
    response_model=PipelineRecord,
    dependencies=[Depends(csrf_dependency)],
)
async def unarchive_pipeline_endpoint(
    pipeline: PipelineRecord = Depends(owned_pipeline),
    repo: PipelineRepository = Depends(get_pipeline_repo),
) -> PipelineRecord:
    return await unarchive_pipeline(repo, pipeline)


@router.delete(
    "/{pipeline_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Depends(csrf_dependency)],
)
async def delete_pipeline_endpoint(
    pipeline: PipelineRecord = Depends(owned_pipeline),
    repo: PipelineRepository = Depends(get_pipeline_repo),
) -> None:
    await delete_pipeline(repo, pipeline_id=pipeline.id)
