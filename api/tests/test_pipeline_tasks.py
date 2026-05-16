"""Tests for pipeline tasks repository, service, router, and schemas."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from modules.auth.schemas import UserRecord
from modules.pipeline.cards.schemas import CardRecord
from modules.pipeline.tasks.repository import TaskRepository
from modules.pipeline.tasks import router as tasks_router_module
from modules.pipeline.tasks.schemas import TaskCreate, TaskPatch, TaskRecord
from modules.pipeline.tasks.service import create_task, delete_task, update_task


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
    conn.transaction = MagicMock()
    return _FakePool(conn), conn


def _task_row(**overrides):
    now = datetime.now(timezone.utc)
    base = {
        "id": uuid4(),
        "card_id": uuid4(),
        "assignee_user_id": uuid4(),
        "title": "Follow up",
        "due_at": None,
        "done_at": None,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return base


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


def _task(**overrides):
    return TaskRecord(**_task_row(**overrides))


def _user(**overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id=uuid4(),
        email="user@example.com",
        password_hash="hash",
        name="User",
        email_verified_at=now,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )
    base.update(overrides)
    return UserRecord(**base)


def test_task_create_defaults_assignee_to_none():
    due_at = datetime.now(timezone.utc)

    payload = TaskCreate(title="Call lead", due_at=due_at)

    assert payload.title == "Call lead"
    assert payload.due_at == due_at
    assert payload.assignee_user_id is None


def test_task_create_rejects_blank_title():
    with pytest.raises(ValidationError):
        TaskCreate(title="")


def test_task_patch_accepts_partial_payload():
    payload = TaskPatch(done_at=datetime.now(timezone.utc))

    assert payload.title is None
    assert payload.due_at is None
    assert payload.done_at is not None


@pytest.mark.asyncio
async def test_insert_returns_task_record():
    pool, conn = _mock_pool()
    card_id = uuid4()
    assignee_user_id = uuid4()
    due_at = datetime.now(timezone.utc)
    conn.fetchrow.return_value = _task_row(
        card_id=card_id,
        assignee_user_id=assignee_user_id,
        title="Call",
        due_at=due_at,
    )
    repo = TaskRepository(pool)

    result = await repo.insert(
        card_id=card_id,
        assignee_user_id=assignee_user_id,
        title="Call",
        due_at=due_at,
    )

    assert isinstance(result, TaskRecord)
    assert result.title == "Call"
    sql = conn.fetchrow.call_args[0][0]
    args = conn.fetchrow.call_args[0][1:]
    assert "INSERT INTO pipeline_card_tasks" in sql
    assert "RETURNING" in sql
    assert args == (card_id, assignee_user_id, "Call", due_at)


@pytest.mark.asyncio
async def test_list_for_card_returns_ordered_task_records():
    pool, conn = _mock_pool()
    card_id = uuid4()
    conn.fetch.return_value = [_task_row(card_id=card_id), _task_row(card_id=card_id)]
    repo = TaskRepository(pool)

    result = await repo.list_for_card(card_id)

    assert len(result) == 2
    assert all(isinstance(task, TaskRecord) for task in result)
    sql = conn.fetch.call_args[0][0]
    assert "WHERE card_id = $1" in sql
    assert "ORDER BY done_at NULLS FIRST" in sql
    assert conn.fetch.call_args[0][1:] == (card_id,)


@pytest.mark.asyncio
async def test_get_in_card_returns_record_when_found():
    pool, conn = _mock_pool()
    task_id = uuid4()
    card_id = uuid4()
    conn.fetchrow.return_value = _task_row(id=task_id, card_id=card_id)
    repo = TaskRepository(pool)

    result = await repo.get_in_card(task_id, card_id=card_id)

    assert isinstance(result, TaskRecord)
    sql = conn.fetchrow.call_args[0][0]
    assert "WHERE id = $1 AND card_id = $2" in sql
    assert conn.fetchrow.call_args[0][1:] == (task_id, card_id)


@pytest.mark.asyncio
async def test_get_in_card_returns_none_when_missing():
    pool, conn = _mock_pool()
    conn.fetchrow.return_value = None
    repo = TaskRepository(pool)

    result = await repo.get_in_card(uuid4(), card_id=uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_update_uses_coalesce_and_updated_at():
    pool, conn = _mock_pool()
    task_id = uuid4()
    done_at = datetime.now(timezone.utc)
    conn.fetchrow.return_value = _task_row(id=task_id, title="Done", done_at=done_at)
    repo = TaskRepository(pool)

    result = await repo.update(task_id, title="Done", due_at=None, done_at=done_at)

    assert isinstance(result, TaskRecord)
    assert result.done_at == done_at
    sql = conn.fetchrow.call_args[0][0]
    assert "UPDATE pipeline_card_tasks" in sql
    assert "COALESCE" in sql
    assert "updated_at = now()" in sql
    assert "RETURNING" in sql


@pytest.mark.asyncio
async def test_delete_executes_delete_sql():
    pool, conn = _mock_pool()
    task_id = uuid4()
    repo = TaskRepository(pool)

    result = await repo.delete(task_id)

    assert result is None
    assert "DELETE FROM pipeline_card_tasks WHERE id = $1" in conn.execute.call_args[0][0]
    assert conn.execute.call_args[0][1:] == (task_id,)


@pytest.mark.asyncio
async def test_list_open_for_assignee_returns_open_tasks():
    pool, conn = _mock_pool()
    assignee_user_id = uuid4()
    conn.fetch.return_value = [_task_row(assignee_user_id=assignee_user_id)]
    repo = TaskRepository(pool)

    result = await repo.list_open_for_assignee(assignee_user_id)

    assert len(result) == 1
    assert isinstance(result[0], TaskRecord)
    sql = conn.fetch.call_args[0][0]
    assert "assignee_user_id = $1" in sql
    assert "done_at IS NULL" in sql
    assert "ORDER BY due_at NULLS LAST" in sql
    assert conn.fetch.call_args[0][1:] == (assignee_user_id,)


@pytest.mark.asyncio
async def test_create_task_defaults_assignee_to_current_user():
    card = _card()
    user = _user()
    created = _task(card_id=card.id, assignee_user_id=user.id, title="Call")
    repo = AsyncMock()
    repo.insert.return_value = created
    payload = TaskCreate(title="Call")

    result = await create_task(repo, card=card, payload=payload, current_user=user)

    repo.insert.assert_awaited_once_with(
        card_id=card.id,
        assignee_user_id=user.id,
        title="Call",
        due_at=None,
    )
    assert result == created


@pytest.mark.asyncio
async def test_create_task_uses_payload_assignee_when_present():
    card = _card()
    user = _user()
    assignee_user_id = uuid4()
    due_at = datetime.now(timezone.utc)
    created = _task(card_id=card.id, assignee_user_id=assignee_user_id, due_at=due_at)
    repo = AsyncMock()
    repo.insert.return_value = created
    payload = TaskCreate(title="Call", due_at=due_at, assignee_user_id=assignee_user_id)

    result = await create_task(repo, card=card, payload=payload, current_user=user)

    repo.insert.assert_awaited_once_with(
        card_id=card.id,
        assignee_user_id=assignee_user_id,
        title="Call",
        due_at=due_at,
    )
    assert result == created


@pytest.mark.asyncio
async def test_update_task_delegates_to_repository():
    task = _task()
    done_at = datetime.now(timezone.utc)
    updated = _task(id=task.id, title="Updated", done_at=done_at)
    repo = AsyncMock()
    repo.update.return_value = updated
    payload = TaskPatch(title="Updated", done_at=done_at)

    result = await update_task(repo, task=task, payload=payload)

    repo.update.assert_awaited_once_with(
        task.id,
        title="Updated",
        due_at=None,
        done_at=done_at,
    )
    assert result == updated


@pytest.mark.asyncio
async def test_delete_task_delegates_to_repository():
    task = _task()
    repo = AsyncMock()

    result = await delete_task(repo, task=task)

    repo.delete.assert_awaited_once_with(task.id)
    assert result is None


@pytest.mark.asyncio
async def test_list_tasks_endpoint_returns_card_tasks():
    card = _card()
    tasks = [_task(card_id=card.id)]
    repo = AsyncMock()
    repo.list_for_card.return_value = tasks

    result = await tasks_router_module.list_tasks(card=card, repo=repo)

    repo.list_for_card.assert_awaited_once_with(card.id)
    assert result == tasks


@pytest.mark.asyncio
async def test_create_task_endpoint_delegates_to_service():
    card = _card()
    user = _user()
    payload = TaskCreate(title="Call")
    repo = AsyncMock()
    created = _task(card_id=card.id, assignee_user_id=user.id)

    with patch(
        "modules.pipeline.tasks.router.create_task",
        new_callable=AsyncMock,
        return_value=created,
    ) as mock_svc:
        result = await tasks_router_module.create_task_endpoint(
            payload=payload,
            card=card,
            current_user=user,
            repo=repo,
        )

    mock_svc.assert_awaited_once_with(
        repo,
        card=card,
        payload=payload,
        current_user=user,
    )
    assert result == created


@pytest.mark.asyncio
async def test_update_task_endpoint_delegates_to_service():
    task = _task()
    payload = TaskPatch(title="Updated")
    repo = AsyncMock()
    updated = _task(id=task.id, title="Updated")

    with patch(
        "modules.pipeline.tasks.router.update_task",
        new_callable=AsyncMock,
        return_value=updated,
    ) as mock_svc:
        result = await tasks_router_module.update_task_endpoint(
            payload=payload,
            task=task,
            repo=repo,
        )

    mock_svc.assert_awaited_once_with(repo, task=task, payload=payload)
    assert result == updated


@pytest.mark.asyncio
async def test_delete_task_endpoint_delegates_to_service():
    task = _task()
    repo = AsyncMock()

    with patch(
        "modules.pipeline.tasks.router.delete_task",
        new_callable=AsyncMock,
    ) as mock_svc:
        result = await tasks_router_module.delete_task_endpoint(task=task, repo=repo)

    mock_svc.assert_awaited_once_with(repo, task=task)
    assert result is None


@pytest.mark.asyncio
async def test_list_my_open_tasks_returns_current_user_tasks():
    user = _user()
    tasks = [_task(assignee_user_id=user.id)]
    repo = AsyncMock()
    repo.list_open_for_assignee.return_value = tasks

    result = await tasks_router_module.list_my_open_tasks(current_user=user, repo=repo)

    repo.list_open_for_assignee.assert_awaited_once_with(user.id)
    assert result == tasks


def test_router_includes_card_tasks_and_mine_routes():
    paths = {route.path for route in tasks_router_module.router.routes}

    assert "/pipelines/{pipeline_id}/cards/{card_id}/tasks" in paths
    assert "/pipelines/{pipeline_id}/cards/{card_id}/tasks/{task_id}" in paths
    assert "/pipelines/tasks/mine" in paths


@pytest.mark.asyncio
async def test_get_task_repo_creates_repository_with_pool():
    from modules.pipeline.dependencies import get_task_repo

    fake_pool = object()
    with patch("modules.pipeline.dependencies.get_pool", new_callable=AsyncMock, return_value=fake_pool):
        repo = await get_task_repo()

    assert isinstance(repo, TaskRepository)
    assert repo._pool is fake_pool


@pytest.mark.asyncio
async def test_owned_task_returns_task_when_found():
    from modules.pipeline.dependencies import owned_task

    card = _card()
    task = _task(card_id=card.id)
    repo = AsyncMock()
    repo.get_in_card.return_value = task

    result = await owned_task(task_id=task.id, card=card, repo=repo)

    repo.get_in_card.assert_awaited_once_with(task.id, card_id=card.id)
    assert result == task


@pytest.mark.asyncio
async def test_owned_task_raises_404_when_not_found():
    from modules.pipeline.dependencies import owned_task

    repo = AsyncMock()
    repo.get_in_card.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await owned_task(task_id=uuid4(), card=_card(), repo=repo)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "task_not_found"
