"""Tests for pipeline stages router and dependencies."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from modules.pipeline.pipelines.schemas import PipelineRecord
from modules.pipeline.stages import router as stages_router_module
from modules.pipeline.stages.schemas import (
    StageCreate,
    StagePatch,
    StageRecord,
    StageReorderRequest,
)


def _pipeline(**overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id=uuid4(),
        owner_user_id=uuid4(),
        name="Pipeline",
        description=None,
        archived_at=None,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return PipelineRecord(**base)


def _stage(**overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id=uuid4(),
        pipeline_id=uuid4(),
        name="Lead",
        position=0,
        color=None,
        is_won=False,
        is_lost=False,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return StageRecord(**base)


@pytest.mark.asyncio
async def test_list_stages_returns_pipeline_stages():
    pipeline = _pipeline()
    stages = [_stage(pipeline_id=pipeline.id), _stage(pipeline_id=pipeline.id, position=1)]
    repo = AsyncMock()
    repo.list_for_pipeline.return_value = stages

    result = await stages_router_module.list_stages(pipeline=pipeline, repo=repo)

    repo.list_for_pipeline.assert_awaited_once_with(pipeline.id)
    assert result == stages


@pytest.mark.asyncio
async def test_create_stage_endpoint_delegates_to_service():
    pipeline = _pipeline()
    payload = StageCreate(name="Novo", color="info", position=2)
    repo = AsyncMock()
    created = _stage(pipeline_id=pipeline.id, name="Novo", position=2)

    with patch(
        "modules.pipeline.stages.router.create_stage",
        new_callable=AsyncMock,
        return_value=created,
    ) as mock_svc:
        result = await stages_router_module.create_stage_endpoint(
            payload=payload,
            pipeline=pipeline,
            repo=repo,
        )

    mock_svc.assert_awaited_once_with(repo, pipeline_id=pipeline.id, payload=payload)
    assert result == created


@pytest.mark.asyncio
async def test_update_stage_endpoint_delegates_to_service():
    pipeline = _pipeline()
    stage = _stage(pipeline_id=pipeline.id)
    payload = StagePatch(name="Updated", color="warning")
    repo = AsyncMock()
    updated = _stage(id=stage.id, pipeline_id=pipeline.id, name="Updated")

    with patch(
        "modules.pipeline.stages.router.update_stage",
        new_callable=AsyncMock,
        return_value=updated,
    ) as mock_svc:
        result = await stages_router_module.update_stage_endpoint(
            payload=payload,
            pipeline=pipeline,
            stage=stage,
            repo=repo,
        )

    mock_svc.assert_awaited_once_with(repo, stage=stage, payload=payload)
    assert result == updated


@pytest.mark.asyncio
async def test_reorder_stages_endpoint_delegates_to_service():
    pipeline = _pipeline()
    stage_ids = [uuid4(), uuid4()]
    payload = StageReorderRequest(stage_ids=stage_ids)
    repo = AsyncMock()

    with patch(
        "modules.pipeline.stages.router.reorder_stages",
        new_callable=AsyncMock,
    ) as mock_svc:
        result = await stages_router_module.reorder_stages_endpoint(
            payload=payload,
            pipeline=pipeline,
            repo=repo,
        )

    mock_svc.assert_awaited_once_with(repo, pipeline_id=pipeline.id, stage_ids=stage_ids)
    assert result is None


@pytest.mark.asyncio
async def test_reorder_stages_endpoint_propagates_validation_error():
    from modules.pipeline.errors import ErrorCode, pipeline_error

    pipeline = _pipeline()
    payload = StageReorderRequest(stage_ids=[uuid4()])
    repo = AsyncMock()

    with patch(
        "modules.pipeline.stages.router.reorder_stages",
        new_callable=AsyncMock,
        side_effect=pipeline_error(ErrorCode.STAGE_NOT_IN_PIPELINE),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await stages_router_module.reorder_stages_endpoint(
                payload=payload,
                pipeline=pipeline,
                repo=repo,
            )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "stage_not_in_pipeline"


@pytest.mark.asyncio
async def test_delete_stage_endpoint_delegates_to_service_without_move_target():
    pipeline = _pipeline()
    stage = _stage(pipeline_id=pipeline.id)
    repo = AsyncMock()

    with patch(
        "modules.pipeline.stages.router.delete_stage",
        new_callable=AsyncMock,
    ) as mock_svc:
        result = await stages_router_module.delete_stage_endpoint(
            move_cards_to=None,
            pipeline=pipeline,
            stage=stage,
            repo=repo,
        )

    mock_svc.assert_awaited_once_with(
        repo,
        pipeline_id=pipeline.id,
        stage=stage,
        move_cards_to=None,
    )
    assert result is None


@pytest.mark.asyncio
async def test_delete_stage_endpoint_delegates_to_service_with_move_target():
    pipeline = _pipeline()
    stage = _stage(pipeline_id=pipeline.id)
    repo = AsyncMock()
    target_id = uuid4()

    with patch(
        "modules.pipeline.stages.router.delete_stage",
        new_callable=AsyncMock,
    ) as mock_svc:
        await stages_router_module.delete_stage_endpoint(
            move_cards_to=target_id,
            pipeline=pipeline,
            stage=stage,
            repo=repo,
        )

    mock_svc.assert_awaited_once_with(
        repo,
        pipeline_id=pipeline.id,
        stage=stage,
        move_cards_to=target_id,
    )


@pytest.mark.asyncio
async def test_delete_stage_endpoint_propagates_business_error():
    from modules.pipeline.errors import ErrorCode, pipeline_error

    pipeline = _pipeline()
    stage = _stage(pipeline_id=pipeline.id)
    repo = AsyncMock()

    with patch(
        "modules.pipeline.stages.router.delete_stage",
        new_callable=AsyncMock,
        side_effect=pipeline_error(ErrorCode.STAGE_HAS_CARDS),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await stages_router_module.delete_stage_endpoint(
                move_cards_to=None,
                pipeline=pipeline,
                stage=stage,
                repo=repo,
            )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "stage_has_cards"


@pytest.mark.asyncio
async def test_owned_stage_dep_returns_stage_when_found():
    from modules.pipeline.dependencies import owned_stage

    pipeline = _pipeline()
    stage = _stage(pipeline_id=pipeline.id)
    repo = AsyncMock()
    repo.get_in_pipeline.return_value = stage

    result = await owned_stage(stage_id=stage.id, pipeline=pipeline, repo=repo)

    repo.get_in_pipeline.assert_awaited_once_with(stage.id, pipeline_id=pipeline.id)
    assert result == stage


@pytest.mark.asyncio
async def test_owned_stage_dep_raises_404_when_not_found():
    from modules.pipeline.dependencies import owned_stage

    pipeline = _pipeline()
    repo = AsyncMock()
    repo.get_in_pipeline.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await owned_stage(stage_id=uuid4(), pipeline=pipeline, repo=repo)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "stage_not_found"


@pytest.mark.asyncio
async def test_owned_pipeline_dep_returns_pipeline_when_found():
    from modules.pipeline.dependencies import owned_pipeline

    pipeline = _pipeline()
    user = type("User", (), {"id": pipeline.owner_user_id})()
    repo = AsyncMock()
    repo.get_for_owner.return_value = pipeline

    result = await owned_pipeline(pipeline_id=pipeline.id, user=user, repo=repo)

    repo.get_for_owner.assert_awaited_once_with(
        pipeline.id,
        owner_user_id=pipeline.owner_user_id,
    )
    assert result == pipeline


@pytest.mark.asyncio
async def test_owned_pipeline_dep_raises_404_when_not_found():
    from modules.pipeline.dependencies import owned_pipeline

    user = type("User", (), {"id": uuid4()})()
    repo = AsyncMock()
    repo.get_for_owner.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await owned_pipeline(pipeline_id=uuid4(), user=user, repo=repo)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "pipeline_not_found"


@pytest.mark.asyncio
async def test_dependency_factories_create_repositories_with_pool():
    from modules.pipeline.cards.repository import CardRepository
    from modules.pipeline.dependencies import get_card_repo, get_pipeline_repo, get_stage_repo
    from modules.pipeline.pipelines.repository import PipelineRepository
    from modules.pipeline.stages.repository import StageRepository

    fake_pool = object()
    with patch(
        "modules.pipeline.dependencies.get_pool",
        new_callable=AsyncMock,
        return_value=fake_pool,
    ):
        pipeline_repo = await get_pipeline_repo()
        stage_repo = await get_stage_repo()
        card_repo = await get_card_repo()

    assert isinstance(pipeline_repo, PipelineRepository)
    assert isinstance(stage_repo, StageRepository)
    assert isinstance(card_repo, CardRepository)
    assert pipeline_repo._pool is fake_pool
    assert stage_repo._pool is fake_pool
    assert card_repo._pool is fake_pool
