"""Router for /pipelines/{pipeline_id}/cards/{card_id}/activities endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from core.csrf import csrf_dependency
from core.middleware.auth import get_current_user
from modules.auth.schemas import UserRecord
from modules.pipeline.activities.repository import ActivityRepository
from modules.pipeline.activities.schemas import (
    ActivityCreate,
    ActivityPatch,
    ActivityRecord,
)
from modules.pipeline.activities.service import (
    create_activity,
    delete_activity,
    update_activity,
)
from modules.pipeline.cards.schemas import CardRecord
from modules.pipeline.dependencies import get_activity_repo, owned_activity, owned_card


router = APIRouter(
    prefix="/pipelines/{pipeline_id}/cards/{card_id}/activities",
    tags=["pipeline_activities"],
)


@router.get("", response_model=list[ActivityRecord])
async def list_activities(
    cursor: datetime | None = None,
    limit: int = Query(50, ge=1, le=100),
    card: CardRecord = Depends(owned_card),
    repo: ActivityRepository = Depends(get_activity_repo),
) -> list[ActivityRecord]:
    return await repo.list(card_id=card.id, cursor=cursor, limit=limit)


@router.post(
    "",
    response_model=ActivityRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(csrf_dependency)],
)
async def create_activity_endpoint(
    payload: ActivityCreate,
    card: CardRecord = Depends(owned_card),
    repo: ActivityRepository = Depends(get_activity_repo),
    current_user: UserRecord = Depends(get_current_user),
) -> ActivityRecord:
    return await create_activity(
        repo,
        card_id=card.id,
        payload=payload,
        current_user=current_user,
    )


@router.patch(
    "/{activity_id}",
    response_model=ActivityRecord,
    dependencies=[Depends(csrf_dependency)],
)
async def update_activity_endpoint(
    payload: ActivityPatch,
    activity: ActivityRecord = Depends(owned_activity),
    repo: ActivityRepository = Depends(get_activity_repo),
) -> ActivityRecord:
    return await update_activity(repo, activity=activity, payload=payload)


@router.delete(
    "/{activity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Depends(csrf_dependency)],
)
async def delete_activity_endpoint(
    activity: ActivityRecord = Depends(owned_activity),
    repo: ActivityRepository = Depends(get_activity_repo),
) -> None:
    await delete_activity(repo, activity=activity)
