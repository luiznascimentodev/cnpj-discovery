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
from modules.pipeline.cards.schemas import CardRecord


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


def test_normalize_cnpj_accepts_eight_digits():
    assert normalize_cnpj("12345678") == "12345678"


def test_normalize_cnpj_accepts_formatted_full_cnpj():
    assert normalize_cnpj("12.345.678/0001-00") == "12345678"


def test_normalize_cnpj_rejects_wrong_digit_count():
    assert normalize_cnpj("123") is None


def test_parse_csv_comma_with_header():
    assert parse_csv("cnpj\n12345678\n") == [(2, "12345678")]


def test_parse_csv_semicolon_without_header():
    assert parse_csv("12345678;x\n87654321;y\n") == [(1, "12345678"), (2, "87654321")]


def test_parse_csv_handles_bom_and_crlf():
    assert parse_csv("\ufeffcnpj\r\n12345678\r\n") == [(2, "12345678")]


def test_parse_csv_keeps_invalid_rows_after_header():
    assert parse_csv("cnpj\nabc\n") == [(2, "abc")]


def test_parse_csv_skips_blank_rows():
    assert parse_csv("cnpj\n\n12345678\n") == [(3, "12345678")]


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
    repo.existing_cards_in_pipeline_by_cnpj.return_value = {"87654321"}
    repo.max_position_in_stage.return_value = 4
    inserted = [_card(pipeline_id=pipeline_id, stage_id=stage_id, cnpj_basico="12345678", position=5)]
    repo.bulk_insert.return_value = inserted

    result = await import_cards(
        repo,
        pipeline_id=pipeline_id,
        stage_id=stage_id,
        current_user_id=user_id,
        content="cnpj\n12.345.678/0001-00\n87654321\n12345678\nabc\n99999999\n",
    )

    assert result.created == 1
    assert [row.reason for row in result.skipped] == [
        "duplicate_in_pipeline",
        "invalid_cnpj_format",
        "duplicate_in_pipeline",
        "cnpj_not_found",
    ]
    repo.bulk_insert.assert_awaited_once()
    assert repo.bulk_insert.call_args.args[0][0]["position"] == 5
    repo.insert_stage_change.assert_awaited_once_with(
        inserted[0].id,
        from_stage_id=None,
        to_stage_id=stage_id,
        changed_by_user_id=user_id,
    )


@pytest.mark.asyncio
async def test_import_cards_empty_file_does_not_query_bulk_insert():
    repo = AsyncMock()

    result = await import_cards(
        repo,
        pipeline_id=uuid4(),
        stage_id=uuid4(),
        current_user_id=uuid4(),
        content="cnpj\n",
    )

    assert result.created == 0
    assert result.summary.total_rows == 0
    repo.bulk_insert.assert_not_called()


@pytest.mark.asyncio
async def test_import_cards_all_invalid_rows():
    repo = AsyncMock()

    result = await import_cards(
        repo,
        pipeline_id=uuid4(),
        stage_id=uuid4(),
        current_user_id=uuid4(),
        content="cnpj\nabc\n",
    )

    assert result.created == 0
    assert result.summary.invalid_rows == 1
    assert result.skipped[0].reason == "invalid_cnpj_format"
