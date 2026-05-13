import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from models.enrichment_jobs import (
    EnrichmentEstimateRequest,
    EnrichmentEstimateResponse,
    EnrichmentJobCreateRequest,
    EnrichmentJobItem,
    EnrichmentJobItemsResponse,
    EnrichmentJobListResponse,
    EnrichmentJobResponse,
    EnrichmentJobSummary,
)
from services.query_builder import build_enrichment_candidate_query


MAX_FREE_ESTIMATE_SECONDS_PER_ITEM = 8


@dataclass(frozen=True)
class Candidate:
    cnpj_basico: str
    cnpj_ordem: str
    cnpj_dv: str

    @property
    def cnpj(self) -> str:
        return f"{self.cnpj_basico}{self.cnpj_ordem}{self.cnpj_dv}"


_SQL_ACTIVE_SELECTED_CNPJS = """
    SELECT est.cnpj_basico, est.cnpj_ordem, est.cnpj_dv
    FROM estabelecimentos est
    WHERE est.situacao_cadastral = 2
      AND est.cnpj_basico || est.cnpj_ordem || est.cnpj_dv = ANY($1::text[])
    ORDER BY est.cnpj_basico, est.cnpj_ordem, est.cnpj_dv
"""

_SQL_FRESH_CACHE_HITS = """
    SELECT pc.cnpj_basico || pc.cnpj_ordem || pc.cnpj_dv AS cnpj
    FROM paid_enrichment.published_contacts pc
    WHERE pc.cnpj_basico || pc.cnpj_ordem || pc.cnpj_dv = ANY($1::text[])
    GROUP BY pc.cnpj_basico, pc.cnpj_ordem, pc.cnpj_dv
    HAVING max(pc.last_seen) >= now() - make_interval(days => $2)
"""

_SQL_INSERT_JOB = """
    INSERT INTO app_private.enrichment_jobs (
        account_id, created_by, source_type, filter_hash, filters_json,
        status, priority, plan_key, requested_count, accepted_count,
        cache_hit_count, skipped_count, failed_count, ready_count,
        cost_credits, idempotency_key
    )
    VALUES (
        $1, $2, $3, $4, $5::jsonb,
        'queued', 1000, $6, $7, $8,
        $9, $10, 0, $9,
        $11, $12
    )
    ON CONFLICT (account_id, idempotency_key)
    DO UPDATE SET updated_at = app_private.enrichment_jobs.updated_at
    RETURNING id, status, created_at, idempotency_key
"""

_SQL_INSERT_ITEM = """
    INSERT INTO app_private.enrichment_job_items (
        job_id, account_id, cnpj_basico, cnpj_ordem, cnpj_dv,
        status, priority, result_source, cache_fresh_until
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now() + make_interval(days => $9))
    ON CONFLICT (job_id, cnpj_basico, cnpj_ordem, cnpj_dv) DO NOTHING
"""

_SQL_LIST_JOBS = """
    SELECT id, status, source_type, requested_count, accepted_count,
           cache_hit_count, skipped_count, failed_count, ready_count,
           cost_credits, created_at, started_at, completed_at, cancelled_at
    FROM app_private.enrichment_jobs
    WHERE account_id = $1
    ORDER BY created_at DESC, id DESC
    LIMIT $2
"""

_SQL_GET_JOB = """
    SELECT id, status, source_type, requested_count, accepted_count,
           cache_hit_count, skipped_count, failed_count, ready_count,
           cost_credits, created_at, started_at, completed_at, cancelled_at
    FROM app_private.enrichment_jobs
    WHERE account_id = $1 AND id = $2
"""

_SQL_LIST_ITEMS = """
    SELECT cnpj_basico || cnpj_ordem || cnpj_dv AS cnpj, status, result_source,
           attempts, last_error, updated_at
    FROM app_private.enrichment_job_items
    WHERE account_id = $1 AND job_id = $2
    ORDER BY id
    LIMIT $3 OFFSET $4
"""

_SQL_CANCEL_JOB = """
    UPDATE app_private.enrichment_jobs
    SET status = 'cancelled',
        cancelled_at = now(),
        updated_at = now()
    WHERE account_id = $1
      AND id = $2
      AND status IN ('queued', 'running')
"""

