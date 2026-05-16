"""Service layer for pipeline card tasks."""
from __future__ import annotations

from modules.auth.schemas import UserRecord
from modules.pipeline.cards.schemas import CardRecord
from modules.pipeline.tasks.repository import TaskRepository
from modules.pipeline.tasks.schemas import TaskCreate, TaskPatch, TaskRecord


async def create_task(
    repo: TaskRepository,
    *,
    card: CardRecord,
    payload: TaskCreate,
    current_user: UserRecord,
) -> TaskRecord:
    assignee_user_id = payload.assignee_user_id or current_user.id
    return await repo.insert(
        card_id=card.id,
        assignee_user_id=assignee_user_id,
        title=payload.title,
        due_at=payload.due_at,
    )


async def update_task(
    repo: TaskRepository,
    *,
    task: TaskRecord,
    payload: TaskPatch,
) -> TaskRecord:
    return await repo.update(
        task.id,
        title=payload.title,
        due_at=payload.due_at,
        done_at=payload.done_at,
    )


async def delete_task(repo: TaskRepository, *, task: TaskRecord) -> None:
    await repo.delete(task.id)
