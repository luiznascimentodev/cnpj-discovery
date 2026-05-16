"""Pydantic schemas for pipeline card activities."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ActivityKind = Literal["note", "call", "email", "meeting"]


class ActivityCreate(BaseModel):
    kind: ActivityKind
    body: str = Field(..., min_length=1, max_length=10000)
    occurred_at: datetime | None = None


class ActivityPatch(BaseModel):
    body: str = Field(..., min_length=1, max_length=10000)


class ActivityRecord(BaseModel):
    id: UUID
    card_id: UUID
    author_user_id: UUID
    kind: ActivityKind
    body: str
    occurred_at: datetime
    created_at: datetime
