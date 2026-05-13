"""Fila persistente do crawler com resume real.

`claim_crawl_requests` é a primitiva de resume:

- Nunca retorna rows `done`/`error`/`blocked`/`skipped`.
- Nunca retorna rows que outro worker já está processando
  (`FOR UPDATE SKIP LOCKED`).
- Recupera leases mortos: linhas em `running` com `updated_at`
  anterior a `now() - lease_seconds` voltam à fila automaticamente.
- Idempotência extra: `crawl_pages` tem `UNIQUE(url, content_hash)`
  — se a mesma URL é refetcheada com o mesmo conteúdo, não duplica.

`updated_at` é o ponto de lease porque toda mudança de status passa
por aqui e atualiza esse timestamp.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

DEFAULT_LEASE_SECONDS = 600
DEFAULT_CLAIM_BATCH = 20

TERMINAL_REQUEST_STATUSES = frozenset({"error", "blocked", "skipped"})

_SQL_CLAIM_CRAWL_REQUESTS = """
    WITH due AS (
        SELECT id
        FROM paid_enrichment.crawl_requests
        WHERE next_run_at <= now()
          AND $1::text <> ''
          AND (
                status IN ('pending', 'retry')
                OR (status = 'running' AND updated_at < now() - make_interval(secs => $2::int))
          )
        ORDER BY priority DESC, next_run_at, id
        LIMIT $3::int
        FOR UPDATE SKIP LOCKED
    )
    UPDATE paid_enrichment.crawl_requests cr
    SET status = 'running',
        attempts = cr.attempts + 1,
        updated_at = now(),
        last_error = NULL
    FROM due
    WHERE cr.id = due.id
    RETURNING cr.id, cr.cnpj_basico, cr.cnpj_ordem, cr.cnpj_dv, cr.url, cr.domain,
              cr.priority, cr.depth, cr.attempts, cr.source
"""

_SQL_MARK_DONE = """
    UPDATE paid_enrichment.crawl_requests
    SET status = 'done', content_hash = $2, updated_at = now(), last_error = NULL
    WHERE id = $1
"""

_SQL_MARK_RETRY = """
    UPDATE paid_enrichment.crawl_requests
    SET status = 'retry',
        next_run_at = now() + make_interval(secs => $2),
        last_error = $3,
        updated_at = now()
    WHERE id = $1
"""

_SQL_MARK_TERMINAL = """
    UPDATE paid_enrichment.crawl_requests
    SET status = $2, last_error = $3, updated_at = now()
    WHERE id = $1
"""

_SQL_RELEASE_STALE_REQUESTS = """
    UPDATE paid_enrichment.crawl_requests
    SET status = 'pending', updated_at = now()
    WHERE status = 'running'
      AND updated_at < now() - make_interval(secs => $1)
    RETURNING id
"""

_SQL_GET_HOST = """
    SELECT consecutive_failures, blocked_until, last_fetch_at, crawl_delay_seconds
    FROM paid_enrichment.crawl_hosts
    WHERE domain = $1
"""

_SQL_UPDATE_HOST_FAILURES = """
    INSERT INTO paid_enrichment.crawl_hosts (
        domain, consecutive_failures, blocked_until, last_fetch_at
    )
    VALUES ($1, $2, $3, COALESCE($4, now()))
    ON CONFLICT (domain) DO UPDATE SET
        consecutive_failures = EXCLUDED.consecutive_failures,
        blocked_until = EXCLUDED.blocked_until,
        last_fetch_at = COALESCE(EXCLUDED.last_fetch_at, paid_enrichment.crawl_hosts.last_fetch_at)
"""

_SQL_RESET_HOST_FAILURES = """
    UPDATE paid_enrichment.crawl_hosts
    SET consecutive_failures = 0,
        blocked_until = NULL,
        last_fetch_at = now()
    WHERE domain = $1
"""


@dataclass(frozen=True)
class ClaimedCrawlRequest:
    id: int
    cnpj_basico: str
    cnpj_ordem: str
    cnpj_dv: str
    url: str
    domain: str
    priority: int
    depth: int
    attempts: int
    source: str


@dataclass(frozen=True)
class HostState:
    consecutive_failures: int
    blocked_until: Optional[datetime]
    last_fetch_at: Optional[datetime]
    crawl_delay_seconds: Optional[float]


async def claim_crawl_requests(
    pool,
    *,
    worker_id: str,
    batch_size: int = DEFAULT_CLAIM_BATCH,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> list[ClaimedCrawlRequest]:
    if not worker_id:
        raise ValueError("worker_id is required")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            _SQL_CLAIM_CRAWL_REQUESTS,
            worker_id,
            lease_seconds,
            batch_size,
        )
    return [
        ClaimedCrawlRequest(
            id=row["id"],
            cnpj_basico=row["cnpj_basico"],
            cnpj_ordem=row["cnpj_ordem"],
            cnpj_dv=row["cnpj_dv"],
            url=row["url"],
            domain=row["domain"],
            priority=row["priority"],
            depth=row["depth"],
            attempts=row["attempts"],
            source=row["source"],
        )
        for row in rows
    ]


async def mark_request_done(pool, request_id: int, content_hash: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(_SQL_MARK_DONE, request_id, content_hash)


async def mark_request_retry(
    pool,
    request_id: int,
    *,
    retry_in_seconds: int,
    last_error: str,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            _SQL_MARK_RETRY,
            request_id,
            max(retry_in_seconds, 0),
            last_error,
        )


async def mark_request_terminal(
    pool,
    request_id: int,
    *,
    status: str,
    last_error: str | None = None,
) -> None:
    if status not in TERMINAL_REQUEST_STATUSES:
        raise ValueError(f"Invalid terminal status: {status}")
    async with pool.acquire() as conn:
        await conn.execute(_SQL_MARK_TERMINAL, request_id, status, last_error)


async def release_stale_requests(
    pool,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> int:
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL_RELEASE_STALE_REQUESTS, lease_seconds)
    return len(rows)


async def get_host_state(pool, domain: str) -> Optional[HostState]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SQL_GET_HOST, domain)
    if not row:
        return None
    return HostState(
        consecutive_failures=row["consecutive_failures"] or 0,
        blocked_until=row["blocked_until"],
        last_fetch_at=row["last_fetch_at"],
        crawl_delay_seconds=float(row["crawl_delay_seconds"])
        if row["crawl_delay_seconds"] is not None
        else None,
    )


async def update_host_failures(
    pool,
    domain: str,
    *,
    consecutive_failures: int,
    blocked_until: Optional[datetime] = None,
    last_fetch_at: Optional[datetime] = None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            _SQL_UPDATE_HOST_FAILURES,
            domain,
            consecutive_failures,
            blocked_until,
            last_fetch_at,
        )


async def reset_host_failures(pool, domain: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(_SQL_RESET_HOST_FAILURES, domain)
