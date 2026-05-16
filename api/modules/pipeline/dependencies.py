"""Shared dependencies for pipeline module."""
from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from core.db import get_pool
from core.middleware.auth import get_current_user
from modules.auth.schemas import UserRecord
from modules.pipeline.cards.repository import CardRepository
from modules.pipeline.cards.schemas import CardRecord
from modules.pipeline.errors import ErrorCode, pipeline_error
from modules.pipeline.pipelines.repository import PipelineRepository
from modules.pipeline.pipelines.schemas import PipelineRecord
from modules.pipeline.stages.repository import StageRepository
from modules.pipeline.stages.schemas import StageRecord


async def get_pipeline_repo() -> PipelineRepository:
    return PipelineRepository(await get_pool())


async def get_stage_repo() -> StageRepository:
    return StageRepository(await get_pool())


async def get_card_repo() -> CardRepository:
    return CardRepository(await get_pool())


async def owned_pipeline(
    pipeline_id: UUID,
    user: UserRecord = Depends(get_current_user),
    repo: PipelineRepository = Depends(get_pipeline_repo),
) -> PipelineRecord:
    pipeline = await repo.get_for_owner(pipeline_id, owner_user_id=user.id)
    if pipeline is None:
        raise pipeline_error(ErrorCode.PIPELINE_NOT_FOUND)
    return pipeline


async def owned_stage(
    stage_id: UUID,
    pipeline: PipelineRecord = Depends(owned_pipeline),
    repo: StageRepository = Depends(get_stage_repo),
) -> StageRecord:
    stage = await repo.get_in_pipeline(stage_id, pipeline_id=pipeline.id)
    if stage is None:
        raise pipeline_error(ErrorCode.STAGE_NOT_FOUND)
    return stage


async def owned_card(
    card_id: UUID,
    pipeline: PipelineRecord = Depends(owned_pipeline),
    repo: CardRepository = Depends(get_card_repo),
) -> CardRecord:
    card = await repo.get_in_pipeline(card_id, pipeline_id=pipeline.id)
    if card is None:
        raise pipeline_error(ErrorCode.CARD_NOT_FOUND)
    return card
