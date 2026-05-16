"""Service layer for pipelines — orchestrates repos and enforces business rules."""
from __future__ import annotations

from uuid import UUID

from modules.pipeline.cards.repository import CardRepository
from modules.pipeline.errors import ErrorCode, pipeline_error
from modules.pipeline.pipelines.repository import PipelineRepository
from modules.pipeline.pipelines.schemas import (
    PipelineCreate,
    PipelineDetail,
    PipelinePatch,
    PipelineRecord,
    StageCount,
)
from modules.pipeline.stages.repository import StageRepository


DEFAULT_STAGES: list[dict] = [
    {"name": "Lead",        "color": "info",    "is_won": False, "is_lost": False},
    {"name": "Contatado",   "color": "info",    "is_won": False, "is_lost": False},
    {"name": "Qualificado", "color": "warning", "is_won": False, "is_lost": False},
    {"name": "Proposta",    "color": "warning", "is_won": False, "is_lost": False},
    {"name": "Ganho",       "color": "success", "is_won": True,  "is_lost": False},
    {"name": "Perdido",     "color": "danger",  "is_won": False, "is_lost": True},
]


async def create_pipeline(
    repo_pipeline: PipelineRepository,
    repo_stage: StageRepository,
    *,
    owner_user_id: UUID,
    payload: PipelineCreate,
) -> PipelineRecord:
    pipeline = await repo_pipeline.insert(
        owner_user_id=owner_user_id,
        name=payload.name,
        description=payload.description,
    )
    defaults = [{**s, "position": idx} for idx, s in enumerate(DEFAULT_STAGES)]
    await repo_stage.bulk_insert(pipeline.id, defaults)
    return pipeline


async def update_pipeline(
    repo: PipelineRepository,
    *,
    pipeline_id: UUID,
    payload: PipelinePatch,
) -> PipelineRecord:
    return await repo.update(pipeline_id, name=payload.name, description=payload.description)


async def archive_pipeline(repo: PipelineRepository, pipeline: PipelineRecord) -> PipelineRecord:
    if pipeline.archived_at is not None:
        return pipeline  # idempotente
    return await repo.archive(pipeline.id)


async def unarchive_pipeline(repo: PipelineRepository, pipeline: PipelineRecord) -> PipelineRecord:
    if pipeline.archived_at is None:
        raise pipeline_error(ErrorCode.NOT_ARCHIVED)
    return await repo.unarchive(pipeline.id)


async def delete_pipeline(repo: PipelineRepository, *, pipeline_id: UUID) -> None:
    await repo.delete(pipeline_id)


async def get_pipeline_detail(
    repo_pipeline: PipelineRepository,
    repo_stage: StageRepository,
    repo_card: CardRepository,
    *,
    pipeline: PipelineRecord,
) -> PipelineDetail:
    stages = await repo_stage.list_for_pipeline(pipeline.id)
    cards = await repo_card.list_with_company_summary(pipeline.id)
    counts_by_stage: dict[UUID, tuple[int, int]] = {s.id: (0, 0) for s in stages}
    total_value = 0
    for cwc in cards:
        c = cwc.card
        n, v = counts_by_stage[c.stage_id]
        value = c.estimated_value_cents or 0
        counts_by_stage[c.stage_id] = (n + 1, v + value)
        total_value += value
    stage_counts = [
        StageCount(
            stage_id=s.id,
            name=s.name,
            card_count=counts_by_stage[s.id][0],
            total_value_cents=counts_by_stage[s.id][1],
        )
        for s in stages
    ]
    return PipelineDetail(pipeline=pipeline, stage_counts=stage_counts, total_value_cents=total_value)
