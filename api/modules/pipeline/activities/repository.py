"""Repository for pipeline card activity CRUD operations."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from modules.pipeline.activities.schemas import ActivityKind, ActivityRecord


class ActivityRepository:
    def __init__(self, pool):
        self._pool = pool

    async def insert(
        self,
        *,
        card_id: UUID,
        author_user_id: UUID,
        kind: ActivityKind,
        body: str,
        occurred_at: datetime | None,
    ) -> ActivityRecord:
        row = await self._fetchrow(
            "INSERT INTO pipeline_card_activities"
            " (card_id, author_user_id, kind, body, occurred_at)"
            " VALUES ($1, $2, $3, $4, COALESCE($5, now())) RETURNING *",
            card_id,
            author_user_id,
            kind,
            body,
            occurred_at,
        )
        return ActivityRecord(**dict(row))

    async def list(
        self,
        *,
        card_id: UUID,
        cursor: datetime | None,
        limit: int,
    ) -> list[ActivityRecord]:
        if cursor is None:
            rows = await self._fetch(
                "SELECT * FROM pipeline_card_activities"
                " WHERE card_id = $1"
                " ORDER BY occurred_at DESC"
                " LIMIT $2",
                card_id,
                limit,
            )
        else:
            rows = await self._fetch(
                "SELECT * FROM pipeline_card_activities"
                " WHERE card_id = $1 AND occurred_at < $2"
                " ORDER BY occurred_at DESC"
                " LIMIT $3",
                card_id,
                cursor,
                limit,
            )
        return [ActivityRecord(**dict(row)) for row in rows]

    async def get(
        self,
        activity_id: UUID,
        *,
        card_id: UUID,
    ) -> ActivityRecord | None:
        row = await self._fetchrow(
            "SELECT * FROM pipeline_card_activities WHERE id = $1 AND card_id = $2",
            activity_id,
            card_id,
        )
        return ActivityRecord(**dict(row)) if row else None

    async def get_in_card(
        self,
        activity_id: UUID,
        *,
        card_id: UUID,
    ) -> ActivityRecord | None:
        return await self.get(activity_id, card_id=card_id)

    async def update(
        self,
        activity_id: UUID,
        *,
        body: str,
    ) -> ActivityRecord:
        row = await self._fetchrow(
            "UPDATE pipeline_card_activities"
            " SET body = $2"
            " WHERE id = $1 RETURNING *",
            activity_id,
            body,
        )
        return ActivityRecord(**dict(row))

    async def delete(self, activity_id: UUID) -> None:
        await self._execute(
            "DELETE FROM pipeline_card_activities WHERE id = $1",
            activity_id,
        )

    async def _fetchrow(self, query: str, *args):
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def _fetch(self, query: str, *args):
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def _execute(self, query: str, *args) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(query, *args)
