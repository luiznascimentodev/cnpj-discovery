"""Service layer for pipeline stages."""
from __future__ import annotations

from uuid import UUID

from modules.pipeline.errors import ErrorCode, pipeline_error
from modules.pipeline.stages.repository import StageRepository
from modules.pipeline.stages.schemas import StageCreate, StagePatch, StageRecord


async def create_stage(
    repo: StageRepository,
    *,
    pipeline_id: UUID,
    payload: StageCreate,
) -> StageRecord:
    position = payload.position
    if position is None:
        max_position = await repo.max_position_in_pipeline(pipeline_id)
        position = 0 if max_position is None else max_position + 1
    return await repo.insert(
        pipeline_id=pipeline_id,
        name=payload.name,
        position=position,
        color=payload.color,
        is_won=payload.is_won,
        is_lost=payload.is_lost,
    )


async def update_stage(
    repo: StageRepository,
    *,
    stage: StageRecord,
    payload: StagePatch,
) -> StageRecord:
    return await repo.update(
        stage.id,
        name=payload.name,
        color=payload.color,
        is_won=payload.is_won,
        is_lost=payload.is_lost,
    )


async def reorder_stages(
    repo: StageRepository,
    *,
    pipeline_id: UUID,
    stage_ids: list[UUID],
) -> None:
    current = await repo.list_for_pipeline(pipeline_id)
    current_ids = {stage.id for stage in current}
    requested_ids = set(stage_ids)
    if current_ids != requested_ids or len(stage_ids) != len(current):
        raise pipeline_error(ErrorCode.STAGE_NOT_IN_PIPELINE)
    await repo.reorder(pipeline_id, stage_ids)


async def delete_stage(
    repo: StageRepository,
    *,
    pipeline_id: UUID,
    stage: StageRecord,
    move_cards_to: UUID | None,
) -> None:
    total = await repo.count_stages(pipeline_id)
    if total <= 1:
        raise pipeline_error(ErrorCode.CANNOT_DELETE_LAST_STAGE)

    card_count = await repo.count_cards_in_stage(stage.id)
    if card_count == 0:
        await repo.delete(stage.id)
        return

    if move_cards_to is None:
        raise pipeline_error(ErrorCode.STAGE_HAS_CARDS)

    target = await repo.get_in_pipeline(move_cards_to, pipeline_id=pipeline_id)
    if target is None:
        raise pipeline_error(ErrorCode.STAGE_NOT_IN_PIPELINE)

    await repo.move_cards_and_delete(stage.id, move_cards_to)
