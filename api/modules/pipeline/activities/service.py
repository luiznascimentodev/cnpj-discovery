"""Service layer for pipeline card activities."""
from __future__ import annotations

from uuid import UUID

from modules.auth.schemas import UserRecord
from modules.pipeline.activities.repository import ActivityRepository
from modules.pipeline.activities.schemas import (
    ActivityCreate,
    ActivityPatch,
    ActivityRecord,
)


async def create_activity(
    repo: ActivityRepository,
    *,
    card_id: UUID,
    payload: ActivityCreate,
    current_user: UserRecord,
) -> ActivityRecord:
    return await repo.insert(
        card_id=card_id,
        author_user_id=current_user.id,
        kind=payload.kind,
        body=payload.body,
        occurred_at=payload.occurred_at,
    )


async def update_activity(
    repo: ActivityRepository,
    *,
    activity: ActivityRecord,
    payload: ActivityPatch,
) -> ActivityRecord:
    return await repo.update(activity.id, body=payload.body)


async def delete_activity(
    repo: ActivityRepository,
    *,
    activity: ActivityRecord,
) -> None:
    await repo.delete(activity.id)
