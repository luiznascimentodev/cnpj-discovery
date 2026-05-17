"""CSV import helpers for pipeline cards."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from modules.pipeline.cards.repository import CardRepository
from modules.pipeline.cards.schemas import ImportBatchRecord
from modules.pipeline.errors import ErrorCode, pipeline_error

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000

CNPJ_HEADERS = {"cnpj", "cnpj_basico", "cnpj básico", "documento", "cpf_cnpj", "cpf/cnpj"}
NAME_HEADERS = {"nome", "nome_card", "card_name", "titulo", "título", "apelido", "empresa"}


class CsvImportRow(BaseModel):
    line: int
    raw_cnpj: str
    cnpj_basico: str | None
    display_name: str | None
    metadata: dict[str, str]


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
    batch: ImportBatchRecord
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


def _normalize_header(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _dialect_for(text: str) -> csv.Dialect:
    sample = text[:2048]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        return csv.excel


def _has_header(first_row: list[str]) -> bool:
    normalized = {_normalize_header(cell) for cell in first_row}
    if normalized & (CNPJ_HEADERS | NAME_HEADERS):
        return True
    return all(normalize_cnpj(cell) is None for cell in first_row)


def _find_column(headers: list[str], aliases: set[str]) -> int | None:
    for index, header in enumerate(headers):
        if _normalize_header(header) in aliases:
            return index
    return None


def _find_cnpj_column(headers: list[str], data_rows: list[list[str]]) -> int:
    by_header = _find_column(headers, CNPJ_HEADERS)
    if by_header is not None:
        return by_header
    sample = data_rows[:20]
    for index in range(max((len(row) for row in sample), default=1)):
        if any(index < len(row) and normalize_cnpj(row[index]) for row in sample):
            return index
    return 0


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def parse_csv(content: str) -> list[CsvImportRow]:
    text = content.lstrip("\ufeff")
    if len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise pipeline_error(ErrorCode.PAYLOAD_TOO_LARGE)

    reader = csv.reader(io.StringIO(text), _dialect_for(text))
    raw_rows = [(line, row) for line, row in enumerate(reader, start=1)]
    raw_rows = [
        (line, row)
        for line, row in raw_rows
        if row and not all(not cell.strip() for cell in row)
    ]
    if not raw_rows:
        return []

    _, first_row = raw_rows[0]
    has_header = _has_header(first_row)
    headers = first_row if has_header else [f"column_{index + 1}" for index in range(len(first_row))]
    data_rows = raw_rows[1:] if has_header else raw_rows
    cnpj_index = _find_cnpj_column(headers, [row for _, row in data_rows])
    name_index = _find_column(headers, NAME_HEADERS)

    parsed: list[CsvImportRow] = []
    for line_number, row in data_rows:
        raw_cnpj = _cell(row, cnpj_index)
        metadata: dict[str, str] = {}
        for index, value in enumerate(row):
            if index in {cnpj_index, name_index}:
                continue
            key = headers[index] if index < len(headers) and headers[index] else f"column_{index + 1}"
            metadata[key] = value.strip()

        parsed.append(
            CsvImportRow(
                line=line_number,
                raw_cnpj=raw_cnpj,
                cnpj_basico=normalize_cnpj(raw_cnpj),
                display_name=_cell(row, name_index) or None,
                metadata=metadata,
            )
        )

    if len(parsed) > MAX_ROWS:
        raise pipeline_error(ErrorCode.PAYLOAD_TOO_LARGE)
    return parsed


async def import_cards(
    repo_card: CardRepository,
    *,
    pipeline_id: UUID,
    stage_id: UUID,
    current_user_id: UUID,
    filename: str,
    file_size_bytes: int,
    content: str,
) -> ImportResult:
    parsed = parse_csv(content)
    skipped: list[SkippedRow] = []
    ordered_rows: list[CsvImportRow] = []
    duplicate_import_rows: list[dict] = []
    seen: set[str] = set()
    duplicates_in_file = 0

    for row in parsed:
        if row.cnpj_basico is None:
            skipped.append(
                SkippedRow(line=row.line, cnpj=row.raw_cnpj, reason="invalid_cnpj_format")
            )
            continue
        if row.cnpj_basico in seen:
            duplicates_in_file += 1
            skipped.append(
                SkippedRow(
                    line=row.line,
                    cnpj=row.cnpj_basico,
                    reason="duplicate_in_pipeline",
                )
            )
            duplicate_import_rows.append(
                {
                    "line_number": row.line,
                    "raw_cnpj": row.raw_cnpj,
                    "cnpj_basico": row.cnpj_basico,
                    "display_name": row.display_name,
                    "status": "skipped",
                    "reason": "duplicate_in_pipeline",
                    "metadata_json": json.dumps(row.metadata, ensure_ascii=False),
                }
            )
            continue
        seen.add(row.cnpj_basico)
        ordered_rows.append(row)

    cnpjs = [row.cnpj_basico for row in ordered_rows if row.cnpj_basico]
    existing_cnpjs = await repo_card.existing_cnpjs_in_basico(cnpjs) if cnpjs else set()
    existing_card_ids = (
        await repo_card.existing_card_ids_in_pipeline_by_cnpj(pipeline_id, cnpjs)
        if cnpjs
        else {}
    )

    rows_to_insert: list[dict] = []
    import_row_payloads: list[dict] = [*duplicate_import_rows]
    next_position = 0
    if ordered_rows:
        max_position = await repo_card.max_position_in_stage(stage_id)
        next_position = 0 if max_position is None else max_position + 1

    for row in ordered_rows:
        cnpj = row.cnpj_basico or ""
        if cnpj not in existing_cnpjs:
            skipped.append(SkippedRow(line=row.line, cnpj=cnpj, reason="cnpj_not_found"))
            import_row_payloads.append(
                {
                    "line_number": row.line,
                    "raw_cnpj": row.raw_cnpj,
                    "cnpj_basico": cnpj,
                    "display_name": row.display_name,
                    "status": "skipped",
                    "reason": "cnpj_not_found",
                    "metadata_json": json.dumps(row.metadata, ensure_ascii=False),
                }
            )
            continue
        if cnpj in existing_card_ids:
            skipped.append(SkippedRow(line=row.line, cnpj=cnpj, reason="duplicate_in_pipeline"))
            import_row_payloads.append(
                {
                    "line_number": row.line,
                    "raw_cnpj": row.raw_cnpj,
                    "cnpj_basico": cnpj,
                    "display_name": row.display_name,
                    "card_id": existing_card_ids[cnpj],
                    "status": "skipped",
                    "reason": "duplicate_in_pipeline",
                    "metadata_json": json.dumps(row.metadata, ensure_ascii=False),
                }
            )
            continue
        rows_to_insert.append(
            {
                "pipeline_id": pipeline_id,
                "stage_id": stage_id,
                "cnpj_basico": cnpj,
                "position": next_position,
                "display_name": row.display_name,
                "estimated_value_cents": None,
                "notes": None,
                "import_row": row,
            }
        )
        next_position += 1

    inserted = await repo_card.bulk_insert(rows_to_insert) if rows_to_insert else []
    for card, source in zip(inserted, rows_to_insert, strict=True):
        await repo_card.insert_stage_change(
            card.id,
            from_stage_id=None,
            to_stage_id=stage_id,
            changed_by_user_id=current_user_id,
        )
        import_row = source["import_row"]
        import_row_payloads.append(
            {
                "line_number": import_row.line,
                "raw_cnpj": import_row.raw_cnpj,
                "cnpj_basico": import_row.cnpj_basico,
                "display_name": import_row.display_name,
                "card_id": card.id,
                "status": "created",
                "reason": None,
                "metadata_json": json.dumps(import_row.metadata, ensure_ascii=False),
            }
        )

    for row in parsed:
        if row.cnpj_basico is None:
            import_row_payloads.append(
                {
                    "line_number": row.line,
                    "raw_cnpj": row.raw_cnpj,
                    "cnpj_basico": None,
                    "display_name": row.display_name,
                    "status": "skipped",
                    "reason": "invalid_cnpj_format",
                    "metadata_json": json.dumps(row.metadata, ensure_ascii=False),
                }
            )

    await repo_card.delete_import_batch_for_file(
        owner_user_id=current_user_id,
        pipeline_id=pipeline_id,
        filename=filename,
        file_size_bytes=file_size_bytes,
    )
    batch = await repo_card.insert_import_batch(
        owner_user_id=current_user_id,
        pipeline_id=pipeline_id,
        stage_id=stage_id,
        filename=filename,
        file_size_bytes=file_size_bytes,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        total_rows=len(parsed),
        created_count=len(inserted),
        skipped_count=len(skipped),
    )
    await repo_card.insert_import_rows(
        [dict(row, batch_id=batch.id) for row in sorted(import_row_payloads, key=lambda item: item["line_number"])]
    )

    return ImportResult(
        batch=batch,
        created=len(inserted),
        skipped=sorted(skipped, key=lambda row: row.line),
        summary=ImportSummary(
            total_rows=len(parsed),
            valid_rows=len(ordered_rows),
            invalid_rows=len([row for row in skipped if row.reason == "invalid_cnpj_format"]),
            duplicates_in_file=duplicates_in_file,
        ),
    )
