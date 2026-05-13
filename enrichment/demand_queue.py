from dataclasses import dataclass


DEMAND_FINAL_STATUSES = frozenset(
    {"cache_hit", "enriched", "no_public_contact", "failed_terminal", "cancelled"}
)

_SQL_HAS_PENDING_DEMAND = """
    SELECT EXISTS (
        SELECT 1
        FROM app_private.enrichment_job_items item
        JOIN app_private.enrichment_jobs job ON job.id = item.job_id
        WHERE item.status IN ('pending', 'failed_retryable')
          AND job.status IN ('queued', 'running')
          AND (item.lease_expires_at IS NULL OR item.lease_expires_at <= now())
    )
"""

_SQL_CLAIM_DEMAND_ITEMS = """
    WITH due AS (
        SELECT item.id
        FROM app_private.enrichment_job_items item
        JOIN app_private.enrichment_jobs job ON job.id = item.job_id
        WHERE item.status IN ('pending', 'failed_retryable')
          AND job.status IN ('queued', 'running')
          AND (item.lease_expires_at IS NULL OR item.lease_expires_at <= now())
        ORDER BY item.priority DESC, job.created_at, item.id
        LIMIT $2
        FOR UPDATE SKIP LOCKED
    ),
    claimed AS (
        UPDATE app_private.enrichment_job_items item
        SET status = 'leased',
            locked_by = $1,
            locked_at = now(),
            lease_expires_at = now() + make_interval(secs => $3),
            attempts = item.attempts + 1,
            updated_at = now()
        FROM due
        WHERE item.id = due.id
        RETURNING item.id, item.job_id, item.account_id,
                  item.cnpj_basico, item.cnpj_ordem, item.cnpj_dv,
                  item.attempts, item.priority
    )
    UPDATE app_private.enrichment_jobs job
    SET status = 'running',
        started_at = COALESCE(job.started_at, now()),
        updated_at = now()
    FROM claimed
    WHERE job.id = claimed.job_id
    RETURNING claimed.id, claimed.job_id, claimed.account_id,
              claimed.cnpj_basico, claimed.cnpj_ordem, claimed.cnpj_dv,
              claimed.attempts, claimed.priority
"""

_SQL_COMPLETE_DEMAND_ITEM = """
    UPDATE app_private.enrichment_job_items
    SET status = $2,
        result_source = $3,
        last_error = $4,
        locked_by = NULL,
        locked_at = NULL,
        lease_expires_at = NULL,
        updated_at = now()
    WHERE id = $1
    RETURNING job_id
"""

_SQL_REFRESH_JOB_COUNTERS = """
    WITH counts AS (
        SELECT
            job_id,
            count(*) FILTER (WHERE status IN ('cache_hit','enriched')) AS ready_count,
            count(*) FILTER (WHERE status = 'cache_hit') AS cache_hit_count,
            count(*) FILTER (WHERE status IN ('skipped_inactive','cancelled')) AS skipped_count,
            count(*) FILTER (WHERE status IN ('failed_retryable','failed_terminal')) AS failed_count,
            bool_or(status IN ('pending','leased','failed_retryable')) AS has_open,
            bool_or(status IN ('failed_retryable','failed_terminal')) AS has_errors
        FROM app_private.enrichment_job_items
        WHERE job_id = $1
        GROUP BY job_id
    )
    UPDATE app_private.enrichment_jobs job
    SET ready_count = counts.ready_count,
        cache_hit_count = counts.cache_hit_count,
        skipped_count = counts.skipped_count,
        failed_count = counts.failed_count,
        status = CASE
            WHEN counts.has_open THEN job.status
            WHEN counts.has_errors THEN 'completed_with_errors'
            ELSE 'completed'
        END,
        completed_at = CASE
            WHEN counts.has_open THEN job.completed_at
            ELSE COALESCE(job.completed_at, now())
        END,
        updated_at = now()
    FROM counts
    WHERE job.id = counts.job_id
"""

_SQL_RELEASE_STALE_DEMAND_ITEMS = """
    UPDATE app_private.enrichment_job_items
    SET status = 'pending',
        locked_by = NULL,
        locked_at = NULL,
        lease_expires_at = NULL,
        updated_at = now()
    WHERE status = 'leased'
      AND lease_expires_at IS NOT NULL
      AND lease_expires_at < now()
    RETURNING id
"""

_SQL_COUNT_PUBLISHED_CONTACTS = """
    SELECT count(*)
    FROM paid_enrichment.published_contacts
    WHERE cnpj_basico = $1 AND cnpj_ordem = $2 AND cnpj_dv = $3
"""


@dataclass(frozen=True)
class DemandItem:
    id: int
    job_id: int
    account_id: str
    cnpj_basico: str
    cnpj_ordem: str
    cnpj_dv: str
    attempts: int
    priority: int

    @property
    def cnpj(self) -> str:
        return f"{self.cnpj_basico}{self.cnpj_ordem}{self.cnpj_dv}"


def _row_to_item(row) -> DemandItem:
    return DemandItem(
        id=row["id"],
        job_id=row["job_id"],
        account_id=row["account_id"],
        cnpj_basico=row["cnpj_basico"],
        cnpj_ordem=row["cnpj_ordem"],
        cnpj_dv=row["cnpj_dv"],
        attempts=row["attempts"],
        priority=row["priority"],
    )


async def has_pending_demand(pool) -> bool:
    async with pool.acquire() as conn:
        return bool(await conn.fetchval(_SQL_HAS_PENDING_DEMAND))


async def claim_demand_items(
    pool,
    *,
    worker_id: str,
    batch_size: int,
    lease_seconds: int,
) -> list[DemandItem]:
    if not worker_id:
        raise ValueError("worker_id is required")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL_CLAIM_DEMAND_ITEMS, worker_id, batch_size, lease_seconds)
    return [_row_to_item(row) for row in rows]


async def complete_demand_item(
    pool,
    *,
    item_id: int,
    status: str,
    result_source: str | None = None,
    last_error: str | None = None,
) -> None:
    if status not in DEMAND_FINAL_STATUSES and status != "failed_retryable":
        raise ValueError(f"Invalid demand item status: {status}")
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                _SQL_COMPLETE_DEMAND_ITEM,
                item_id,
                status,
                result_source,
                last_error,
            )
            if row:
                await conn.execute(_SQL_REFRESH_JOB_COUNTERS, row["job_id"])


async def release_stale_demand_items(pool) -> int:
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL_RELEASE_STALE_DEMAND_ITEMS)
    return len(rows)


async def count_published_contacts(pool, item: DemandItem) -> int:
    async with pool.acquire() as conn:
        value = await conn.fetchval(
            _SQL_COUNT_PUBLISHED_CONTACTS,
            item.cnpj_basico,
            item.cnpj_ordem,
            item.cnpj_dv,
        )
    return int(value or 0)
