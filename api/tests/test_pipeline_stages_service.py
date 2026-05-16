"""Tests for modules.pipeline.stages.service."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from modules.pipeline.stages.schemas import StageCreate, StagePatch, StageRecord
from modules.pipeline.stages.service import (
    create_stage,
    delete_stage,
    reorder_stages,
    update_stage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stage(pipeline_id, position=0, **overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id=uuid4(),
        pipeline_id=pipeline_id,
        name="Stage",
        position=position,
        color=None,
        is_won=False,
        is_lost=False,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return StageRecord(**base)


def _assert_http_error(exc: HTTPException, *, status_code: int, code: str) -> None:
    assert exc.status_code == status_code
    assert exc.detail["code"] == code


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_stage_with_explicit_position_uses_payload_position():
    pipeline_id = uuid4()
    created = _stage(pipeline_id, position=2, name="Demo", color="#123456", is_won=True)
    repo = AsyncMock()
    repo.insert.return_value = created

    payload = StageCreate(
        name="Demo",
        color="#123456",
        is_won=True,
        is_lost=False,
        position=2,
    )

    result = await create_stage(repo, pipeline_id=pipeline_id, payload=payload)

    repo.max_position_in_pipeline.assert_not_called()
    repo.insert.assert_called_once_with(
        pipeline_id=pipeline_id,
        name="Demo",
        position=2,
        color="#123456",
        is_won=True,
        is_lost=False,
    )
    assert result == created


@pytest.mark.asyncio
async def test_create_stage_with_default_position_uses_max_plus_one():
    pipeline_id = uuid4()
    created = _stage(pipeline_id, position=5, name="Follow-up")
    repo = AsyncMock()
    repo.max_position_in_pipeline.return_value = 4
    repo.insert.return_value = created

    payload = StageCreate(name="Follow-up")

    result = await create_stage(repo, pipeline_id=pipeline_id, payload=payload)

    repo.max_position_in_pipeline.assert_called_once_with(pipeline_id)
    repo.insert.assert_called_once_with(
        pipeline_id=pipeline_id,
        name="Follow-up",
        position=5,
        color=None,
        is_won=False,
        is_lost=False,
    )
    assert result == created


@pytest.mark.asyncio
async def test_create_stage_in_empty_pipeline_defaults_position_to_zero():
    pipeline_id = uuid4()
    created = _stage(pipeline_id, position=0, name="First")
    repo = AsyncMock()
    repo.max_position_in_pipeline.return_value = None
    repo.insert.return_value = created

    payload = StageCreate(name="First")

    result = await create_stage(repo, pipeline_id=pipeline_id, payload=payload)

    repo.max_position_in_pipeline.assert_called_once_with(pipeline_id)
    repo.insert.assert_called_once_with(
        pipeline_id=pipeline_id,
        name="First",
        position=0,
        color=None,
        is_won=False,
        is_lost=False,
    )
    assert result == created


@pytest.mark.asyncio
async def test_update_stage_delegates_to_repo():
    stage = _stage(uuid4())
    updated = _stage(
        stage.pipeline_id,
        id=stage.id,
        name="Updated",
        color="#abcdef",
        is_lost=True,
    )
    repo = AsyncMock()
    repo.update.return_value = updated

    payload = StagePatch(name="Updated", color="#abcdef", is_won=None, is_lost=True)

    result = await update_stage(repo, stage=stage, payload=payload)

    repo.update.assert_called_once_with(
        stage.id,
        name="Updated",
        color="#abcdef",
        is_won=None,
        is_lost=True,
    )
    assert result == updated


@pytest.mark.asyncio
async def test_reorder_stages_when_ids_cover_pipeline_calls_repo():
    pipeline_id = uuid4()
    stage_a = _stage(pipeline_id, position=0)
    stage_b = _stage(pipeline_id, position=1)
    stage_c = _stage(pipeline_id, position=2)
    ordered_ids = [stage_c.id, stage_a.id, stage_b.id]
    repo = AsyncMock()
    repo.list_for_pipeline.return_value = [stage_a, stage_b, stage_c]

    result = await reorder_stages(repo, pipeline_id=pipeline_id, stage_ids=ordered_ids)

    repo.list_for_pipeline.assert_called_once_with(pipeline_id)
    repo.reorder.assert_called_once_with(pipeline_id, ordered_ids)
    assert result is None


@pytest.mark.asyncio
async def test_reorder_stages_with_missing_stage_id_raises_mismatch():
    pipeline_id = uuid4()
    stage_a = _stage(pipeline_id, position=0)
    stage_b = _stage(pipeline_id, position=1)
    repo = AsyncMock()
    repo.list_for_pipeline.return_value = [stage_a, stage_b]

    with pytest.raises(HTTPException) as exc_info:
        await reorder_stages(repo, pipeline_id=pipeline_id, stage_ids=[stage_a.id])

    repo.reorder.assert_not_called()
    _assert_http_error(
        exc_info.value,
        status_code=422,
        code="stage_not_in_pipeline",
    )


@pytest.mark.asyncio
async def test_reorder_stages_with_extra_stage_id_raises_mismatch():
    pipeline_id = uuid4()
    stage_a = _stage(pipeline_id, position=0)
    stage_b = _stage(pipeline_id, position=1)
    extra_stage_id = uuid4()
    repo = AsyncMock()
    repo.list_for_pipeline.return_value = [stage_a, stage_b]

    with pytest.raises(HTTPException) as exc_info:
        await reorder_stages(
            repo,
            pipeline_id=pipeline_id,
            stage_ids=[stage_a.id, stage_b.id, extra_stage_id],
        )

    repo.reorder.assert_not_called()
    _assert_http_error(
        exc_info.value,
        status_code=422,
        code="stage_not_in_pipeline",
    )


@pytest.mark.asyncio
async def test_reorder_stages_with_duplicate_stage_id_raises_mismatch():
    pipeline_id = uuid4()
    stage_a = _stage(pipeline_id, position=0)
    stage_b = _stage(pipeline_id, position=1)
    repo = AsyncMock()
    repo.list_for_pipeline.return_value = [stage_a, stage_b]

    with pytest.raises(HTTPException) as exc_info:
        await reorder_stages(
            repo,
            pipeline_id=pipeline_id,
            stage_ids=[stage_a.id, stage_a.id],
        )

    repo.reorder.assert_not_called()
    _assert_http_error(
        exc_info.value,
        status_code=422,
        code="stage_not_in_pipeline",
    )


@pytest.mark.asyncio
async def test_delete_stage_when_last_stage_raises_cannot_delete_last_stage():
    pipeline_id = uuid4()
    stage = _stage(pipeline_id)
    repo = AsyncMock()
    repo.count_stages.return_value = 1

    with pytest.raises(HTTPException) as exc_info:
        await delete_stage(
            repo,
            pipeline_id=pipeline_id,
            stage=stage,
            move_cards_to=None,
        )

    repo.count_stages.assert_called_once_with(pipeline_id)
    repo.count_cards_in_stage.assert_not_called()
    repo.delete.assert_not_called()
    repo.move_cards_and_delete.assert_not_called()
    _assert_http_error(
        exc_info.value,
        status_code=409,
        code="cannot_delete_last_stage",
    )


@pytest.mark.asyncio
async def test_delete_stage_without_cards_deletes_stage():
    pipeline_id = uuid4()
    stage = _stage(pipeline_id)
    repo = AsyncMock()
    repo.count_stages.return_value = 2
    repo.count_cards_in_stage.return_value = 0

    result = await delete_stage(
        repo,
        pipeline_id=pipeline_id,
        stage=stage,
        move_cards_to=None,
    )

    repo.count_stages.assert_called_once_with(pipeline_id)
    repo.count_cards_in_stage.assert_called_once_with(stage.id)
    repo.delete.assert_called_once_with(stage.id)
    repo.move_cards_and_delete.assert_not_called()
    assert result is None


@pytest.mark.asyncio
async def test_delete_stage_with_cards_without_target_raises_stage_has_cards():
    pipeline_id = uuid4()
    stage = _stage(pipeline_id)
    repo = AsyncMock()
    repo.count_stages.return_value = 2
    repo.count_cards_in_stage.return_value = 3

    with pytest.raises(HTTPException) as exc_info:
        await delete_stage(
            repo,
            pipeline_id=pipeline_id,
            stage=stage,
            move_cards_to=None,
        )

    repo.delete.assert_not_called()
    repo.move_cards_and_delete.assert_not_called()
    _assert_http_error(exc_info.value, status_code=409, code="stage_has_cards")


@pytest.mark.asyncio
async def test_delete_stage_with_cards_and_valid_target_moves_cards_and_deletes():
    pipeline_id = uuid4()
    stage = _stage(pipeline_id)
    target_stage = _stage(pipeline_id, position=1)
    repo = AsyncMock()
    repo.count_stages.return_value = 2
    repo.count_cards_in_stage.return_value = 3
    repo.get_in_pipeline.return_value = target_stage

    result = await delete_stage(
        repo,
        pipeline_id=pipeline_id,
        stage=stage,
        move_cards_to=target_stage.id,
    )

    repo.get_in_pipeline.assert_called_once_with(target_stage.id, pipeline_id=pipeline_id)
    repo.move_cards_and_delete.assert_called_once_with(stage.id, target_stage.id)
    repo.delete.assert_not_called()
    assert result is None


@pytest.mark.asyncio
async def test_delete_stage_with_cards_and_invalid_target_raises_stage_not_in_pipeline():
    pipeline_id = uuid4()
    stage = _stage(pipeline_id)
    target_stage_id = uuid4()
    repo = AsyncMock()
    repo.count_stages.return_value = 2
    repo.count_cards_in_stage.return_value = 3
    repo.get_in_pipeline.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await delete_stage(
            repo,
            pipeline_id=pipeline_id,
            stage=stage,
            move_cards_to=target_stage_id,
        )

    repo.get_in_pipeline.assert_called_once_with(target_stage_id, pipeline_id=pipeline_id)
    repo.delete.assert_not_called()
    repo.move_cards_and_delete.assert_not_called()
    _assert_http_error(
        exc_info.value,
        status_code=422,
        code="stage_not_in_pipeline",
    )
