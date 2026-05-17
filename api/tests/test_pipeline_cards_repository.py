"""Tests for CardRepository."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from modules.pipeline.cards.repository import CardRepository
from modules.pipeline.cards.schemas import (
    CardInPipelineSummary,
    CardRecord,
    CardWithCompany,
    ImportBatchRecord,
    ImportRowRecord,
)


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_pipeline_stages_repository)
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


def _mock_pool():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_Transaction())
    pool = _FakePool(conn)
    return pool, conn


def _card_row(**overrides):
    now = datetime.now(timezone.utc)
    base = {
        "id": uuid4(),
        "pipeline_id": uuid4(),
        "stage_id": uuid4(),
        "cnpj_basico": "12345678",
        "position": 0,
        "estimated_value_cents": None,
        "notes": None,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return base


def _import_batch_row(**overrides):
    now = datetime.now(timezone.utc)
    base = {
        "id": uuid4(),
        "pipeline_id": uuid4(),
        "owner_user_id": uuid4(),
        "stage_id": uuid4(),
        "filename": "cards.csv",
        "file_size_bytes": 100,
        "content_sha256": "a" * 64,
        "total_rows": 1,
        "created_count": 1,
        "skipped_count": 0,
        "created_at": now,
    }
    base.update(overrides)
    return base


def _import_row(**overrides):
    now = datetime.now(timezone.utc)
    base = {
        "id": 1,
        "batch_id": uuid4(),
        "line_number": 2,
        "raw_cnpj": "12.345.678/0001-00",
        "cnpj_basico": "12345678",
        "display_name": "Lead",
        "card_id": uuid4(),
        "status": "created",
        "reason": None,
        "metadata": {"segmento": "SaaS"},
        "created_at": now,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cnpj_exists_returns_true():
    pool, conn = _mock_pool()
    conn.fetchval.return_value = True
    repo = CardRepository(pool)

    result = await repo.cnpj_exists("12345678")

    assert result is True
    sql = conn.fetchval.call_args[0][0]
    assert "EXISTS" in sql
    assert "empresas" in sql
    assert "cnpj_basico = $1" in sql


@pytest.mark.asyncio
async def test_cnpj_exists_returns_false():
    pool, conn = _mock_pool()
    conn.fetchval.return_value = False
    repo = CardRepository(pool)

    result = await repo.cnpj_exists("99999999")

    assert result is False


@pytest.mark.asyncio
async def test_existing_cnpjs_returns_set():
    pool, conn = _mock_pool()
    conn.fetch.return_value = [{"cnpj_basico": "12345678"}, {"cnpj_basico": "87654321"}]
    repo = CardRepository(pool)

    result = await repo.existing_cnpjs(["12345678", "87654321", "00000001"])

    assert result == {"12345678", "87654321"}
    sql = conn.fetch.call_args[0][0]
    assert "empresas" in sql
    assert "ANY($1" in sql


@pytest.mark.asyncio
async def test_existing_cnpjs_in_basico_delegates_to_existing_cnpjs():
    pool, conn = _mock_pool()
    conn.fetch.return_value = [{"cnpj_basico": "12345678"}]
    repo = CardRepository(pool)

    result = await repo.existing_cnpjs_in_basico(["12345678"])

    assert result == {"12345678"}


@pytest.mark.asyncio
async def test_card_exists_in_pipeline_returns_bool():
    pool, conn = _mock_pool()
    pipeline_id = uuid4()
    conn.fetchval.return_value = True
    repo = CardRepository(pool)

    result = await repo.card_exists_in_pipeline(pipeline_id, "12345678")

    assert result is True
    sql = conn.fetchval.call_args[0][0]
    assert "pipeline_cards" in sql
    assert "pipeline_id = $1" in sql
    assert "cnpj_basico = $2" in sql


@pytest.mark.asyncio
async def test_existing_cards_in_pipeline_by_cnpj_returns_set():
    pool, conn = _mock_pool()
    pipeline_id = uuid4()
    conn.fetch.return_value = [{"cnpj_basico": "12345678"}]
    repo = CardRepository(pool)

    result = await repo.existing_cards_in_pipeline_by_cnpj(
        pipeline_id, ["12345678", "99999999"]
    )

    assert result == {"12345678"}
    sql = conn.fetch.call_args[0][0]
    assert "pipeline_cards" in sql
    assert "pipeline_id = $1" in sql
    assert "ANY($2" in sql


@pytest.mark.asyncio
async def test_existing_card_ids_in_pipeline_by_cnpj_returns_mapping():
    pool, conn = _mock_pool()
    pipeline_id = uuid4()
    card_id = uuid4()
    conn.fetch.return_value = [{"cnpj_basico": "12345678", "id": card_id}]
    repo = CardRepository(pool)

    result = await repo.existing_card_ids_in_pipeline_by_cnpj(
        pipeline_id, ["12345678", "99999999"]
    )

    assert result == {"12345678": card_id}
    sql = conn.fetch.call_args[0][0]
    assert "SELECT cnpj_basico, id" in sql
    assert "pipeline_cards" in sql


@pytest.mark.asyncio
async def test_insert_returns_card_record():
    pool, conn = _mock_pool()
    pipeline_id = uuid4()
    stage_id = uuid4()
    conn.fetchrow.return_value = _card_row(
        pipeline_id=pipeline_id, stage_id=stage_id, cnpj_basico="12345678"
    )
    repo = CardRepository(pool)

    result = await repo.insert(
        pipeline_id=pipeline_id,
        stage_id=stage_id,
        cnpj_basico="12345678",
        position=0,
        display_name="Lead A",
        estimated_value_cents=None,
        notes=None,
    )

    assert isinstance(result, CardRecord)
    assert result.cnpj_basico == "12345678"

    sql = conn.fetchrow.call_args[0][0]
    assert "INSERT INTO pipeline_cards" in sql
    assert "display_name" in sql
    assert "RETURNING" in sql


@pytest.mark.asyncio
async def test_bulk_insert_returns_ordered_list():
    pool, conn = _mock_pool()
    pipeline_id = uuid4()
    stage_id = uuid4()
    row1 = _card_row(cnpj_basico="11111111", position=0)
    row2 = _card_row(cnpj_basico="22222222", position=1)
    conn.fetchrow.side_effect = [row1, row2]
    repo = CardRepository(pool)

    rows = [
        {
            "pipeline_id": pipeline_id,
            "stage_id": stage_id,
            "cnpj_basico": "11111111",
            "position": 0,
            "display_name": "Lead 1",
            "estimated_value_cents": None,
            "notes": None,
        },
        {
            "pipeline_id": pipeline_id,
            "stage_id": stage_id,
            "cnpj_basico": "22222222",
            "position": 1,
            "display_name": "Lead 2",
            "estimated_value_cents": None,
            "notes": None,
        },
    ]
    results = await repo.bulk_insert(rows)

    assert len(results) == 2
    assert all(isinstance(r, CardRecord) for r in results)
    assert results[0].cnpj_basico == "11111111"
    assert results[1].cnpj_basico == "22222222"


@pytest.mark.asyncio
async def test_bulk_insert_empty_returns_empty_list():
    pool, conn = _mock_pool()
    repo = CardRepository(pool)

    results = await repo.bulk_insert([])

    assert results == []
    conn.fetchrow.assert_not_called()


@pytest.mark.asyncio
async def test_list_with_company_summary_empty():
    pool, conn = _mock_pool()
    pipeline_id = uuid4()
    conn.fetch.return_value = []
    repo = CardRepository(pool)

    results = await repo.list_with_company_summary(pipeline_id)

    assert results == []
    sql = conn.fetch.call_args[0][0]
    assert "LEFT JOIN empresas" in sql
    assert "LATERAL" in sql
    assert "identificador_matriz_filial" in sql
    assert "ORDER BY c.stage_id, c.position" in sql


@pytest.mark.asyncio
async def test_list_with_company_summary_populated():
    pool, conn = _mock_pool()
    pipeline_id = uuid4()
    card_data = _card_row(pipeline_id=pipeline_id)
    row = dict(card_data)
    row["razao_social"] = "Empresa Teste Ltda"
    row["uf"] = "SP"
    conn.fetch.return_value = [row]
    repo = CardRepository(pool)

    results = await repo.list_with_company_summary(pipeline_id)

    assert len(results) == 1
    assert isinstance(results[0], CardWithCompany)
    assert isinstance(results[0].card, CardRecord)
    assert results[0].company.razao_social == "Empresa Teste Ltda"
    assert results[0].company.uf == "SP"


@pytest.mark.asyncio
async def test_get_in_pipeline_returns_record():
    pool, conn = _mock_pool()
    card_id = uuid4()
    pipeline_id = uuid4()
    conn.fetchrow.return_value = _card_row(id=card_id, pipeline_id=pipeline_id)
    repo = CardRepository(pool)

    result = await repo.get_in_pipeline(card_id, pipeline_id=pipeline_id)

    assert isinstance(result, CardRecord)
    sql = conn.fetchrow.call_args[0][0]
    assert "WHERE id = $1 AND pipeline_id = $2" in sql


@pytest.mark.asyncio
async def test_get_in_pipeline_returns_none_when_not_found():
    pool, conn = _mock_pool()
    conn.fetchrow.return_value = None
    repo = CardRepository(pool)

    result = await repo.get_in_pipeline(uuid4(), pipeline_id=uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_update_uses_coalesce_and_returning():
    pool, conn = _mock_pool()
    card_id = uuid4()
    conn.fetchrow.return_value = _card_row(id=card_id, estimated_value_cents=5000)
    repo = CardRepository(pool)

    result = await repo.update(
        card_id,
        display_name="Lead",
        estimated_value_cents=5000,
        notes="test",
    )

    assert isinstance(result, CardRecord)
    sql = conn.fetchrow.call_args[0][0]
    assert "UPDATE pipeline_cards" in sql
    assert "COALESCE" in sql
    assert "RETURNING" in sql


@pytest.mark.asyncio
async def test_move_uses_deferred_constraints_in_transaction():
    pool, conn = _mock_pool()
    card_id = uuid4()
    new_stage_id = uuid4()
    conn.fetchrow.return_value = _card_row(stage_id=new_stage_id, position=3)
    repo = CardRepository(pool)

    result = await repo.move(card_id, stage_id=new_stage_id, position=3)

    assert isinstance(result, CardRecord)
    assert result.position == 3

    execute_calls = conn.execute.call_args_list
    assert any("SET CONSTRAINTS" in c[0][0] for c in execute_calls)

    sql = conn.fetchrow.call_args[0][0]
    assert "UPDATE pipeline_cards" in sql
    assert "RETURNING" in sql
    assert "updated_at" in sql


@pytest.mark.asyncio
async def test_delete_executes_correct_sql():
    pool, conn = _mock_pool()
    card_id = uuid4()
    repo = CardRepository(pool)

    result = await repo.delete(card_id)

    assert result is None
    sql = conn.execute.call_args[0][0]
    assert "DELETE FROM pipeline_cards WHERE id = $1" in sql
    assert conn.execute.call_args[0][1] == card_id


@pytest.mark.asyncio
async def test_max_position_in_stage_returns_value():
    pool, conn = _mock_pool()
    stage_id = uuid4()
    conn.fetchval.return_value = 5
    repo = CardRepository(pool)

    result = await repo.max_position_in_stage(stage_id)

    assert result == 5
    sql = conn.fetchval.call_args[0][0]
    assert "MAX(position)" in sql
    assert "pipeline_cards" in sql
    assert "stage_id = $1" in sql


@pytest.mark.asyncio
async def test_max_position_in_stage_returns_none_when_empty():
    pool, conn = _mock_pool()
    conn.fetchval.return_value = None
    repo = CardRepository(pool)

    result = await repo.max_position_in_stage(uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_first_stage_id_in_pipeline_returns_stage_id():
    pool, conn = _mock_pool()
    pipeline_id = uuid4()
    stage_id = uuid4()
    conn.fetchval.return_value = stage_id
    repo = CardRepository(pool)

    result = await repo.first_stage_id_in_pipeline(pipeline_id)

    assert result == stage_id
    sql = conn.fetchval.call_args[0][0]
    assert "pipeline_stages" in sql
    assert "ORDER BY position LIMIT 1" in sql


@pytest.mark.asyncio
async def test_stage_exists_in_pipeline_returns_bool():
    pool, conn = _mock_pool()
    stage_id = uuid4()
    pipeline_id = uuid4()
    conn.fetchval.return_value = True
    repo = CardRepository(pool)

    result = await repo.stage_exists_in_pipeline(stage_id, pipeline_id=pipeline_id)

    assert result is True
    sql = conn.fetchval.call_args[0][0]
    assert "pipeline_stages" in sql
    assert "id = $1 AND pipeline_id = $2" in sql


@pytest.mark.asyncio
async def test_pipelines_containing_cnpj_returns_list():
    pool, conn = _mock_pool()
    owner_user_id = uuid4()
    pipeline_id = uuid4()
    stage_id = uuid4()
    card_id = uuid4()
    conn.fetch.return_value = [
        {
            "pipeline_id": pipeline_id,
            "pipeline_name": "Meu Funil",
            "card_id": card_id,
            "stage_id": stage_id,
            "stage_name": "Qualificado",
        }
    ]
    repo = CardRepository(pool)

    results = await repo.pipelines_containing_cnpj(owner_user_id, "12345678")

    assert len(results) == 1
    assert isinstance(results[0], CardInPipelineSummary)
    assert results[0].pipeline_name == "Meu Funil"
    assert results[0].stage_name == "Qualificado"

    sql = conn.fetch.call_args[0][0]
    assert "pipelines" in sql
    assert "pipeline_cards" in sql
    assert "pipeline_stages" in sql
    assert "owner_user_id" in sql
    assert "archived_at IS NULL" in sql


@pytest.mark.asyncio
async def test_insert_stage_change_executes_insert():
    pool, conn = _mock_pool()
    card_id = uuid4()
    from_stage_id = uuid4()
    to_stage_id = uuid4()
    user_id = uuid4()
    repo = CardRepository(pool)

    result = await repo.insert_stage_change(
        card_id,
        from_stage_id=from_stage_id,
        to_stage_id=to_stage_id,
        changed_by_user_id=user_id,
    )

    assert result is None
    sql = conn.execute.call_args[0][0]
    assert "INSERT INTO pipeline_card_stage_changes" in sql
    args = conn.execute.call_args[0][1:]
    assert card_id in args
    assert from_stage_id in args
    assert to_stage_id in args
    assert user_id in args


@pytest.mark.asyncio
async def test_delete_import_batch_for_file_executes_delete():
    pool, conn = _mock_pool()
    repo = CardRepository(pool)
    owner_user_id = uuid4()
    pipeline_id = uuid4()

    await repo.delete_import_batch_for_file(
        owner_user_id=owner_user_id,
        pipeline_id=pipeline_id,
        filename="cards.csv",
        file_size_bytes=100,
    )

    sql = conn.execute.call_args[0][0]
    assert "DELETE FROM pipeline_card_import_batches" in sql
    assert conn.execute.call_args[0][1:] == (owner_user_id, pipeline_id, "cards.csv", 100)


@pytest.mark.asyncio
async def test_insert_import_batch_returns_record():
    pool, conn = _mock_pool()
    owner_user_id = uuid4()
    pipeline_id = uuid4()
    stage_id = uuid4()
    conn.fetchrow.return_value = _import_batch_row(
        owner_user_id=owner_user_id,
        pipeline_id=pipeline_id,
        stage_id=stage_id,
    )
    repo = CardRepository(pool)

    result = await repo.insert_import_batch(
        owner_user_id=owner_user_id,
        pipeline_id=pipeline_id,
        stage_id=stage_id,
        filename="cards.csv",
        file_size_bytes=100,
        content_sha256="a" * 64,
        total_rows=3,
        created_count=1,
        skipped_count=2,
    )

    assert isinstance(result, ImportBatchRecord)
    sql = conn.fetchrow.call_args[0][0]
    assert "INSERT INTO pipeline_card_import_batches" in sql
    assert "content_sha256" in sql


@pytest.mark.asyncio
async def test_insert_import_rows_returns_records_and_decodes_metadata_json():
    pool, conn = _mock_pool()
    batch_id = uuid4()
    card_id = uuid4()
    conn.fetchrow.return_value = _import_row(
        batch_id=batch_id,
        card_id=card_id,
        metadata='{"segmento": "SaaS"}',
    )
    repo = CardRepository(pool)

    result = await repo.insert_import_rows(
        [
            {
                "batch_id": batch_id,
                "line_number": 2,
                "raw_cnpj": "12345678",
                "cnpj_basico": "12345678",
                "display_name": "Lead",
                "card_id": card_id,
                "status": "created",
                "reason": None,
                "metadata_json": '{"segmento": "SaaS"}',
            }
        ]
    )

    assert len(result) == 1
    assert isinstance(result[0], ImportRowRecord)
    assert result[0].metadata == {"segmento": "SaaS"}
    sql = conn.fetchrow.call_args[0][0]
    assert "INSERT INTO pipeline_card_import_rows" in sql
    assert "$9::jsonb" in sql


@pytest.mark.asyncio
async def test_list_import_batches_returns_records():
    pool, conn = _mock_pool()
    pipeline_id = uuid4()
    conn.fetch.return_value = [_import_batch_row(pipeline_id=pipeline_id)]
    repo = CardRepository(pool)

    result = await repo.list_import_batches(pipeline_id)

    assert len(result) == 1
    assert isinstance(result[0], ImportBatchRecord)
    assert "ORDER BY created_at DESC" in conn.fetch.call_args[0][0]


@pytest.mark.asyncio
async def test_list_import_rows_for_card_returns_records():
    pool, conn = _mock_pool()
    card_id = uuid4()
    conn.fetch.return_value = [_import_row(card_id=card_id)]
    repo = CardRepository(pool)

    result = await repo.list_import_rows_for_card(card_id)

    assert len(result) == 1
    assert isinstance(result[0], ImportRowRecord)
    assert "WHERE card_id = $1" in conn.fetch.call_args[0][0]
