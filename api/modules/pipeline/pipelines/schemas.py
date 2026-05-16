"""Pydantic schemas for pipelines."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PipelineCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)


class PipelinePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)


class PipelineRecord(BaseModel):
    id: UUID
    owner_user_id: UUID
    name: str
    description: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StageCount(BaseModel):
    stage_id: UUID
    name: str
    card_count: int
    total_value_cents: int


class PipelineDetail(BaseModel):
    pipeline: PipelineRecord
    stage_counts: list[StageCount]
    total_value_cents: int
