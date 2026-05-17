"""Service layer for pipeline cards."""
from __future__ import annotations

from uuid import UUID

from modules.pipeline.cards.repository import CardRepository
from modules.pipeline.cards.schemas import (
    CardCreate,
    CardInPipelineSummary,
    CardMove,
    CardPatch,
    CardRecord,
    CardWithCompany,
)
from modules.pipeline.errors import ErrorCode, pipeline_error


async def create_card(
    repo: CardRepository,
    *,
    pipeline_id: UUID,
    payload: CardCreate,
    current_user_id: UUID,
) -> CardRecord:
    if not await repo.cnpj_exists(payload.cnpj_basico):
        raise pipeline_error(ErrorCode.CNPJ_NOT_FOUND)
    if await repo.card_exists_in_pipeline(pipeline_id, payload.cnpj_basico):
        raise pipeline_error(ErrorCode.CARD_DUPLICATE)

    stage_id = payload.stage_id
    if stage_id is None:
        stage_id = await repo.first_stage_id_in_pipeline(pipeline_id)
    elif not await repo.stage_exists_in_pipeline(stage_id, pipeline_id=pipeline_id):
        raise pipeline_error(ErrorCode.STAGE_NOT_IN_PIPELINE)

    if stage_id is None:
        raise pipeline_error(ErrorCode.STAGE_NOT_IN_PIPELINE)

    max_position = await repo.max_position_in_stage(stage_id)
    card = await repo.insert(
        pipeline_id=pipeline_id,
        stage_id=stage_id,
        cnpj_basico=payload.cnpj_basico,
        position=0 if max_position is None else max_position + 1,
        display_name=payload.display_name,
        estimated_value_cents=payload.estimated_value_cents,
        notes=payload.notes,
    )
    await repo.insert_stage_change(
        card.id,
        from_stage_id=None,
        to_stage_id=stage_id,
        changed_by_user_id=current_user_id,
    )
    return card


async def list_cards(repo: CardRepository, pipeline_id: UUID) -> list[CardWithCompany]:
    return await repo.list_with_company_summary(pipeline_id)


async def update_card(
    repo: CardRepository,
    *,
    card: CardRecord,
    payload: CardPatch,
) -> CardRecord:
    return await repo.update(
        card.id,
        display_name=payload.display_name,
        estimated_value_cents=payload.estimated_value_cents,
        notes=payload.notes,
    )


async def move_card(
    repo: CardRepository,
    *,
    card: CardRecord,
    payload: CardMove,
    current_user_id: UUID,
) -> CardRecord:
    if not await repo.stage_exists_in_pipeline(payload.stage_id, pipeline_id=card.pipeline_id):
        raise pipeline_error(ErrorCode.STAGE_NOT_IN_PIPELINE)

    moved = await repo.move(card.id, stage_id=payload.stage_id, position=payload.position)
    if payload.stage_id != card.stage_id:
        await repo.insert_stage_change(
            card.id,
            from_stage_id=card.stage_id,
            to_stage_id=payload.stage_id,
            changed_by_user_id=current_user_id,
        )
    return moved


async def delete_card(repo: CardRepository, *, card_id: UUID) -> None:
    await repo.delete(card_id)


async def cards_by_cnpj(
    repo: CardRepository,
    *,
    owner_user_id: UUID,
    cnpj_basico: str,
) -> list[CardInPipelineSummary]:
    return await repo.pipelines_containing_cnpj(owner_user_id, cnpj_basico)
