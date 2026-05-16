"""Pydantic schemas for pipeline stages."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class StageCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    color: str | None = Field(None, max_length=32)
    is_won: bool = False
    is_lost: bool = False
    position: int | None = Field(None, ge=0)


class StagePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    color: str | None = Field(None, max_length=32)
    is_won: bool | None = None
    is_lost: bool | None = None


class StageRecord(BaseModel):
    id: UUID
    pipeline_id: UUID
    name: str
    position: int
    color: str | None
    is_won: bool
    is_lost: bool
    created_at: datetime
    updated_at: datetime


class StageReorderRequest(BaseModel):
    stage_ids: list[UUID] = Field(..., min_length=1)
