"""Repository for pipeline card task CRUD operations."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from modules.pipeline.tasks.schemas import TaskRecord


class TaskRepository:
    def __init__(self, pool):
        self._pool = pool

    async def insert(
        self,
        *,
        card_id: UUID,
        assignee_user_id: UUID,
        title: str,
        due_at: datetime | None,
    ) -> TaskRecord:
        row = await self._fetchrow(
            "INSERT INTO pipeline_card_tasks"
            " (card_id, assignee_user_id, title, due_at)"
            " VALUES ($1, $2, $3, $4) RETURNING *",
            card_id,
            assignee_user_id,
            title,
            due_at,
        )
        return TaskRecord(**dict(row))

    async def list_for_card(self, card_id: UUID) -> list[TaskRecord]:
        rows = await self._fetch(
            "SELECT * FROM pipeline_card_tasks"
            " WHERE card_id = $1"
            " ORDER BY done_at NULLS FIRST, due_at NULLS LAST, created_at DESC",
            card_id,
        )
        return [TaskRecord(**dict(row)) for row in rows]

    async def get_in_card(
        self,
        task_id: UUID,
        *,
        card_id: UUID,
    ) -> TaskRecord | None:
        row = await self._fetchrow(
            "SELECT * FROM pipeline_card_tasks WHERE id = $1 AND card_id = $2",
            task_id,
            card_id,
        )
        return TaskRecord(**dict(row)) if row else None

    async def update(
        self,
        task_id: UUID,
        *,
        title: str | None,
        due_at: datetime | None,
        done_at: datetime | None,
    ) -> TaskRecord:
        row = await self._fetchrow(
            "UPDATE pipeline_card_tasks"
            " SET title = COALESCE($2, title),"
            " due_at = COALESCE($3, due_at),"
            " done_at = COALESCE($4, done_at),"
            " updated_at = now()"
            " WHERE id = $1 RETURNING *",
            task_id,
            title,
            due_at,
            done_at,
        )
        return TaskRecord(**dict(row))

    async def delete(self, task_id: UUID) -> None:
        await self._execute(
            "DELETE FROM pipeline_card_tasks WHERE id = $1",
            task_id,
        )

    async def list_open_for_assignee(self, assignee_user_id: UUID) -> list[TaskRecord]:
        rows = await self._fetch(
            "SELECT * FROM pipeline_card_tasks"
            " WHERE assignee_user_id = $1 AND done_at IS NULL"
            " ORDER BY due_at NULLS LAST, created_at DESC",
            assignee_user_id,
        )
        return [TaskRecord(**dict(row)) for row in rows]

    async def _fetchrow(self, query: str, *args):
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def _fetch(self, query: str, *args):
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def _execute(self, query: str, *args) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(query, *args)
