"""Tests for StageRepository."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from modules.pipeline.stages.repository import StageRepository
from modules.pipeline.stages.schemas import StageRecord


# ---------------------------------------------------------------------------
# Helpers (local copy — do NOT import from test_pipelines_repository)
# ---------------------------------------------------------------------------


class _AcquireContext:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Transaction:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *args):
        return None


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _AcquireContext(self._conn)


def _mock_pool_with_conn():
    conn = AsyncMock()
    # transaction() must be a regular (non-async) call returning a context manager
    conn.transaction = MagicMock(return_value=_Transaction())
    pool = _FakePool(conn)
    return pool, conn


def _stage_row(**overrides):
    now = datetime.now(timezone.utc)
    base = {
        "id": uuid4(),
        "pipeline_id": uuid4(),
        "name": "Stage",
        "position": 0,
        "color": None,
        "is_won": False,
        "is_lost": False,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insert_returns_stage_record():
    pool, conn = _mock_pool_with_conn()
    pipeline_id = uuid4()
    conn.fetchrow.return_value = _stage_row(name="Lead", position=0)
    repo = StageRepository(pool)

    result = await repo.insert(
        pipeline_id=pipeline_id,
        name="Lead",
        position=0,
        color=None,
        is_won=False,
        is_lost=False,
    )

    assert isinstance(result, StageRecord)
    assert result.name == "Lead"

    call_args = conn.fetchrow.call_args[0]
    sql = call_args[0]
    args = call_args[1:]
    assert "INSERT INTO pipeline_stages" in sql
    assert "RETURNING" in sql
    assert pipeline_id in args
    assert "Lead" in args


@pytest.mark.asyncio
async def test_bulk_insert_returns_list_of_records():
    pool, conn = _mock_pool_with_conn()
    pipeline_id = uuid4()
    row1 = _stage_row(name="Qualificado", position=0)
    row2 = _stage_row(name="Proposta", position=1)
    conn.fetchrow.side_effect = [row1, row2]
    repo = StageRepository(pool)

    defaults = [
        {"name": "Qualificado", "position": 0, "color": None, "is_won": False, "is_lost": False},
        {"name": "Proposta", "position": 1, "color": None, "is_won": False, "is_lost": False},
    ]
    results = await repo.bulk_insert(pipeline_id, defaults)

    assert len(results) == 2
    assert all(isinstance(r, StageRecord) for r in results)
    assert results[0].name == "Qualificado"
    assert results[1].name == "Proposta"
    assert conn.fetchrow.call_count == 2


@pytest.mark.asyncio
async def test_list_for_pipeline_returns_ordered_stages():
    pool, conn = _mock_pool_with_conn()
    pipeline_id = uuid4()
    conn.fetch.return_value = [_stage_row(position=0), _stage_row(position=1)]
    repo = StageRepository(pool)

    results = await repo.list_for_pipeline(pipeline_id)

    assert len(results) == 2
    assert all(isinstance(r, StageRecord) for r in results)

    call_args = conn.fetch.call_args[0]
    sql = call_args[0]
    args = call_args[1:]
    assert "WHERE pipeline_id = $1" in sql
    assert "ORDER BY position" in sql
    assert args == (pipeline_id,)


@pytest.mark.asyncio
async def test_get_in_pipeline_returns_record_when_found():
    pool, conn = _mock_pool_with_conn()
    stage_id = uuid4()
    pipeline_id = uuid4()
    conn.fetchrow.return_value = _stage_row(id=stage_id)
    repo = StageRepository(pool)

    result = await repo.get_in_pipeline(stage_id, pipeline_id=pipeline_id)

    assert isinstance(result, StageRecord)

    sql = conn.fetchrow.call_args[0][0]
    assert "WHERE id = $1 AND pipeline_id = $2" in sql


@pytest.mark.asyncio
async def test_get_in_pipeline_returns_none_when_not_found():
    pool, conn = _mock_pool_with_conn()
    conn.fetchrow.return_value = None
    repo = StageRepository(pool)

    result = await repo.get_in_pipeline(uuid4(), pipeline_id=uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_update_uses_coalesce_and_updated_at():
    pool, conn = _mock_pool_with_conn()
    stage_id = uuid4()
    conn.fetchrow.return_value = _stage_row(name="Updated")
    repo = StageRepository(pool)

    result = await repo.update(stage_id, name="Updated", color=None, is_won=None, is_lost=None)

    assert isinstance(result, StageRecord)
    assert result.name == "Updated"

    sql = conn.fetchrow.call_args[0][0]
    assert "COALESCE" in sql
    assert "updated_at = now()" in sql


@pytest.mark.asyncio
async def test_count_stages_returns_int():
    pool, conn = _mock_pool_with_conn()
    pipeline_id = uuid4()
    conn.fetchval.return_value = 3
    repo = StageRepository(pool)

    result = await repo.count_stages(pipeline_id)

    assert result == 3

    call_args = conn.fetchval.call_args[0]
    sql = call_args[0]
    args = call_args[1:]
    assert "COUNT(*)" in sql
    assert "pipeline_stages" in sql
    assert args == (pipeline_id,)


@pytest.mark.asyncio
async def test_count_cards_in_stage_returns_int():
    pool, conn = _mock_pool_with_conn()
    stage_id = uuid4()
    conn.fetchval.return_value = 7
    repo = StageRepository(pool)

    result = await repo.count_cards_in_stage(stage_id)

    assert result == 7

    call_args = conn.fetchval.call_args[0]
    sql = call_args[0]
    args = call_args[1:]
    assert "COUNT(*)" in sql
    assert "pipeline_cards" in sql
    assert args == (stage_id,)


@pytest.mark.asyncio
async def test_reorder_sets_constraints_and_updates_positions():
    pool, conn = _mock_pool_with_conn()
    pipeline_id = uuid4()
    id1, id2, id3 = uuid4(), uuid4(), uuid4()
    stage_ids = [id1, id2, id3]
    repo = StageRepository(pool)

    await repo.reorder(pipeline_id, stage_ids)

    # SET CONSTRAINTS must be called
    execute_calls = conn.execute.call_args_list
    sqls = [c[0][0] for c in execute_calls]
    assert any("SET CONSTRAINTS" in s for s in sqls)

    # 3 UPDATEs with positions 0, 1, 2
    update_calls = [c for c in execute_calls if "UPDATE pipeline_stages" in c[0][0]]
    assert len(update_calls) == 3

    # Verify positions 0..2 were passed
    positions_passed = [c[0][2] for c in update_calls]  # $2 = position
    assert sorted(positions_passed) == [0, 1, 2]

    # Verify each stage_id was used
    ids_passed = [c[0][1] for c in update_calls]  # $1 = stage_id
    assert set(ids_passed) == {id1, id2, id3}


@pytest.mark.asyncio
async def test_move_cards_and_delete_flow():
    pool, conn = _mock_pool_with_conn()
    stage_id = uuid4()
    target_stage_id = uuid4()

    card1_id = uuid4()
    card2_id = uuid4()

    # fetchval returns max position in target
    conn.fetchval.return_value = 5
    # fetch returns cards in source stage
    conn.fetch.return_value = [{"id": card1_id}, {"id": card2_id}]

    repo = StageRepository(pool)

    await repo.move_cards_and_delete(stage_id, target_stage_id)

    execute_calls = conn.execute.call_args_list
    sqls = [c[0][0] for c in execute_calls]

    # SET CONSTRAINTS must be called
    assert any("SET CONSTRAINTS" in s for s in sqls)

    # Cards updated
    update_card_calls = [c for c in execute_calls if "UPDATE pipeline_cards" in c[0][0]]
    assert len(update_card_calls) == 2

    # Positions must be 6 and 7 (max+1, max+2)
    positions = sorted(c[0][3] for c in update_card_calls)  # $3 = position
    assert positions == [6, 7]

    # DELETE from pipeline_stages must happen
    delete_calls = [c for c in execute_calls if "DELETE FROM pipeline_stages" in c[0][0]]
    assert len(delete_calls) == 1
    assert delete_calls[0][0][1] == stage_id


@pytest.mark.asyncio
async def test_delete_executes_correct_sql():
    pool, conn = _mock_pool_with_conn()
    stage_id = uuid4()
    repo = StageRepository(pool)

    result = await repo.delete(stage_id)

    assert result is None

    call_args = conn.execute.call_args[0]
    sql = call_args[0]
    args = call_args[1:]
    assert "DELETE FROM pipeline_stages WHERE id = $1" in sql
    assert args == (stage_id,)


@pytest.mark.asyncio
async def test_max_position_in_pipeline_returns_value():
    pool, conn = _mock_pool_with_conn()
    pipeline_id = uuid4()
    conn.fetchval.return_value = 4
    repo = StageRepository(pool)

    result = await repo.max_position_in_pipeline(pipeline_id)

    assert result == 4

    call_args = conn.fetchval.call_args[0]
    sql = call_args[0]
    args = call_args[1:]
    assert "MAX(position)" in sql
    assert "pipeline_stages" in sql
    assert args == (pipeline_id,)


@pytest.mark.asyncio
async def test_max_position_in_pipeline_returns_none_when_empty():
    pool, conn = _mock_pool_with_conn()
    pipeline_id = uuid4()
    conn.fetchval.return_value = None
    repo = StageRepository(pool)

    result = await repo.max_position_in_pipeline(pipeline_id)

    assert result is None
