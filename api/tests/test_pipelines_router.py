"""Tests for pipeline/pipelines router and dependencies."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException
from starlette.datastructures import URL

from modules.pipeline.pipelines import router as pipelines_router_module
from modules.pipeline.pipelines.schemas import PipelineCreate, PipelineDetail, PipelinePatch, PipelineRecord, StageCount


class FakeRequest:
    def __init__(self, *, cookies=None, headers=None, scheme="http", client_host="127.0.0.1"):
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.url = URL(f"{scheme}://test.local")
        self.client = SimpleNamespace(host=client_host) if client_host else None


def _pipeline(**overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id=uuid4(),
        owner_user_id=uuid4(),
        name="X",
        description=None,
        archived_at=None,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return PipelineRecord(**base)


def _user(**overrides):
    from modules.auth.schemas import UserRecord
    now = datetime.now(timezone.utc)
    base = dict(
        id=uuid4(),
        email="u@e.com",
        password_hash="x",
        name="N",
        email_verified_at=now,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )
    base.update(overrides)
    return UserRecord(**base)


# ── list_pipelines ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_pipelines_returns_active_by_default():
    user = _user()
    p = _pipeline(owner_user_id=user.id)
    repo = AsyncMock()
    repo.list_for_owner = AsyncMock(return_value=[p])

    result = await pipelines_router_module.list_pipelines(
        archived=False,
        user=user,
        repo=repo,
    )

    repo.list_for_owner.assert_awaited_once_with(user.id, include_archived=False)
    assert result == [p]


@pytest.mark.asyncio
async def test_list_pipelines_includes_archived_when_requested():
    user = _user()
    now = datetime.now(timezone.utc)
    p_archived = _pipeline(owner_user_id=user.id, archived_at=now)
    repo = AsyncMock()
    repo.list_for_owner = AsyncMock(return_value=[p_archived])

    result = await pipelines_router_module.list_pipelines(
        archived=True,
        user=user,
        repo=repo,
    )

    repo.list_for_owner.assert_awaited_once_with(user.id, include_archived=True)
    assert result == [p_archived]


# ── create_pipeline ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_pipeline_passes_rate_limit_then_calls_service():
    user = _user()
    p = _pipeline(owner_user_id=user.id)
    payload = PipelineCreate(name="Pipe A")
    request = FakeRequest()
    repo = AsyncMock()
    stage_repo = AsyncMock()

    with patch("modules.pipeline.pipelines.router._limit", new_callable=AsyncMock) as mock_limit, \
         patch("modules.pipeline.pipelines.router.create_pipeline", new_callable=AsyncMock, return_value=p) as mock_svc:
        result = await pipelines_router_module.create_pipeline_endpoint(
            payload=payload,
            request=request,
            user=user,
            repo=repo,
            stage_repo=stage_repo,
        )

    mock_limit.assert_awaited_once()
    mock_svc.assert_awaited_once_with(
        repo,
        stage_repo,
        owner_user_id=user.id,
        payload=payload,
    )
    assert result == p


@pytest.mark.asyncio
async def test_create_pipeline_returns_429_when_rate_limit_exceeded():
    user = _user()
    payload = PipelineCreate(name="Pipe B")
    request = FakeRequest()
    repo = AsyncMock()
    stage_repo = AsyncMock()

    with patch(
        "modules.pipeline.pipelines.router._limit",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=429, detail="Muitas tentativas."),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await pipelines_router_module.create_pipeline_endpoint(
                payload=payload,
                request=request,
                user=user,
                repo=repo,
                stage_repo=stage_repo,
            )

    assert exc_info.value.status_code == 429


# ── get_pipeline_detail ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_pipeline_detail_aggregates_via_service():
    pipeline = _pipeline()
    stage_repo = AsyncMock()
    card_repo = AsyncMock()
    detail = PipelineDetail(
        pipeline=pipeline,
        stage_counts=[],
        total_value_cents=0,
    )

    with patch(
        "modules.pipeline.pipelines.router.get_pipeline_detail",
        new_callable=AsyncMock,
        return_value=detail,
    ) as mock_svc:
        result = await pipelines_router_module.get_pipeline(
            pipeline=pipeline,
            stage_repo=stage_repo,
            card_repo=card_repo,
        )

    mock_svc.assert_awaited_once()
    assert result == detail


# ── update_pipeline ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_pipeline_delegates_to_service():
    pipeline = _pipeline()
    patch_payload = PipelinePatch(name="New Name")
    repo = AsyncMock()
    updated = _pipeline(id=pipeline.id, name="New Name")

    with patch(
        "modules.pipeline.pipelines.router.update_pipeline",
        new_callable=AsyncMock,
        return_value=updated,
    ) as mock_svc:
        result = await pipelines_router_module.update_pipeline_endpoint(
            payload=patch_payload,
            pipeline=pipeline,
            repo=repo,
        )

    mock_svc.assert_awaited_once_with(repo, pipeline_id=pipeline.id, payload=patch_payload)
    assert result == updated


# ── archive_pipeline ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_archive_pipeline():
    pipeline = _pipeline()
    repo = AsyncMock()
    archived = _pipeline(id=pipeline.id, archived_at=datetime.now(timezone.utc))

    with patch(
        "modules.pipeline.pipelines.router.archive_pipeline",
        new_callable=AsyncMock,
        return_value=archived,
    ) as mock_svc:
        result = await pipelines_router_module.archive_pipeline_endpoint(
            pipeline=pipeline,
            repo=repo,
        )

    mock_svc.assert_awaited_once_with(repo, pipeline)
    assert result == archived


# ── unarchive_pipeline ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unarchive_pipeline_when_archived():
    now = datetime.now(timezone.utc)
    pipeline = _pipeline(archived_at=now)
    repo = AsyncMock()
    unarchived = _pipeline(id=pipeline.id, archived_at=None)

    with patch(
        "modules.pipeline.pipelines.router.unarchive_pipeline",
        new_callable=AsyncMock,
        return_value=unarchived,
    ) as mock_svc:
        result = await pipelines_router_module.unarchive_pipeline_endpoint(
            pipeline=pipeline,
            repo=repo,
        )

    mock_svc.assert_awaited_once_with(repo, pipeline)
    assert result == unarchived


@pytest.mark.asyncio
async def test_unarchive_pipeline_when_active_raises_409():
    from modules.pipeline.errors import ErrorCode, pipeline_error

    pipeline = _pipeline(archived_at=None)
    repo = AsyncMock()

    with patch(
        "modules.pipeline.pipelines.router.unarchive_pipeline",
        new_callable=AsyncMock,
        side_effect=pipeline_error(ErrorCode.NOT_ARCHIVED),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await pipelines_router_module.unarchive_pipeline_endpoint(
                pipeline=pipeline,
                repo=repo,
            )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "not_archived"


# ── delete_pipeline ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_pipeline():
    pipeline = _pipeline()
    repo = AsyncMock()

    with patch(
        "modules.pipeline.pipelines.router.delete_pipeline",
        new_callable=AsyncMock,
    ) as mock_svc:
        result = await pipelines_router_module.delete_pipeline_endpoint(
            pipeline=pipeline,
            repo=repo,
        )

    mock_svc.assert_awaited_once_with(repo, pipeline_id=pipeline.id)
    assert result is None


# ── owned_pipeline dependency ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_owned_pipeline_dep_returns_404_when_not_found():
    from modules.pipeline.dependencies import owned_pipeline

    user = _user()
    repo = AsyncMock()
    repo.get_for_owner = AsyncMock(return_value=None)
    pipeline_id = uuid4()

    with pytest.raises(HTTPException) as exc_info:
        await owned_pipeline(pipeline_id=pipeline_id, user=user, repo=repo)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "pipeline_not_found"


@pytest.mark.asyncio
async def test_owned_pipeline_dep_returns_pipeline_when_found():
    from modules.pipeline.dependencies import owned_pipeline

    user = _user()
    pipeline = _pipeline(owner_user_id=user.id)
    repo = AsyncMock()
    repo.get_for_owner = AsyncMock(return_value=pipeline)

    result = await owned_pipeline(pipeline_id=pipeline.id, user=user, repo=repo)

    repo.get_for_owner.assert_awaited_once_with(pipeline.id, owner_user_id=user.id)
    assert result == pipeline


# ── _limit helper ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_limit_helper_passes_when_ok():
    from modules.pipeline.pipelines.router import _limit
    from types import SimpleNamespace

    limiter = AsyncMock()
    limiter.try_acquire.return_value = SimpleNamespace(ok=True, retry_after=0)

    with patch("modules.pipeline.pipelines.router.RateLimiter", return_value=limiter), \
         patch("modules.pipeline.pipelines.router.get_redis", return_value=object()):
        await _limit(FakeRequest(), "test:key", window=3600, max_count=10)

    limiter.try_acquire.assert_awaited_once()


@pytest.mark.asyncio
async def test_limit_helper_raises_429_when_exhausted():
    from modules.pipeline.pipelines.router import _limit
    from types import SimpleNamespace

    limiter = AsyncMock()
    limiter.try_acquire.return_value = SimpleNamespace(ok=False, retry_after=60)

    with patch("modules.pipeline.pipelines.router.RateLimiter", return_value=limiter), \
         patch("modules.pipeline.pipelines.router.get_redis", return_value=object()):
        with pytest.raises(HTTPException) as exc_info:
            await _limit(FakeRequest(), "test:key", window=3600, max_count=10)

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["Retry-After"] == "60"


# ── dependency factory coverage ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_pipeline_repo_creates_repo_with_pool():
    from modules.pipeline.dependencies import get_pipeline_repo
    from modules.pipeline.pipelines.repository import PipelineRepository

    fake_pool = object()
    with patch("modules.pipeline.dependencies.get_pool", new_callable=AsyncMock, return_value=fake_pool):
        repo = await get_pipeline_repo()

    assert isinstance(repo, PipelineRepository)
    assert repo._pool is fake_pool


@pytest.mark.asyncio
async def test_get_stage_repo_creates_repo_with_pool():
    from modules.pipeline.dependencies import get_stage_repo
    from modules.pipeline.stages.repository import StageRepository

    fake_pool = object()
    with patch("modules.pipeline.dependencies.get_pool", new_callable=AsyncMock, return_value=fake_pool):
        repo = await get_stage_repo()

    assert isinstance(repo, StageRepository)
    assert repo._pool is fake_pool


@pytest.mark.asyncio
async def test_get_card_repo_creates_repo_with_pool():
    from modules.pipeline.dependencies import get_card_repo
    from modules.pipeline.cards.repository import CardRepository

    fake_pool = object()
    with patch("modules.pipeline.dependencies.get_pool", new_callable=AsyncMock, return_value=fake_pool):
        repo = await get_card_repo()

    assert isinstance(repo, CardRepository)
    assert repo._pool is fake_pool
