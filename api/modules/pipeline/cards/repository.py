"""Repository for pipeline card CRUD operations."""
from __future__ import annotations

from uuid import UUID

from modules.pipeline.cards.schemas import (
    CardInPipelineSummary,
    CardRecord,
    CardWithCompany,
    CompanySummary,
)


class CardRepository:
    def __init__(self, pool):
        self._pool = pool

    async def cnpj_exists(self, cnpj_basico: str) -> bool:
        return await self._fetchval(
            "SELECT EXISTS (SELECT 1 FROM empresas WHERE cnpj_basico = $1)",
            cnpj_basico,
        )

    async def existing_cnpjs(self, cnpjs: list[str]) -> set[str]:
        rows = await self._fetch(
            "SELECT cnpj_basico FROM empresas WHERE cnpj_basico = ANY($1::char(8)[])",
            cnpjs,
        )
        return {row["cnpj_basico"] for row in rows}

    async def card_exists_in_pipeline(
        self,
        pipeline_id: UUID,
        cnpj_basico: str,
    ) -> bool:
        return await self._fetchval(
            "SELECT EXISTS ("
            " SELECT 1 FROM pipeline_cards"
            " WHERE pipeline_id = $1 AND cnpj_basico = $2"
            ")",
            pipeline_id,
            cnpj_basico,
        )

    async def existing_cards_in_pipeline_by_cnpj(
        self,
        pipeline_id: UUID,
        cnpjs: list[str],
    ) -> set[str]:
        rows = await self._fetch(
            "SELECT cnpj_basico FROM pipeline_cards"
            " WHERE pipeline_id = $1 AND cnpj_basico = ANY($2::char(8)[])",
            pipeline_id,
            cnpjs,
        )
        return {row["cnpj_basico"] for row in rows}

    async def insert(
        self,
        *,
        pipeline_id: UUID,
        stage_id: UUID,
        cnpj_basico: str,
        position: int,
        estimated_value_cents: int | None,
        notes: str | None,
    ) -> CardRecord:
        row = await self._fetchrow(
            "INSERT INTO pipeline_cards"
            " (pipeline_id, stage_id, cnpj_basico, position, estimated_value_cents, notes)"
            " VALUES ($1, $2, $3, $4, $5, $6) RETURNING *",
            pipeline_id,
            stage_id,
            cnpj_basico,
            position,
            estimated_value_cents,
            notes,
        )
        return CardRecord(**dict(row))

    async def bulk_insert(self, rows: list[dict]) -> list[CardRecord]:
        results: list[CardRecord] = []
        for row in rows:
            record = await self.insert(
                pipeline_id=row["pipeline_id"],
                stage_id=row["stage_id"],
                cnpj_basico=row["cnpj_basico"],
                position=row["position"],
                estimated_value_cents=row.get("estimated_value_cents"),
                notes=row.get("notes"),
            )
            results.append(record)
        return results

    async def list_with_company_summary(
        self,
        pipeline_id: UUID,
    ) -> list[CardWithCompany]:
        rows = await self._fetch(
            "SELECT c.*,"
            " e.razao_social,"
            " est.uf"
            " FROM pipeline_cards c"
            " LEFT JOIN empresas e ON e.cnpj_basico = c.cnpj_basico"
            " LEFT JOIN LATERAL ("
            "   SELECT uf FROM estabelecimentos est"
            "   WHERE est.cnpj_basico = c.cnpj_basico"
            "     AND est.cnpj_ordem = '0001'"
            "     AND est.identificador_matriz_filial = 1"
            "   LIMIT 1"
            " ) est ON true"
            " WHERE c.pipeline_id = $1"
            " ORDER BY c.stage_id, c.position",
            pipeline_id,
        )
        results: list[CardWithCompany] = []
        for row in rows:
            row_dict = dict(row)
            razao_social = row_dict.pop("razao_social", None)
            uf = row_dict.pop("uf", None)
            card = CardRecord(**row_dict)
            company = CompanySummary(razao_social=razao_social, uf=uf)
            results.append(CardWithCompany(card=card, company=company))
        return results

    async def get_in_pipeline(
        self,
        card_id: UUID,
        *,
        pipeline_id: UUID,
    ) -> CardRecord | None:
        row = await self._fetchrow(
            "SELECT * FROM pipeline_cards WHERE id = $1 AND pipeline_id = $2",
            card_id,
            pipeline_id,
        )
        return CardRecord(**dict(row)) if row else None

    async def update(
        self,
        card_id: UUID,
        *,
        estimated_value_cents: int | None,
        notes: str | None,
    ) -> CardRecord:
        row = await self._fetchrow(
            "UPDATE pipeline_cards"
            " SET estimated_value_cents = COALESCE($2, estimated_value_cents),"
            " notes = COALESCE($3, notes),"
            " updated_at = now()"
            " WHERE id = $1 RETURNING *",
            card_id,
            estimated_value_cents,
            notes,
        )
        return CardRecord(**dict(row))

    async def move(
        self,
        card_id: UUID,
        *,
        stage_id: UUID,
        position: int,
    ) -> CardRecord:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SET CONSTRAINTS ALL DEFERRED")
                row = await conn.fetchrow(
                    "UPDATE pipeline_cards"
                    " SET stage_id = $2, position = $3, updated_at = now()"
                    " WHERE id = $1 RETURNING *",
                    card_id,
                    stage_id,
                    position,
                )
        return CardRecord(**dict(row))

    async def delete(self, card_id: UUID) -> None:
        await self._execute(
            "DELETE FROM pipeline_cards WHERE id = $1",
            card_id,
        )

    async def max_position_in_stage(self, stage_id: UUID) -> int | None:
        return await self._fetchval(
            "SELECT MAX(position) FROM pipeline_cards WHERE stage_id = $1",
            stage_id,
        )

    async def pipelines_containing_cnpj(
        self,
        owner_user_id: UUID,
        cnpj_basico: str,
    ) -> list[CardInPipelineSummary]:
        rows = await self._fetch(
            "SELECT p.id AS pipeline_id, p.name AS pipeline_name,"
            " c.id AS card_id, s.id AS stage_id, s.name AS stage_name"
            " FROM pipelines p"
            " JOIN pipeline_cards c ON c.pipeline_id = p.id"
            " JOIN pipeline_stages s ON s.id = c.stage_id"
            " WHERE p.owner_user_id = $1"
            "   AND c.cnpj_basico = $2"
            "   AND p.archived_at IS NULL",
            owner_user_id,
            cnpj_basico,
        )
        return [
            CardInPipelineSummary(
                pipeline_id=row["pipeline_id"],
                pipeline_name=row["pipeline_name"],
                card_id=row["card_id"],
                stage_id=row["stage_id"],
                stage_name=row["stage_name"],
            )
            for row in rows
        ]

    async def insert_stage_change(
        self,
        card_id: UUID,
        *,
        from_stage_id: UUID,
        to_stage_id: UUID,
        changed_by_user_id: UUID,
    ) -> None:
        await self._execute(
            "INSERT INTO pipeline_card_stage_changes"
            " (card_id, from_stage_id, to_stage_id, changed_by_user_id)"
            " VALUES ($1, $2, $3, $4)",
            card_id,
            from_stage_id,
            to_stage_id,
            changed_by_user_id,
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
