"""Tests for PipelineRepository."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from modules.pipeline.pipelines.repository import PipelineRepository
from modules.pipeline.pipelines.schemas import PipelineRecord


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


def _mock_pool_with_conn():
    conn = AsyncMock()
    pool = _FakePool(conn)
    return pool, conn


def _row(**overrides):
    now = datetime.now(timezone.utc)
    base = {
        "id": uuid4(),
        "owner_user_id": uuid4(),
        "name": "X",
        "description": None,
        "archived_at": None,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_insert_runs_correct_sql_and_returns_record():
    pool, conn = _mock_pool_with_conn()
    owner_id = uuid4()
    conn.fetchrow.return_value = _row(name="Sales")
    repo = PipelineRepository(pool)

    result = await repo.insert(owner_user_id=owner_id, name="Sales", description="desc")

    assert isinstance(result, PipelineRecord)
    assert result.name == "Sales"

    call_args = conn.fetchrow.call_args
    sql = call_args[0][0]
    args = call_args[0][1:]
    assert "INSERT INTO pipelines" in sql
    assert args == (owner_id, "Sales", "desc")


@pytest.mark.asyncio
async def test_get_for_owner_returns_record_when_found():
    pool, conn = _mock_pool_with_conn()
    pipeline_id = uuid4()
    owner_id = uuid4()
    conn.fetchrow.return_value = _row()
    repo = PipelineRepository(pool)

    result = await repo.get_for_owner(pipeline_id, owner_user_id=owner_id)

    assert isinstance(result, PipelineRecord)

    sql = conn.fetchrow.call_args[0][0]
    assert "WHERE id = $1 AND owner_user_id = $2" in sql


@pytest.mark.asyncio
async def test_get_for_owner_returns_none_when_not_found():
    pool, conn = _mock_pool_with_conn()
    conn.fetchrow.return_value = None
    repo = PipelineRepository(pool)

    result = await repo.get_for_owner(uuid4(), owner_user_id=uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_list_for_owner_without_archived():
    pool, conn = _mock_pool_with_conn()
    owner_id = uuid4()
    conn.fetch.return_value = [_row(), _row()]
    repo = PipelineRepository(pool)

    results = await repo.list_for_owner(owner_id, include_archived=False)

    assert len(results) == 2
    assert all(isinstance(r, PipelineRecord) for r in results)

    call_args = conn.fetch.call_args[0]
    sql = call_args[0]
    args = call_args[1:]
    assert "ORDER BY created_at DESC" in sql
    assert args == (owner_id, False)


@pytest.mark.asyncio
async def test_list_for_owner_with_archived():
    pool, conn = _mock_pool_with_conn()
    owner_id = uuid4()
    conn.fetch.return_value = []
    repo = PipelineRepository(pool)

    results = await repo.list_for_owner(owner_id, include_archived=True)

    assert results == []

    call_args = conn.fetch.call_args[0]
    args = call_args[1:]
    assert args == (owner_id, True)


@pytest.mark.asyncio
async def test_update_runs_with_coalesce():
    pool, conn = _mock_pool_with_conn()
    pipeline_id = uuid4()
    conn.fetchrow.return_value = _row(name="New")
    repo = PipelineRepository(pool)

    result = await repo.update(pipeline_id, name="New", description=None)

    assert isinstance(result, PipelineRecord)
    assert result.name == "New"

    sql = conn.fetchrow.call_args[0][0]
    assert "COALESCE" in sql
    assert "updated_at = now()" in sql


@pytest.mark.asyncio
async def test_archive_sets_archived_at():
    pool, conn = _mock_pool_with_conn()
    pipeline_id = uuid4()
    now = datetime.now(timezone.utc)
    conn.fetchrow.return_value = _row(archived_at=now)
    repo = PipelineRepository(pool)

    result = await repo.archive(pipeline_id)

    assert isinstance(result, PipelineRecord)
    assert result.archived_at is not None

    sql = conn.fetchrow.call_args[0][0]
    assert "archived_at = now()" in sql


@pytest.mark.asyncio
async def test_unarchive_clears_archived_at():
    pool, conn = _mock_pool_with_conn()
    pipeline_id = uuid4()
    conn.fetchrow.return_value = _row(archived_at=None)
    repo = PipelineRepository(pool)

    result = await repo.unarchive(pipeline_id)

    assert isinstance(result, PipelineRecord)
    assert result.archived_at is None

    sql = conn.fetchrow.call_args[0][0]
    assert "archived_at = NULL" in sql


@pytest.mark.asyncio
async def test_delete_executes_correct_sql():
    pool, conn = _mock_pool_with_conn()
    pipeline_id = uuid4()
    repo = PipelineRepository(pool)

    result = await repo.delete(pipeline_id)

    assert result is None

    call_args = conn.execute.call_args[0]
    sql = call_args[0]
    args = call_args[1:]
    assert "DELETE FROM pipelines WHERE id = $1" in sql
    assert args == (pipeline_id,)


@pytest.mark.asyncio
async def test_count_for_owner_returns_int():
    pool, conn = _mock_pool_with_conn()
    owner_id = uuid4()
    conn.fetchval.return_value = 5
    repo = PipelineRepository(pool)

    result = await repo.count_for_owner(owner_id)

    assert result == 5

    call_args = conn.fetchval.call_args[0]
    sql = call_args[0]
    args = call_args[1:]
    assert "COUNT(*)" in sql
    assert "WHERE owner_user_id = $1 AND archived_at IS NULL" in sql
    assert args == (owner_id,)
