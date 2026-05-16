"""Authorization regression tests for pipeline ownership boundaries."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.datastructures import URL

from core.csrf import csrf_dependency
from core.middleware.auth import get_current_user
from modules.pipeline.cards.schemas import CardMove, CardRecord
from modules.pipeline.cards.service import move_card
from modules.pipeline.dependencies import (
    owned_activity,
    owned_card,
    owned_pipeline,
    owned_stage,
    owned_task,
)
from modules.pipeline.pipelines.schemas import PipelineRecord
from modules.pipeline.stages.schemas import StageRecord


class FakeRequest:
    def __init__(self, *, cookies=None, headers=None):
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.url = URL("http://test.local")
        self.client = SimpleNamespace(host="127.0.0.1")


class FakeResponse:
    def set_cookie(self, *args, **kwargs):
        pass


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
        name="Stage",
        position=0,
        color=None,
        is_won=False,
        is_lost=False,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return StageRecord(**base)


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


@pytest.mark.asyncio
async def test_cross_user_pipeline_returns_404_not_403():
    repo = AsyncMock()
    repo.get_for_owner.return_value = None
    user = SimpleNamespace(id=uuid4())

    with pytest.raises(HTTPException) as exc_info:
        await owned_pipeline(pipeline_id=uuid4(), user=user, repo=repo)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "pipeline_not_found"


@pytest.mark.asyncio
async def test_cross_user_stage_returns_404_not_403():
    pipeline = _pipeline()
    repo = AsyncMock()
    repo.get_in_pipeline.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await owned_stage(stage_id=uuid4(), pipeline=pipeline, repo=repo)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "stage_not_found"


@pytest.mark.asyncio
async def test_cross_user_card_returns_404_not_403():
    pipeline = _pipeline()
    repo = AsyncMock()
    repo.get_in_pipeline.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await owned_card(card_id=uuid4(), pipeline=pipeline, repo=repo)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "card_not_found"


@pytest.mark.asyncio
async def test_cross_user_activity_returns_404_not_403():
    card = _card()
    repo = AsyncMock()
    repo.get_in_card.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await owned_activity(activity_id=uuid4(), card=card, repo=repo)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "activity_not_found"


@pytest.mark.asyncio
async def test_cross_user_task_returns_404_not_403():
    card = _card()
    repo = AsyncMock()
    repo.get_in_card.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await owned_task(task_id=uuid4(), card=card, repo=repo)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "task_not_found"


@pytest.mark.asyncio
async def test_move_card_to_stage_outside_pipeline_returns_422():
    repo = AsyncMock()
    repo.stage_exists_in_pipeline.return_value = False
    card = _card()

    with pytest.raises(HTTPException) as exc_info:
        await move_card(
            repo,
            card=card,
            payload=CardMove(stage_id=uuid4(), position=0),
            current_user_id=uuid4(),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "stage_not_in_pipeline"


@pytest.mark.asyncio
async def test_post_without_csrf_token_returns_403():
    with pytest.raises(HTTPException) as exc_info:
        await csrf_dependency(FakeRequest())

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_post_with_mismatched_csrf_token_returns_403():
    request = FakeRequest(cookies={"cnpj_csrf": "cookie"}, headers={"x-csrf-token": "header"})

    with pytest.raises(HTTPException) as exc_info:
        await csrf_dependency(request)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_post_with_matching_csrf_token_passes():
    request = FakeRequest(cookies={"cnpj_csrf": "same"}, headers={"x-csrf-token": "same"})

    result = await csrf_dependency(request)

    assert result is None


@pytest.mark.asyncio
async def test_get_without_session_cookie_returns_401():
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(FakeRequest(), FakeResponse())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_owned_stage_returns_stage_for_same_pipeline():
    pipeline = _pipeline()
    stage = _stage(pipeline_id=pipeline.id)
    repo = AsyncMock()
    repo.get_in_pipeline.return_value = stage

    result = await owned_stage(stage_id=stage.id, pipeline=pipeline, repo=repo)

    assert result == stage


@pytest.mark.asyncio
async def test_owned_card_returns_card_for_same_pipeline():
    pipeline = _pipeline()
    card = _card(pipeline_id=pipeline.id)
    repo = AsyncMock()
    repo.get_in_pipeline.return_value = card

    result = await owned_card(card_id=card.id, pipeline=pipeline, repo=repo)

    assert result == card
