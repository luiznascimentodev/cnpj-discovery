"""Repository for pipeline stage CRUD operations."""
from __future__ import annotations

from uuid import UUID

from modules.pipeline.stages.schemas import StageRecord


class StageRepository:
    def __init__(self, pool):
        self._pool = pool

    async def insert(
        self,
        *,
        pipeline_id: UUID,
        name: str,
        position: int,
        color: str | None,
        is_won: bool,
        is_lost: bool,
    ) -> StageRecord:
        row = await self._fetchrow(
            "INSERT INTO pipeline_stages (pipeline_id, name, position, color, is_won, is_lost)"
            " VALUES ($1, $2, $3, $4, $5, $6) RETURNING *",
            pipeline_id,
            name,
            position,
            color,
            is_won,
            is_lost,
        )
        return StageRecord(**dict(row))

    async def bulk_insert(
        self,
        pipeline_id: UUID,
        defaults: list[dict],
    ) -> list[StageRecord]:
        results: list[StageRecord] = []
        for d in defaults:
            record = await self.insert(
                pipeline_id=pipeline_id,
                name=d["name"],
                position=d["position"],
                color=d.get("color"),
                is_won=d.get("is_won", False),
                is_lost=d.get("is_lost", False),
            )
            results.append(record)
        return results

    async def list_for_pipeline(self, pipeline_id: UUID) -> list[StageRecord]:
        rows = await self._fetch(
            "SELECT * FROM pipeline_stages WHERE pipeline_id = $1 ORDER BY position",
            pipeline_id,
        )
        return [StageRecord(**dict(r)) for r in rows]

    async def get_in_pipeline(
        self,
        stage_id: UUID,
        *,
        pipeline_id: UUID,
    ) -> StageRecord | None:
        row = await self._fetchrow(
            "SELECT * FROM pipeline_stages WHERE id = $1 AND pipeline_id = $2",
            stage_id,
            pipeline_id,
        )
        return StageRecord(**dict(row)) if row else None

    async def update(
        self,
        stage_id: UUID,
        *,
        name: str | None,
        color: str | None,
        is_won: bool | None,
        is_lost: bool | None,
    ) -> StageRecord:
        row = await self._fetchrow(
            "UPDATE pipeline_stages"
            " SET name = COALESCE($2, name),"
            " color = COALESCE($3, color),"
            " is_won = COALESCE($4, is_won),"
            " is_lost = COALESCE($5, is_lost),"
            " updated_at = now()"
            " WHERE id = $1 RETURNING *",
            stage_id,
            name,
            color,
            is_won,
            is_lost,
        )
        return StageRecord(**dict(row))

    async def count_stages(self, pipeline_id: UUID) -> int:
        return await self._fetchval(
            "SELECT COUNT(*) FROM pipeline_stages WHERE pipeline_id = $1",
            pipeline_id,
        )

    async def count_cards_in_stage(self, stage_id: UUID) -> int:
        return await self._fetchval(
            "SELECT COUNT(*) FROM pipeline_cards WHERE stage_id = $1",
            stage_id,
        )

    async def reorder(self, pipeline_id: UUID, stage_ids: list[UUID]) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SET CONSTRAINTS ALL DEFERRED")
                for idx, sid in enumerate(stage_ids):
                    await conn.execute(
                        "UPDATE pipeline_stages"
                        " SET position = $2, updated_at = now()"
                        " WHERE id = $1 AND pipeline_id = $3",
                        sid,
                        idx,
                        pipeline_id,
                    )

    async def move_cards_and_delete(
        self,
        stage_id: UUID,
        target_stage_id: UUID,
    ) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SET CONSTRAINTS ALL DEFERRED")
                max_pos = await conn.fetchval(
                    "SELECT COALESCE(MAX(position), -1) FROM pipeline_cards WHERE stage_id = $1",
                    target_stage_id,
                )
                rows = await conn.fetch(
                    "SELECT id FROM pipeline_cards WHERE stage_id = $1 ORDER BY position",
                    stage_id,
                )
                for i, row in enumerate(rows):
                    await conn.execute(
                        "UPDATE pipeline_cards"
                        " SET stage_id = $2, position = $3, updated_at = now()"
                        " WHERE id = $1",
                        row["id"],
                        target_stage_id,
                        max_pos + 1 + i,
                    )
                await conn.execute(
                    "DELETE FROM pipeline_stages WHERE id = $1",
                    stage_id,
                )

    async def delete(self, stage_id: UUID) -> None:
        await self._execute(
            "DELETE FROM pipeline_stages WHERE id = $1",
            stage_id,
        )

    async def max_position_in_pipeline(self, pipeline_id: UUID) -> int | None:
        return await self._fetchval(
            "SELECT MAX(position) FROM pipeline_stages WHERE pipeline_id = $1",
            pipeline_id,
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