_SQL_CANCEL_ITEMS = """
    UPDATE app_private.enrichment_job_items
    SET status = 'cancelled',
        updated_at = now()
    WHERE account_id = $1
      AND job_id = $2
      AND status IN ('pending', 'failed_retryable')
    RETURNING id
"""

_SQL_EXPORT_ITEMS = """
    SELECT
        eji.cnpj_basico || eji.cnpj_ordem || eji.cnpj_dv AS cnpj,
        eji.status,
        e.razao_social,
        NULLIF(est.nome_fantasia, '') AS nome_fantasia,
        est.uf,
        m.descricao AS municipio,
        string_agg(DISTINCT pc.normalized_value, ' | ' ORDER BY pc.normalized_value)
            FILTER (WHERE pc.contact_type = 'email') AS emails,
        string_agg(DISTINCT pc.value, ' | ' ORDER BY pc.value)
            FILTER (WHERE pc.contact_type IN ('phone', 'whatsapp')) AS telefones,
        string_agg(DISTINCT pc.evidence_url, ' | ' ORDER BY pc.evidence_url)
            FILTER (WHERE pc.evidence_url IS NOT NULL) AS evidencias
    FROM app_private.enrichment_job_items eji
    JOIN estabelecimentos est
      ON est.cnpj_basico = eji.cnpj_basico
     AND est.cnpj_ordem = eji.cnpj_ordem
     AND est.cnpj_dv = eji.cnpj_dv
    JOIN empresas e ON e.cnpj_basico = eji.cnpj_basico
    LEFT JOIN municipios m ON m.codigo = est.municipio
    LEFT JOIN paid_enrichment.published_contacts pc
      ON pc.cnpj_basico = eji.cnpj_basico
     AND pc.cnpj_ordem = eji.cnpj_ordem
     AND pc.cnpj_dv = eji.cnpj_dv
    WHERE eji.account_id = $1 AND eji.job_id = $2
    GROUP BY eji.id, eji.cnpj_basico, eji.cnpj_ordem, eji.cnpj_dv,
             eji.status, e.razao_social, est.nome_fantasia, est.uf, m.descricao
    ORDER BY eji.id
"""


def _rows_to_candidates(rows) -> list[Candidate]:
    return [
        Candidate(row["cnpj_basico"], row["cnpj_ordem"], row["cnpj_dv"])
        for row in rows
    ]


def _json_dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _filter_hash(payload: EnrichmentEstimateRequest) -> str:
    source = {
        "cnpjs": payload.cnpjs,
        "filters": payload.filters.model_dump(mode="json") if payload.filters else None,
        "max_items": payload.max_items,
        "stale_after_days": payload.stale_after_days,
    }
    return hashlib.sha256(_json_dump(source).encode("utf-8")).hexdigest()


async def _materialize_candidates(conn, payload: EnrichmentEstimateRequest) -> tuple[int, list[Candidate]]:
    if payload.cnpjs:
        rows = await conn.fetch(_SQL_ACTIVE_SELECTED_CNPJS, payload.cnpjs)
        return len(payload.cnpjs), _rows_to_candidates(rows)

    query, params = build_enrichment_candidate_query(
        payload.filters,
        max_items=payload.max_items,
    )
    rows = await conn.fetch(query, *params)
    candidates = _rows_to_candidates(rows)
    return len(candidates), candidates


async def _fresh_cache_hits(conn, candidates: list[Candidate], stale_after_days: int) -> set[str]:
    if not candidates:
        return set()
    rows = await conn.fetch(
        _SQL_FRESH_CACHE_HITS,
        [candidate.cnpj for candidate in candidates],
        stale_after_days,
    )
    return {row["cnpj"] for row in rows}


def _estimate_response(
    payload: EnrichmentEstimateRequest,
    *,
    requested_count: int,
    candidates: list[Candidate],
    cache_hits: set[str],
) -> EnrichmentEstimateResponse:
    eligible_count = len(candidates)
    cache_hit_count = len(cache_hits)
    new_count = eligible_count - cache_hit_count
    skipped_inactive_count = max(requested_count - eligible_count, 0)
    return EnrichmentEstimateResponse(
        source_type=payload.source_type,
        requested_count=requested_count,
        eligible_count=eligible_count,
        cache_hit_count=cache_hit_count,
        new_count=new_count,
        skipped_inactive_count=skipped_inactive_count,
        cost_credits=new_count,
        estimated_seconds_min=new_count,
        estimated_seconds_max=new_count * MAX_FREE_ESTIMATE_SECONDS_PER_ITEM,
    )


