"""Repository for pipeline card CRUD operations."""
from __future__ import annotations

import json
from uuid import UUID

from modules.pipeline.cards.schemas import (
    CardInPipelineSummary,
    CardRecord,
    CardWithCompany,
    CompanySummary,
    ImportBatchRecord,
    ImportRowRecord,
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

    async def existing_cnpjs_in_basico(self, cnpjs: list[str]) -> set[str]:
        return await self.existing_cnpjs(cnpjs)

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

    async def existing_card_ids_in_pipeline_by_cnpj(
        self,
        pipeline_id: UUID,
        cnpjs: list[str],
    ) -> dict[str, UUID]:
        rows = await self._fetch(
            "SELECT cnpj_basico, id FROM pipeline_cards"
            " WHERE pipeline_id = $1 AND cnpj_basico = ANY($2::char(8)[])",
            pipeline_id,
            cnpjs,
        )
        return {row["cnpj_basico"]: row["id"] for row in rows}

    async def insert(
        self,
        *,
        pipeline_id: UUID,
        stage_id: UUID,
        cnpj_basico: str,
        position: int,
        display_name: str | None,
        estimated_value_cents: int | None,
        notes: str | None,
    ) -> CardRecord:
        row = await self._fetchrow(
            "INSERT INTO pipeline_cards"
            " (pipeline_id, stage_id, cnpj_basico, position, display_name,"
            " estimated_value_cents, notes)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *",
            pipeline_id,
            stage_id,
            cnpj_basico,
            position,
            display_name,
            estimated_value_cents,
            notes,
        )
        return CardRecord(**dict(row))

    async def bulk_insert(self, rows: list[dict]) -> list[CardRecord]:
        results: list[CardRecord] = []
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for row in rows:
                    inserted = await conn.fetchrow(
                        "INSERT INTO pipeline_cards"
                        " (pipeline_id, stage_id, cnpj_basico, position, display_name,"
                        " estimated_value_cents, notes)"
                        " VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *",
                        row["pipeline_id"],
                        row["stage_id"],
                        row["cnpj_basico"],
                        row["position"],
                        row.get("display_name"),
                        row.get("estimated_value_cents"),
                        row.get("notes"),
                    )
                    results.append(CardRecord(**dict(inserted)))
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
        display_name: str | None,
        estimated_value_cents: int | None,
        notes: str | None,
    ) -> CardRecord:
        row = await self._fetchrow(
            "UPDATE pipeline_cards"
            " SET display_name = COALESCE($2, display_name),"
            " estimated_value_cents = COALESCE($3, estimated_value_cents),"
            " notes = COALESCE($4, notes),"
            " updated_at = now()"
            " WHERE id = $1 RETURNING *",
            card_id,
            display_name,
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

    async def first_stage_id_in_pipeline(self, pipeline_id: UUID) -> UUID | None:
        return await self._fetchval(
            "SELECT id FROM pipeline_stages WHERE pipeline_id = $1 ORDER BY position LIMIT 1",
            pipeline_id,
        )

    async def stage_exists_in_pipeline(self, stage_id: UUID, *, pipeline_id: UUID) -> bool:
        return await self._fetchval(
            "SELECT EXISTS ("
            " SELECT 1 FROM pipeline_stages WHERE id = $1 AND pipeline_id = $2"
            ")",
            stage_id,
            pipeline_id,
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
        from_stage_id: UUID | None,
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

    async def delete_import_batch_for_file(
        self,
        *,
        owner_user_id: UUID,
        pipeline_id: UUID,
        filename: str,
        file_size_bytes: int,
    ) -> None:
        await self._execute(
            "DELETE FROM pipeline_card_import_batches"
            " WHERE owner_user_id = $1"
            "   AND pipeline_id = $2"
            "   AND filename = $3"
            "   AND file_size_bytes = $4",
            owner_user_id,
            pipeline_id,
            filename,
            file_size_bytes,
        )

    async def insert_import_batch(
        self,
        *,
        owner_user_id: UUID,
        pipeline_id: UUID,
        stage_id: UUID,
        filename: str,
        file_size_bytes: int,
        content_sha256: str,
        total_rows: int,
        created_count: int,
        skipped_count: int,
    ) -> ImportBatchRecord:
        row = await self._fetchrow(
            "INSERT INTO pipeline_card_import_batches"
            " (owner_user_id, pipeline_id, stage_id, filename, file_size_bytes,"
            " content_sha256, total_rows, created_count, skipped_count)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)"
            " RETURNING *",
            owner_user_id,
            pipeline_id,
            stage_id,
            filename,
            file_size_bytes,
            content_sha256,
            total_rows,
            created_count,
            skipped_count,
        )
        return ImportBatchRecord(**dict(row))

    async def insert_import_rows(self, rows: list[dict]) -> list[ImportRowRecord]:
        results: list[ImportRowRecord] = []
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for row in rows:
                    inserted = await conn.fetchrow(
                        "INSERT INTO pipeline_card_import_rows"
                        " (batch_id, line_number, raw_cnpj, cnpj_basico, display_name,"
                        " card_id, status, reason, metadata)"
                        " VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)"
                        " RETURNING *",
                        row["batch_id"],
                        row["line_number"],
                        row["raw_cnpj"],
                        row.get("cnpj_basico"),
                        row.get("display_name"),
                        row.get("card_id"),
                        row["status"],
                        row.get("reason"),
                        row.get("metadata_json", "{}"),
                    )
                    results.append(self._import_row_from_row(inserted))
        return results

    async def list_import_batches(self, pipeline_id: UUID) -> list[ImportBatchRecord]:
        rows = await self._fetch(
            "SELECT * FROM pipeline_card_import_batches"
            " WHERE pipeline_id = $1"
            " ORDER BY created_at DESC",
            pipeline_id,
        )
        return [ImportBatchRecord(**dict(row)) for row in rows]

    async def list_import_rows_for_card(self, card_id: UUID) -> list[ImportRowRecord]:
        rows = await self._fetch(
            "SELECT * FROM pipeline_card_import_rows"
            " WHERE card_id = $1"
            " ORDER BY created_at DESC, line_number",
            card_id,
        )
        return [self._import_row_from_row(row) for row in rows]

    def _import_row_from_row(self, row) -> ImportRowRecord:
        row_dict = dict(row)
        metadata = row_dict.get("metadata")
        if isinstance(metadata, str):
            row_dict["metadata"] = json.loads(metadata)
        return ImportRowRecord(**row_dict)

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
