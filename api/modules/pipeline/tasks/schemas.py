"""Pydantic schemas for pipeline card tasks."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    due_at: datetime | None = None
    assignee_user_id: UUID | None = None


class TaskPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    due_at: datetime | None = None
    done_at: datetime | None = None


class TaskRecord(BaseModel):
    id: UUID
    card_id: UUID
    assignee_user_id: UUID
    title: str
    due_at: datetime | None
    done_at: datetime | None
    created_at: datetime
    updated_at: datetime