async def estimate_enrichment_job(pool, payload: EnrichmentEstimateRequest) -> EnrichmentEstimateResponse:
    async with pool.acquire() as conn:
        requested_count, candidates = await _materialize_candidates(conn, payload)
        cache_hits = await _fresh_cache_hits(conn, candidates, payload.stale_after_days)
    return _estimate_response(
        payload,
        requested_count=requested_count,
        candidates=candidates,
        cache_hits=cache_hits,
    )


async def create_enrichment_job(
    pool,
    *,
    account_id: str,
    created_by: str,
    payload: EnrichmentJobCreateRequest,
    idempotency_key: str | None,
    plan_key: str = "default",
) -> EnrichmentJobResponse:
    async with pool.acquire() as conn:
        requested_count, candidates = await _materialize_candidates(conn, payload)
        cache_hits = await _fresh_cache_hits(conn, candidates, payload.stale_after_days)
        estimate = _estimate_response(
            payload,
            requested_count=requested_count,
            candidates=candidates,
            cache_hits=cache_hits,
        )
        filters_json = payload.filters.model_dump(mode="json") if payload.filters else {"cnpjs": payload.cnpjs}
        async with conn.transaction():
            job_row = await conn.fetchrow(
                _SQL_INSERT_JOB,
                account_id,
                created_by,
                payload.source_type,
                _filter_hash(payload),
                _json_dump(filters_json),
                plan_key,
                estimate.requested_count,
                estimate.eligible_count,
                estimate.cache_hit_count,
                estimate.skipped_inactive_count,
                estimate.cost_credits,
                idempotency_key,
            )
            job_id = job_row["id"]
            for candidate in candidates:
                is_cache_hit = candidate.cnpj in cache_hits
                await conn.execute(
                    _SQL_INSERT_ITEM,
                    job_id,
                    account_id,
                    candidate.cnpj_basico,
                    candidate.cnpj_ordem,
                    candidate.cnpj_dv,
                    "cache_hit" if is_cache_hit else "pending",
                    1000 if not is_cache_hit else 100,
                    "cache" if is_cache_hit else None,
                    payload.stale_after_days,
                )
    return EnrichmentJobResponse(
        **estimate.model_dump(),
        job_id=job_id,
        status=job_row["status"],
        created_at=job_row["created_at"],
        idempotency_key=job_row["idempotency_key"],
    )


def _job_summary(row) -> EnrichmentJobSummary:
    return EnrichmentJobSummary(**dict(row))


async def list_enrichment_jobs(pool, *, account_id: str, limit: int = 20) -> EnrichmentJobListResponse:
    bounded_limit = max(1, min(limit, 100))
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL_LIST_JOBS, account_id, bounded_limit)
    return EnrichmentJobListResponse(jobs=[_job_summary(row) for row in rows])


async def get_enrichment_job(pool, *, account_id: str, job_id: int) -> EnrichmentJobSummary | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SQL_GET_JOB, account_id, job_id)
    return _job_summary(row) if row else None


async def list_enrichment_job_items(
    pool,
    *,
    account_id: str,
    job_id: int,
    limit: int = 100,
    offset: int = 0,
) -> EnrichmentJobItemsResponse:
    bounded_limit = max(1, min(limit, 500))
    safe_offset = max(offset, 0)
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL_LIST_ITEMS, account_id, job_id, bounded_limit, safe_offset)
    return EnrichmentJobItemsResponse(
        job_id=job_id,
        items=[EnrichmentJobItem(**dict(row)) for row in rows],
    )


async def cancel_enrichment_job(pool, *, account_id: str, job_id: int) -> int:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(_SQL_CANCEL_JOB, account_id, job_id)
            rows = await conn.fetch(_SQL_CANCEL_ITEMS, account_id, job_id)
    return len(rows)


async def export_enrichment_job_csv(pool, *, account_id: str, job_id: int) -> str:
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL_EXPORT_ITEMS, account_id, job_id)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "cnpj",
            "status",
            "razao_social",
            "nome_fantasia",
            "uf",
            "municipio",
            "emails",
            "telefones",
            "evidencias",
        ],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row[field] for field in writer.fieldnames})
    return output.getvalue()
