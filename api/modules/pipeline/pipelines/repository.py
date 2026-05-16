"""Repository for pipeline CRUD operations."""
from __future__ import annotations

from uuid import UUID

from modules.pipeline.pipelines.schemas import PipelineRecord


class PipelineRepository:
    def __init__(self, pool):
        self._pool = pool

    async def insert(
        self,
        *,
        owner_user_id: UUID,
        name: str,
        description: str | None,
    ) -> PipelineRecord:
        row = await self._fetchrow(
            "INSERT INTO pipelines (owner_user_id, name, description) VALUES ($1, $2, $3) RETURNING *",
            owner_user_id,
            name,
            description,
        )
        return PipelineRecord(**dict(row))

    async def get_for_owner(
        self,
        pipeline_id: UUID,
        *,
        owner_user_id: UUID,
    ) -> PipelineRecord | None:
        row = await self._fetchrow(
            "SELECT * FROM pipelines WHERE id = $1 AND owner_user_id = $2",
            pipeline_id,
            owner_user_id,
        )
        return PipelineRecord(**dict(row)) if row else None

    async def list_for_owner(
        self,
        owner_user_id: UUID,
        *,
        include_archived: bool,
    ) -> list[PipelineRecord]:
        rows = await self._fetch(
            "SELECT * FROM pipelines WHERE owner_user_id = $1 AND ($2 OR archived_at IS NULL) ORDER BY created_at DESC",
            owner_user_id,
            include_archived,
        )
        return [PipelineRecord(**dict(r)) for r in rows]

    async def update(
        self,
        pipeline_id: UUID,
        *,
        name: str | None,
        description: str | None,
    ) -> PipelineRecord:
        row = await self._fetchrow(
            "UPDATE pipelines SET name = COALESCE($2, name), description = COALESCE($3, description), updated_at = now() WHERE id = $1 RETURNING *",
            pipeline_id,
            name,
            description,
        )
        return PipelineRecord(**dict(row))

    async def archive(self, pipeline_id: UUID) -> PipelineRecord:
        row = await self._fetchrow(
            "UPDATE pipelines SET archived_at = now(), updated_at = now() WHERE id = $1 RETURNING *",
            pipeline_id,
        )
        return PipelineRecord(**dict(row))

    async def unarchive(self, pipeline_id: UUID) -> PipelineRecord:
        row = await self._fetchrow(
            "UPDATE pipelines SET archived_at = NULL, updated_at = now() WHERE id = $1 RETURNING *",
            pipeline_id,
        )
        return PipelineRecord(**dict(row))

    async def delete(self, pipeline_id: UUID) -> None:
        await self._execute(
            "DELETE FROM pipelines WHERE id = $1",
            pipeline_id,
        )

    async def count_for_owner(self, owner_user_id: UUID) -> int:
        return await self._fetchval(
            "SELECT COUNT(*) FROM pipelines WHERE owner_user_id = $1 AND archived_at IS NULL",
            owner_user_id,
        )

    async def _fetchrow(self, query: str, *args):
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def _fetch(self, query: str, *args):
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def _fetchval(self, query: str, *args):
        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def _execute(self, query: str, *args) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(query, *args)
