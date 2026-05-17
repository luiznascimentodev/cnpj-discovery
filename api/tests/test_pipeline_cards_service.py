"""Tests for pipeline cards service."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from modules.pipeline.cards.schemas import CardCreate, CardMove, CardPatch, CardRecord
from modules.pipeline.cards.service import (
    cards_by_cnpj,
    create_card,
    delete_card,
    list_cards,
    move_card,
    update_card,
)


def _card(**overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id=uuid4(),
        pipeline_id=uuid4(),
        stage_id=uuid4(),
        cnpj_basico="12345678",
        position=0,
        estimated_value_cents=None,
        notes=None,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return CardRecord(**base)


def _assert_error(exc: HTTPException, status_code: int, code: str) -> None:
    assert exc.status_code == status_code
    assert exc.detail["code"] == code


@pytest.mark.asyncio
async def test_create_card_with_explicit_stage_inserts_and_records_history():
    pipeline_id = uuid4()
    stage_id = uuid4()
    user_id = uuid4()
    card = _card(pipeline_id=pipeline_id, stage_id=stage_id)
    repo = AsyncMock()
    repo.cnpj_exists.return_value = True
    repo.card_exists_in_pipeline.return_value = False
    repo.stage_exists_in_pipeline.return_value = True
    repo.max_position_in_stage.return_value = 4
    repo.insert.return_value = card

    result = await create_card(
        repo,
        pipeline_id=pipeline_id,
        payload=CardCreate(cnpj_basico="12345678", stage_id=stage_id, notes="n"),
        current_user_id=user_id,
    )

    repo.insert.assert_awaited_once_with(
        pipeline_id=pipeline_id,
        stage_id=stage_id,
        cnpj_basico="12345678",
        position=5,
        display_name=None,
        estimated_value_cents=None,
        notes="n",
    )
    repo.insert_stage_change.assert_awaited_once_with(
        card.id,
        from_stage_id=None,
        to_stage_id=stage_id,
        changed_by_user_id=user_id,
    )
    assert result == card


@pytest.mark.asyncio
async def test_create_card_without_stage_uses_first_stage_and_position_zero():
    pipeline_id = uuid4()
    stage_id = uuid4()
    card = _card(pipeline_id=pipeline_id, stage_id=stage_id, position=0)
    repo = AsyncMock()
    repo.cnpj_exists.return_value = True
    repo.card_exists_in_pipeline.return_value = False
    repo.first_stage_id_in_pipeline.return_value = stage_id
    repo.max_position_in_stage.return_value = None
    repo.insert.return_value = card

    result = await create_card(
        repo,
        pipeline_id=pipeline_id,
        payload=CardCreate(cnpj_basico="12345678"),
        current_user_id=uuid4(),
    )

    repo.first_stage_id_in_pipeline.assert_awaited_once_with(pipeline_id)
    assert repo.insert.call_args.kwargs["position"] == 0
    assert result == card


@pytest.mark.asyncio
async def test_create_card_raises_when_cnpj_missing():
    repo = AsyncMock()
    repo.cnpj_exists.return_value = False

    with pytest.raises(HTTPException) as exc_info:
        await create_card(
            repo,
            pipeline_id=uuid4(),
            payload=CardCreate(cnpj_basico="12345678"),
            current_user_id=uuid4(),
        )

    _assert_error(exc_info.value, 422, "cnpj_not_found")
    repo.insert.assert_not_called()


@pytest.mark.asyncio
async def test_create_card_raises_when_duplicate():
    repo = AsyncMock()
    repo.cnpj_exists.return_value = True
    repo.card_exists_in_pipeline.return_value = True

    with pytest.raises(HTTPException) as exc_info:
        await create_card(
            repo,
            pipeline_id=uuid4(),
            payload=CardCreate(cnpj_basico="12345678"),
            current_user_id=uuid4(),
        )

    _assert_error(exc_info.value, 409, "card_duplicate")


@pytest.mark.asyncio
async def test_create_card_raises_when_stage_not_in_pipeline():
    repo = AsyncMock()
    repo.cnpj_exists.return_value = True
    repo.card_exists_in_pipeline.return_value = False
    repo.stage_exists_in_pipeline.return_value = False

    with pytest.raises(HTTPException) as exc_info:
        await create_card(
            repo,
            pipeline_id=uuid4(),
            payload=CardCreate(cnpj_basico="12345678", stage_id=uuid4()),
            current_user_id=uuid4(),
        )

    _assert_error(exc_info.value, 422, "stage_not_in_pipeline")


@pytest.mark.asyncio
async def test_create_card_raises_when_pipeline_has_no_stage():
    repo = AsyncMock()
    repo.cnpj_exists.return_value = True
    repo.card_exists_in_pipeline.return_value = False
    repo.first_stage_id_in_pipeline.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await create_card(
            repo,
            pipeline_id=uuid4(),
            payload=CardCreate(cnpj_basico="12345678"),
            current_user_id=uuid4(),
        )

    _assert_error(exc_info.value, 422, "stage_not_in_pipeline")


@pytest.mark.asyncio
async def test_list_cards_delegates_to_repo():
    repo = AsyncMock()
    repo.list_with_company_summary.return_value = []
    pipeline_id = uuid4()

    result = await list_cards(repo, pipeline_id)

    repo.list_with_company_summary.assert_awaited_once_with(pipeline_id)
    assert result == []


@pytest.mark.asyncio
async def test_update_card_delegates_to_repo():
    card = _card()
    updated = _card(id=card.id, estimated_value_cents=100)
    repo = AsyncMock()
    repo.update.return_value = updated

    result = await update_card(
        repo,
        card=card,
        payload=CardPatch(estimated_value_cents=100, notes="x"),
    )

    repo.update.assert_awaited_once_with(
        card.id,
        display_name=None,
        estimated_value_cents=100,
        notes="x",
    )
    assert result == updated


@pytest.mark.asyncio
async def test_move_card_same_stage_updates_without_history():
    stage_id = uuid4()
    card = _card(stage_id=stage_id)
    moved = _card(id=card.id, stage_id=stage_id, position=2)
    repo = AsyncMock()
    repo.stage_exists_in_pipeline.return_value = True
    repo.move.return_value = moved

    result = await move_card(
        repo,
        card=card,
        payload=CardMove(stage_id=stage_id, position=2),
        current_user_id=uuid4(),
    )

    repo.move.assert_awaited_once_with(card.id, stage_id=stage_id, position=2)
    repo.insert_stage_change.assert_not_called()
    assert result == moved


@pytest.mark.asyncio
async def test_move_card_new_stage_updates_and_records_history():
    old_stage_id = uuid4()
    new_stage_id = uuid4()
    user_id = uuid4()
    card = _card(stage_id=old_stage_id)
    moved = _card(id=card.id, stage_id=new_stage_id)
    repo = AsyncMock()
    repo.stage_exists_in_pipeline.return_value = True
    repo.move.return_value = moved

    result = await move_card(
        repo,
        card=card,
        payload=CardMove(stage_id=new_stage_id, position=0),
        current_user_id=user_id,
    )

    repo.insert_stage_change.assert_awaited_once_with(
        card.id,
        from_stage_id=old_stage_id,
        to_stage_id=new_stage_id,
        changed_by_user_id=user_id,
    )
    assert result == moved


@pytest.mark.asyncio
async def test_move_card_raises_when_stage_not_in_pipeline():
    repo = AsyncMock()
    repo.stage_exists_in_pipeline.return_value = False

    with pytest.raises(HTTPException) as exc_info:
        await move_card(
            repo,
            card=_card(),
            payload=CardMove(stage_id=uuid4(), position=0),
            current_user_id=uuid4(),
        )

    _assert_error(exc_info.value, 422, "stage_not_in_pipeline")
    repo.move.assert_not_called()


@pytest.mark.asyncio
async def test_delete_card_delegates_to_repo():
    repo = AsyncMock()
    card_id = uuid4()

    await delete_card(repo, card_id=card_id)

    repo.delete.assert_awaited_once_with(card_id)


@pytest.mark.asyncio
async def test_cards_by_cnpj_delegates_to_repo():
    repo = AsyncMock()
    repo.pipelines_containing_cnpj.return_value = []
    owner_id = uuid4()

    result = await cards_by_cnpj(repo, owner_user_id=owner_id, cnpj_basico="12345678")

    repo.pipelines_containing_cnpj.assert_awaited_once_with(owner_id, "12345678")
    assert result == []
