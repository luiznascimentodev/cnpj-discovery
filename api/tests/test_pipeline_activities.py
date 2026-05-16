"""Tests for pipeline card activities."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from modules.pipeline.activities.repository import ActivityRepository
from modules.pipeline.activities.schemas import (
    ActivityCreate,
    ActivityPatch,
    ActivityRecord,
)
from modules.pipeline.activities import router as activities_router_module
from modules.pipeline.activities.service import (
    create_activity,
    delete_activity,
    update_activity,
)
from modules.pipeline.cards.schemas import CardRecord


class _AcquireContext:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _AcquireContext(self._conn)


def _mock_pool():
    conn = AsyncMock()
    return _FakePool(conn), conn


def _activity_row(**overrides):
    now = datetime.now(timezone.utc)
    base = {
        "id": uuid4(),
        "card_id": uuid4(),
        "author_user_id": uuid4(),
        "kind": "note",
        "body": "Body",
        "occurred_at": now,
        "created_at": now,
    }
    base.update(overrides)
    return base


def _activity(**overrides):
    return ActivityRecord(**_activity_row(**overrides))


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


def _user(user_id=None):
    return type("User", (), {"id": user_id or uuid4()})()


@pytest.mark.asyncio
async def test_repository_insert_returns_activity_record():
    pool, conn = _mock_pool()
    card_id = uuid4()
    author_user_id = uuid4()
    occurred_at = datetime.now(timezone.utc)
    conn.fetchrow.return_value = _activity_row(
        card_id=card_id,
        author_user_id=author_user_id,
        kind="call",
        body="Called",
        occurred_at=occurred_at,
    )
    repo = ActivityRepository(pool)

    result = await repo.insert(
        card_id=card_id,
        author_user_id=author_user_id,
        kind="call",
        body="Called",
        occurred_at=occurred_at,
    )

    assert isinstance(result, ActivityRecord)
    assert result.kind == "call"
    sql = conn.fetchrow.call_args[0][0]
    assert "INSERT INTO pipeline_card_activities" in sql
    assert "COALESCE($5, now())" in sql
    assert "RETURNING" in sql


@pytest.mark.asyncio
async def test_repository_list_without_cursor_orders_by_occurred_at_desc():
    pool, conn = _mock_pool()
    card_id = uuid4()
    conn.fetch.return_value = [_activity_row(card_id=card_id)]
    repo = ActivityRepository(pool)

    result = await repo.list(card_id=card_id, cursor=None, limit=50)

    assert len(result) == 1
    assert isinstance(result[0], ActivityRecord)
    call_args = conn.fetch.call_args[0]
    sql = call_args[0]
    args = call_args[1:]
    assert "WHERE card_id = $1" in sql
    assert "ORDER BY occurred_at DESC" in sql
    assert "LIMIT $2" in sql
    assert args == (card_id, 50)


@pytest.mark.asyncio
async def test_repository_list_with_cursor_filters_older_records():
    pool, conn = _mock_pool()
    card_id = uuid4()
    cursor = datetime.now(timezone.utc) - timedelta(days=1)
    conn.fetch.return_value = [_activity_row(card_id=card_id)]
    repo = ActivityRepository(pool)

    result = await repo.list(card_id=card_id, cursor=cursor, limit=25)

    assert len(result) == 1
    sql = conn.fetch.call_args[0][0]
    args = conn.fetch.call_args[0][1:]
    assert "occurred_at < $2" in sql
    assert "LIMIT $3" in sql
    assert args == (card_id, cursor, 25)


@pytest.mark.asyncio
async def test_repository_get_returns_record_when_found():
    pool, conn = _mock_pool()
    activity_id = uuid4()
    card_id = uuid4()
    conn.fetchrow.return_value = _activity_row(id=activity_id, card_id=card_id)
    repo = ActivityRepository(pool)

    result = await repo.get(activity_id, card_id=card_id)

    assert isinstance(result, ActivityRecord)
    sql = conn.fetchrow.call_args[0][0]
    assert "WHERE id = $1 AND card_id = $2" in sql


@pytest.mark.asyncio
async def test_repository_get_returns_none_when_not_found():
    pool, conn = _mock_pool()
    conn.fetchrow.return_value = None
    repo = ActivityRepository(pool)

    result = await repo.get(uuid4(), card_id=uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_repository_get_in_card_delegates_to_get():
    pool, conn = _mock_pool()
    activity_id = uuid4()
    card_id = uuid4()
    conn.fetchrow.return_value = _activity_row(id=activity_id, card_id=card_id)
    repo = ActivityRepository(pool)

    result = await repo.get_in_card(activity_id, card_id=card_id)

    assert isinstance(result, ActivityRecord)
    assert conn.fetchrow.call_args[0][1:] == (activity_id, card_id)


@pytest.mark.asyncio
async def test_repository_update_returns_updated_record():
    pool, conn = _mock_pool()
    activity_id = uuid4()
    conn.fetchrow.return_value = _activity_row(id=activity_id, body="Updated")
    repo = ActivityRepository(pool)

    result = await repo.update(activity_id, body="Updated")

    assert result.body == "Updated"
    sql = conn.fetchrow.call_args[0][0]
    assert "UPDATE pipeline_card_activities" in sql
    assert "SET body = $2" in sql
    assert "RETURNING" in sql


@pytest.mark.asyncio
async def test_repository_delete_executes_delete():
    pool, conn = _mock_pool()
    activity_id = uuid4()
    repo = ActivityRepository(pool)

    result = await repo.delete(activity_id)

    assert result is None
    sql = conn.execute.call_args[0][0]
    args = conn.execute.call_args[0][1:]
    assert "DELETE FROM pipeline_card_activities" in sql
    assert args == (activity_id,)


@pytest.mark.asyncio
async def test_create_activity_delegates_author_to_current_user():
    card_id = uuid4()
    user = _user()
    occurred_at = datetime.now(timezone.utc)
    payload = ActivityCreate(kind="email", body="Sent", occurred_at=occurred_at)
    created = _activity(card_id=card_id, author_user_id=user.id, kind="email")
    repo = AsyncMock()
    repo.insert.return_value = created

    result = await create_activity(
        repo,
        card_id=card_id,
        payload=payload,
        current_user=user,
    )

    repo.insert.assert_awaited_once_with(
        card_id=card_id,
        author_user_id=user.id,
        kind="email",
        body="Sent",
        occurred_at=occurred_at,
    )
    assert result == created


@pytest.mark.asyncio
async def test_update_activity_delegates_to_repo():
    activity = _activity()
    updated = _activity(id=activity.id, card_id=activity.card_id, body="Updated")
    repo = AsyncMock()
    repo.update.return_value = updated
    payload = ActivityPatch(body="Updated")

    result = await update_activity(repo, activity=activity, payload=payload)

    repo.update.assert_awaited_once_with(activity.id, body="Updated")
    assert result == updated


@pytest.mark.asyncio
async def test_delete_activity_delegates_to_repo():
    activity = _activity()
    repo = AsyncMock()

    result = await delete_activity(repo, activity=activity)

    repo.delete.assert_awaited_once_with(activity.id)
    assert result is None


@pytest.mark.asyncio
async def test_list_activities_endpoint_uses_card_and_pagination():
    card = _card()
    rows = [_activity(card_id=card.id)]
    repo = AsyncMock()
    repo.list.return_value = rows
    cursor = datetime.now(timezone.utc)

    result = await activities_router_module.list_activities(
        cursor=cursor,
        limit=20,
        card=card,
        repo=repo,
    )

    repo.list.assert_awaited_once_with(card_id=card.id, cursor=cursor, limit=20)
    assert result == rows


@pytest.mark.asyncio
async def test_create_activity_endpoint_delegates_to_service():
    card = _card()
    user = _user()
    payload = ActivityCreate(kind="meeting", body="Met")
    repo = AsyncMock()
    created = _activity(card_id=card.id, author_user_id=user.id, kind="meeting")

    with patch(
        "modules.pipeline.activities.router.create_activity",
        new_callable=AsyncMock,
        return_value=created,
    ) as mock_svc:
        result = await activities_router_module.create_activity_endpoint(
            payload=payload,
            card=card,
            repo=repo,
            current_user=user,
        )

    mock_svc.assert_awaited_once_with(
        repo,
        card_id=card.id,
        payload=payload,
        current_user=user,
    )
    assert result == created


@pytest.mark.asyncio
async def test_update_activity_endpoint_delegates_to_service():
    activity = _activity()
    payload = ActivityPatch(body="Updated")
    repo = AsyncMock()
    updated = _activity(id=activity.id, card_id=activity.card_id, body="Updated")

    with patch(
        "modules.pipeline.activities.router.update_activity",
        new_callable=AsyncMock,
        return_value=updated,
    ) as mock_svc:
        result = await activities_router_module.update_activity_endpoint(
            payload=payload,
            activity=activity,
            repo=repo,
        )

    mock_svc.assert_awaited_once_with(repo, activity=activity, payload=payload)
    assert result == updated


@pytest.mark.asyncio
async def test_delete_activity_endpoint_delegates_to_service():
    activity = _activity()
    repo = AsyncMock()

    with patch(
        "modules.pipeline.activities.router.delete_activity",
        new_callable=AsyncMock,
    ) as mock_svc:
        result = await activities_router_module.delete_activity_endpoint(
            activity=activity,
            repo=repo,
        )

    mock_svc.assert_awaited_once_with(repo, activity=activity)
    assert result is None


@pytest.mark.asyncio
async def test_get_activity_repo_builds_repository():
    from modules.pipeline.dependencies import get_activity_repo

    pool = object()

    with patch(
        "modules.pipeline.dependencies.get_pool",
        new_callable=AsyncMock,
        return_value=pool,
    ):
        repo = await get_activity_repo()

    assert isinstance(repo, ActivityRepository)
    assert repo._pool is pool


@pytest.mark.asyncio
async def test_owned_activity_returns_activity_when_found():
    from modules.pipeline.dependencies import owned_activity

    card = _card()
    activity = _activity(card_id=card.id)
    repo = AsyncMock()
    repo.get_in_card.return_value = activity

    result = await owned_activity(activity_id=activity.id, card=card, repo=repo)

    repo.get_in_card.assert_awaited_once_with(activity.id, card_id=card.id)
    assert result == activity


@pytest.mark.asyncio
async def test_owned_activity_raises_404_when_not_found():
    from modules.pipeline.dependencies import owned_activity

    repo = AsyncMock()
    repo.get_in_card.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await owned_activity(activity_id=uuid4(), card=_card(), repo=repo)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "activity_not_found"
