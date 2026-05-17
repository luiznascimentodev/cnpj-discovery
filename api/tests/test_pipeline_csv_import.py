"""Tests for pipeline card CSV import."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from modules.pipeline.cards.csv_import import (
    MAX_FILE_BYTES,
    MAX_ROWS,
    import_cards,
    normalize_cnpj,
    parse_csv,
)
from modules.pipeline.cards.schemas import CardRecord, ImportBatchRecord


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


def _batch(**overrides):
    now = datetime.now(timezone.utc)
    base = dict(
        id=uuid4(),
        pipeline_id=uuid4(),
        owner_user_id=uuid4(),
        stage_id=uuid4(),
        filename="cards.csv",
        file_size_bytes=32,
        content_sha256="a" * 64,
        total_rows=0,
        created_count=0,
        skipped_count=0,
        created_at=now,
    )
    base.update(overrides)
    return ImportBatchRecord(**base)


def _line_pairs(content: str) -> list[tuple[int, str]]:
    return [(row.line, row.raw_cnpj) for row in parse_csv(content)]


def test_normalize_cnpj_accepts_eight_digits():
    assert normalize_cnpj("12345678") == "12345678"


def test_normalize_cnpj_accepts_formatted_full_cnpj():
    assert normalize_cnpj("12.345.678/0001-00") == "12345678"


def test_normalize_cnpj_rejects_wrong_digit_count():
    assert normalize_cnpj("123") is None


def test_parse_csv_comma_with_header():
    assert _line_pairs("cnpj\n12345678\n") == [(2, "12345678")]


def test_parse_csv_semicolon_without_header():
    assert _line_pairs("12345678;x\n87654321;y\n") == [(1, "12345678"), (2, "87654321")]


def test_parse_csv_handles_bom_and_crlf():
    assert _line_pairs("\ufeffcnpj\r\n12345678\r\n") == [(2, "12345678")]


def test_parse_csv_keeps_invalid_rows_after_header():
    assert _line_pairs("cnpj\nabc\n") == [(2, "abc")]


def test_parse_csv_skips_blank_rows():
    assert _line_pairs("cnpj\n\n12345678\n") == [(3, "12345678")]


def test_parse_csv_empty_file_returns_empty_list():
    assert parse_csv("\n\n") == []


def test_parse_csv_falls_back_to_first_column_when_no_cnpj_sample():
    rows = parse_csv("sem cabecalho\nabc\n")

    assert rows[0].raw_cnpj == "abc"


def test_parse_csv_preserves_display_name_and_extra_columns():
    rows = parse_csv("cnpj;nome;segmento\n12345678;Lead A;SaaS\n")

    assert rows[0].display_name == "Lead A"
    assert rows[0].metadata == {"segmento": "SaaS"}


def test_parse_csv_rejects_large_file():
    with pytest.raises(HTTPException) as exc_info:
        parse_csv("1" * (MAX_FILE_BYTES + 1))

    assert exc_info.value.status_code == 413


def test_parse_csv_rejects_too_many_rows():
    content = "\n".join(["12345678"] * (MAX_ROWS + 1))

    with pytest.raises(HTTPException) as exc_info:
        parse_csv(content)

    assert exc_info.value.status_code == 413


@pytest.mark.asyncio
async def test_import_cards_success_partial_with_all_skip_reasons():
    pipeline_id = uuid4()
    stage_id = uuid4()
    user_id = uuid4()
    repo = AsyncMock()
    repo.existing_cnpjs_in_basico.return_value = {"12345678", "87654321"}
    existing_card_id = uuid4()
    repo.existing_card_ids_in_pipeline_by_cnpj.return_value = {"87654321": existing_card_id}
    repo.max_position_in_stage.return_value = 4
    inserted = [_card(pipeline_id=pipeline_id, stage_id=stage_id, cnpj_basico="12345678", position=5)]
    repo.bulk_insert.return_value = inserted
    repo.insert_import_batch.return_value = _batch(
        pipeline_id=pipeline_id,
        owner_user_id=user_id,
        stage_id=stage_id,
        total_rows=5,
        created_count=1,
        skipped_count=4,
    )

    result = await import_cards(
        repo,
        pipeline_id=pipeline_id,
        stage_id=stage_id,
        current_user_id=user_id,
        filename="cards.csv",
        file_size_bytes=128,
        content="cnpj\n12.345.678/0001-00\n87654321\n12345678\nabc\n99999999\n",
    )

    assert result.created == 1
    assert [row.reason for row in result.skipped] == [
        "duplicate_in_pipeline",
        "duplicate_in_pipeline",
        "invalid_cnpj_format",
        "cnpj_not_found",
    ]
    repo.bulk_insert.assert_awaited_once()
    assert repo.bulk_insert.call_args.args[0][0]["position"] == 5
    assert repo.bulk_insert.call_args.args[0][0]["display_name"] is None
    repo.insert_stage_change.assert_awaited_once_with(
        inserted[0].id,
        from_stage_id=None,
        to_stage_id=stage_id,
        changed_by_user_id=user_id,
    )
    repo.delete_import_batch_for_file.assert_awaited_once_with(
        owner_user_id=user_id,
        pipeline_id=pipeline_id,
        filename="cards.csv",
        file_size_bytes=128,
    )
    repo.insert_import_rows.assert_awaited_once()
    persisted_rows = repo.insert_import_rows.call_args.args[0]
    assert len(persisted_rows) == 5
    assert any(row.get("card_id") == existing_card_id for row in persisted_rows)


@pytest.mark.asyncio
async def test_import_cards_empty_file_does_not_query_bulk_insert():
    repo = AsyncMock()
    repo.insert_import_batch.return_value = _batch()

    result = await import_cards(
        repo,
        pipeline_id=uuid4(),
        stage_id=uuid4(),
        current_user_id=uuid4(),
        filename="empty.csv",
        file_size_bytes=5,
        content="cnpj\n",
    )

    assert result.created == 0
    assert result.summary.total_rows == 0
    repo.bulk_insert.assert_not_called()
    repo.insert_import_batch.assert_awaited_once()


@pytest.mark.asyncio
async def test_import_cards_all_invalid_rows():
    repo = AsyncMock()
    repo.insert_import_batch.return_value = _batch(total_rows=1, skipped_count=1)

    result = await import_cards(
        repo,
        pipeline_id=uuid4(),
        stage_id=uuid4(),
        current_user_id=uuid4(),
        filename="invalid.csv",
        file_size_bytes=9,
        content="cnpj\nabc\n",
    )

    assert result.created == 0
    assert result.summary.invalid_rows == 1
    assert result.skipped[0].reason == "invalid_cnpj_format"
