"""Router for pipeline card task endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status

from core.csrf import csrf_dependency
from core.middleware.auth import get_current_user
from modules.auth.schemas import UserRecord
from modules.pipeline.cards.schemas import CardRecord
from modules.pipeline.dependencies import get_task_repo, owned_card, owned_task
from modules.pipeline.tasks.repository import TaskRepository
from modules.pipeline.tasks.schemas import TaskCreate, TaskPatch, TaskRecord
from modules.pipeline.tasks.service import create_task, delete_task, update_task


router = APIRouter(tags=["pipeline_tasks"])

card_tasks_router = APIRouter(
    prefix="/pipelines/{pipeline_id}/cards/{card_id}/tasks",
    tags=["pipeline_tasks"],
)
mine_router = APIRouter(prefix="/pipelines/tasks", tags=["pipeline_tasks"])


@card_tasks_router.get("", response_model=list[TaskRecord])
async def list_tasks(
    card: CardRecord = Depends(owned_card),
    repo: TaskRepository = Depends(get_task_repo),
) -> list[TaskRecord]:
    return await repo.list_for_card(card.id)


@card_tasks_router.post(
    "",
    response_model=TaskRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(csrf_dependency)],
)
async def create_task_endpoint(
    payload: TaskCreate,
    card: CardRecord = Depends(owned_card),
    current_user: UserRecord = Depends(get_current_user),
    repo: TaskRepository = Depends(get_task_repo),
) -> TaskRecord:
    return await create_task(repo, card=card, payload=payload, current_user=current_user)


@card_tasks_router.patch(
    "/{task_id}",
    response_model=TaskRecord,
    dependencies=[Depends(csrf_dependency)],
)
async def update_task_endpoint(
    payload: TaskPatch,
    task: TaskRecord = Depends(owned_task),
    repo: TaskRepository = Depends(get_task_repo),
) -> TaskRecord:
    return await update_task(repo, task=task, payload=payload)


@card_tasks_router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Depends(csrf_dependency)],
)
async def delete_task_endpoint(
    task: TaskRecord = Depends(owned_task),
    repo: TaskRepository = Depends(get_task_repo),
) -> None:
    await delete_task(repo, task=task)


@mine_router.get("/mine", response_model=list[TaskRecord])
async def list_my_open_tasks(
    current_user: UserRecord = Depends(get_current_user),
    repo: TaskRepository = Depends(get_task_repo),
) -> list[TaskRecord]:
    return await repo.list_open_for_assignee(current_user.id)


router.include_router(card_tasks_router)
router.include_router(mine_router)
