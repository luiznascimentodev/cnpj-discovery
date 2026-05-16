"""CSV import helpers for pipeline cards."""
from __future__ import annotations

import csv
import io
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from modules.pipeline.cards.repository import CardRepository
from modules.pipeline.errors import ErrorCode, pipeline_error

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000


class SkippedRow(BaseModel):
    line: int
    cnpj: str
    reason: Literal["invalid_cnpj_format", "cnpj_not_found", "duplicate_in_pipeline"]


class ImportSummary(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicates_in_file: int


class ImportResult(BaseModel):
    created: int
    skipped: list[SkippedRow]
    summary: ImportSummary


def normalize_cnpj(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 8:
        return digits
    if len(digits) == 14:
        return digits[:8]
    return None


def parse_csv(content: str) -> list[tuple[int, str]]:
    text = content.lstrip("\ufeff")
    if len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise pipeline_error(ErrorCode.PAYLOAD_TOO_LARGE)

    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
    except csv.Error:
        dialect = csv.excel

    rows: list[tuple[int, str]] = []
    reader = csv.reader(io.StringIO(text), dialect)
    for line_number, row in enumerate(reader, start=1):
        if not row or all(not cell.strip() for cell in row):
            continue
        raw_cnpj = row[0].strip()
        if line_number == 1 and normalize_cnpj(raw_cnpj) is None:
            continue
        rows.append((line_number, raw_cnpj))

    if len(rows) > MAX_ROWS:
        raise pipeline_error(ErrorCode.PAYLOAD_TOO_LARGE)
    return rows


async def import_cards(
    repo_card: CardRepository,
    *,
    pipeline_id: UUID,
    stage_id: UUID,
    current_user_id: UUID,
    content: str,
) -> ImportResult:
    parsed = parse_csv(content)
    skipped: list[SkippedRow] = []
    ordered_cnpjs: list[tuple[int, str]] = []
    seen: set[str] = set()
    duplicates_in_file = 0

    for line, raw in parsed:
        cnpj = normalize_cnpj(raw)
        if cnpj is None:
            skipped.append(SkippedRow(line=line, cnpj=raw, reason="invalid_cnpj_format"))
            continue
        if cnpj in seen:
            duplicates_in_file += 1
            skipped.append(SkippedRow(line=line, cnpj=cnpj, reason="duplicate_in_pipeline"))
            continue
        seen.add(cnpj)
        ordered_cnpjs.append((line, cnpj))

    cnpjs = [cnpj for _, cnpj in ordered_cnpjs]
    existing_cnpjs = await repo_card.existing_cnpjs_in_basico(cnpjs) if cnpjs else set()
    existing_cards = (
        await repo_card.existing_cards_in_pipeline_by_cnpj(pipeline_id, cnpjs)
        if cnpjs
        else set()
    )

    rows_to_insert: list[dict] = []
    max_position = await repo_card.max_position_in_stage(stage_id)
    next_position = 0 if max_position is None else max_position + 1

    for line, cnpj in ordered_cnpjs:
        if cnpj not in existing_cnpjs:
            skipped.append(SkippedRow(line=line, cnpj=cnpj, reason="cnpj_not_found"))
            continue
        if cnpj in existing_cards:
            skipped.append(SkippedRow(line=line, cnpj=cnpj, reason="duplicate_in_pipeline"))
            continue
        rows_to_insert.append(
            {
                "pipeline_id": pipeline_id,
                "stage_id": stage_id,
                "cnpj_basico": cnpj,
                "position": next_position,
                "estimated_value_cents": None,
                "notes": None,
            }
        )
        next_position += 1

    inserted = await repo_card.bulk_insert(rows_to_insert) if rows_to_insert else []
    for card in inserted:
        await repo_card.insert_stage_change(
            card.id,
            from_stage_id=None,
            to_stage_id=stage_id,
            changed_by_user_id=current_user_id,
        )

    return ImportResult(
        created=len(inserted),
        skipped=skipped,
        summary=ImportSummary(
            total_rows=len(parsed),
            valid_rows=len(ordered_cnpjs),
            invalid_rows=len([row for row in skipped if row.reason == "invalid_cnpj_format"]),
            duplicates_in_file=duplicates_in_file,
        ),
    )
