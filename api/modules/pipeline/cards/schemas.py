"""Pydantic schemas for pipeline cards."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Any
from uuid import UUID

from pydantic import BaseModel, Field

CnpjBasico = Annotated[str, Field(pattern=r"^\d{8}$")]


class CardCreate(BaseModel):
    cnpj_basico: CnpjBasico
    stage_id: UUID | None = None
    display_name: str | None = Field(None, max_length=200)
    estimated_value_cents: int | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=10000)


class CardPatch(BaseModel):
    display_name: str | None = Field(None, max_length=200)
    estimated_value_cents: int | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=10000)


class CardMove(BaseModel):
    stage_id: UUID
    position: int = Field(..., ge=0)


class CardRecord(BaseModel):
    id: UUID
    pipeline_id: UUID
    stage_id: UUID
    cnpj_basico: str
    position: int
    display_name: str | None = None
    estimated_value_cents: int | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class CompanySummary(BaseModel):
    razao_social: str | None
    uf: str | None


class CardWithCompany(BaseModel):
    card: CardRecord
    company: CompanySummary


class CardInPipelineSummary(BaseModel):
    pipeline_id: UUID
    pipeline_name: str
    card_id: UUID
    stage_id: UUID
    stage_name: str


class ImportBatchRecord(BaseModel):
    id: UUID
    pipeline_id: UUID
    owner_user_id: UUID
    stage_id: UUID
    filename: str | None
    file_size_bytes: int
    content_sha256: str
    total_rows: int
    created_count: int
    skipped_count: int
    created_at: datetime


ImportRowStatus = Literal["created", "skipped"]
ImportSkipReason = Literal["invalid_cnpj_format", "cnpj_not_found", "duplicate_in_pipeline"]


class ImportRowRecord(BaseModel):
    id: int
    batch_id: UUID
    line_number: int
    raw_cnpj: str
    cnpj_basico: str | None
    display_name: str | None
    card_id: UUID | None
    status: ImportRowStatus
    reason: ImportSkipReason | None
    metadata: dict[str, Any]
    created_at: datetime
