"""Pydantic schemas for pipeline cards."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

CnpjBasico = Annotated[str, Field(pattern=r"^\d{8}$")]


class CardCreate(BaseModel):
    cnpj_basico: CnpjBasico
    stage_id: UUID | None = None
    estimated_value_cents: int | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=10000)


class CardPatch(BaseModel):
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
