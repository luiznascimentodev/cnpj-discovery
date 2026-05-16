"""Router for /pipelines/{pipeline_id}/stages endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status

from core.csrf import csrf_dependency
from modules.pipeline.dependencies import get_stage_repo, owned_pipeline, owned_stage
from modules.pipeline.pipelines.schemas import PipelineRecord
from modules.pipeline.stages.repository import StageRepository
from modules.pipeline.stages.schemas import (
    StageCreate,
    StagePatch,
    StageRecord,
    StageReorderRequest,
)
from modules.pipeline.stages.service import (
    create_stage,
    delete_stage,
    reorder_stages,
    update_stage,
)

router = APIRouter(prefix="/pipelines/{pipeline_id}/stages", tags=["pipeline_stages"])


@router.get("", response_model=list[StageRecord])
async def list_stages(
    pipeline: PipelineRecord = Depends(owned_pipeline),
    repo: StageRepository = Depends(get_stage_repo),
) -> list[StageRecord]:
    return await repo.list_for_pipeline(pipeline.id)


@router.post(
    "",
    response_model=StageRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(csrf_dependency)],
)
async def create_stage_endpoint(
    payload: StageCreate,
    pipeline: PipelineRecord = Depends(owned_pipeline),
    repo: StageRepository = Depends(get_stage_repo),
) -> StageRecord:
    return await create_stage(repo, pipeline_id=pipeline.id, payload=payload)


@router.patch(
    "/{stage_id}",
    response_model=StageRecord,
    dependencies=[Depends(csrf_dependency)],
)
async def update_stage_endpoint(
    payload: StagePatch,
    pipeline: PipelineRecord = Depends(owned_pipeline),
    stage: StageRecord = Depends(owned_stage),
    repo: StageRepository = Depends(get_stage_repo),
) -> StageRecord:
    return await update_stage(repo, stage=stage, payload=payload)


@router.post(
    "/reorder",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Depends(csrf_dependency)],
)
async def reorder_stages_endpoint(
    payload: StageReorderRequest,
    pipeline: PipelineRecord = Depends(owned_pipeline),
    repo: StageRepository = Depends(get_stage_repo),
) -> None:
    await reorder_stages(repo, pipeline_id=pipeline.id, stage_ids=payload.stage_ids)


@router.delete(
    "/{stage_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Depends(csrf_dependency)],
)
async def delete_stage_endpoint(
    move_cards_to: UUID | None = None,
    pipeline: PipelineRecord = Depends(owned_pipeline),
    stage: StageRecord = Depends(owned_stage),
    repo: StageRepository = Depends(get_stage_repo),
) -> None:
    await delete_stage(
        repo,
        pipeline_id=pipeline.id,
        stage=stage,
        move_cards_to=move_cards_to,
    )
