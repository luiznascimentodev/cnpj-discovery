"""Fila persistente domain-first com resume real.

Mesma semântica do crawler/queue.py, mas com escopo de domínio:
- Um job por (domain, url, crawl_profile) — muitos CNPJs compartilham o mesmo job.
- `FOR UPDATE SKIP LOCKED` garante que múltiplos workers não processem o mesmo job.
- Leases mortos são liberados por `release_stale_domain_jobs`.
- Enqueue é idempotente: conflito na unique key atualiza prioridade se maior.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

DEFAULT_LEASE_SECONDS = 600
DEFAULT_CLAIM_BATCH = 20
DEFAULT_RETRY_BASE_SECONDS = 60
DEFAULT_RETRY_MAX_SECONDS = 3600

TERMINAL_DOMAIN_JOB_STATUSES = frozenset({"error", "blocked", "skipped"})

# High-yield canonical paths enqueued for each verified domain
CANONICAL_PATHS = [
    "/",
    "/contato",
    "/contact",
    "/sobre",
    "/about",
    "/empresa",
    "/institucional",
    "/atendimento",
]

_SQL_CLAIM_DOMAIN_JOBS = """
    WITH due AS (
        SELECT id
        FROM paid_enrichment.domain_crawl_jobs
        WHERE status IN ('pending', 'retry')
          AND next_run_at <= now()
          AND (locked_at IS NULL OR locked_at < now() - make_interval(secs => $2::int))
          AND ($4::text IS NULL OR crawl_profile = $4::text)
        ORDER BY priority DESC, next_run_at, id
        LIMIT $1::int
        FOR UPDATE SKIP LOCKED
    )
    UPDATE paid_enrichment.domain_crawl_jobs job
    SET status     = 'running',
        locked_at  = now(),
        locked_by  = $3,
        attempts   = job.attempts + 1,
        updated_at = now()
    FROM due
    WHERE job.id = due.id
    RETURNING job.id, job.domain, job.url, job.crawl_profile, job.source,
              job.priority, job.depth, job.attempts
"""

_SQL_COMPLETE_DOMAIN_JOB = """
    UPDATE paid_enrichment.domain_crawl_jobs
    SET status           = 'done',
        last_content_hash = $2,
        last_http_status  = $3,
        locked_at        = NULL,
        locked_by        = NULL,
        updated_at       = now()
    WHERE id = $1
"""

_SQL_RETRY_DOMAIN_JOB = """
    UPDATE paid_enrichment.domain_crawl_jobs
    SET status       = 'retry',
        next_run_at  = now() + make_interval(secs => $2::int),
        last_error   = $3,
        last_http_status = $4,
        locked_at    = NULL,
        locked_by    = NULL,
        updated_at   = now()
    WHERE id = $1
"""

_SQL_TERMINAL_DOMAIN_JOB = """
    UPDATE paid_enrichment.domain_crawl_jobs
    SET status       = $2,
        last_error   = $3,
        last_http_status = $4,
        locked_at    = NULL,
        locked_by    = NULL,
        updated_at   = now()
    WHERE id = $1
"""

_SQL_RELEASE_STALE_DOMAIN_JOBS = """
    UPDATE paid_enrichment.domain_crawl_jobs
    SET status     = 'pending',
        locked_at  = NULL,
        locked_by  = NULL,
        updated_at = now()
    WHERE status = 'running'
      AND locked_at < now() - make_interval(secs => $1::int)
    RETURNING id
"""

_SQL_ENQUEUE_DOMAIN_JOBS = """
    INSERT INTO paid_enrichment.domain_crawl_jobs
        (domain, url, crawl_profile, source, priority, status)
    VALUES ($1, $2, $3, $4, $5, 'pending')
    ON CONFLICT (domain, url, crawl_profile) DO UPDATE
        SET priority   = GREATEST(
                paid_enrichment.domain_crawl_jobs.priority,
                EXCLUDED.priority
            ),
            status     = CASE
                WHEN paid_enrichment.domain_crawl_jobs.status IN ('done', 'error', 'blocked', 'skipped')
                     AND EXCLUDED.priority > paid_enrichment.domain_crawl_jobs.priority
                THEN 'pending'
                ELSE paid_enrichment.domain_crawl_jobs.status
            END,
            updated_at = now()
    RETURNING id, (xmax = 0) AS inserted
"""

_SQL_ENQUEUE_FROM_VERIFIED_DOMAINS = """
    SELECT id, domain, homepage_url
    FROM paid_enrichment.company_domains
    WHERE status = 'verified'
      AND id > $1
    ORDER BY id
    LIMIT $2
"""

# Verified domains with zero static contact candidates AND no active playwright jobs —
# these are candidates for browser fallback.
_SQL_DOMAINS_FOR_PLAYWRIGHT = """
    SELECT DISTINCT cd.domain, cd.homepage_url
    FROM paid_enrichment.company_domains cd
    WHERE cd.status = 'verified'
      AND NOT EXISTS (
          SELECT 1 FROM paid_enrichment.domain_contact_candidates dcc
          WHERE dcc.domain = cd.domain
      )
      AND NOT EXISTS (
          SELECT 1 FROM paid_enrichment.domain_crawl_jobs dcj
          WHERE dcj.domain = cd.domain
            AND dcj.crawl_profile = 'playwright_contact_probe'
            AND dcj.status NOT IN ('error', 'blocked', 'skipped')
      )
    ORDER BY cd.domain
    LIMIT $1
"""

PLAYWRIGHT_PROBE_PATHS = ["/", "/contato", "/contact"]
PLAYWRIGHT_PROFILE = "playwright_contact_probe"


@dataclass(frozen=True)
class ClaimedDomainJob:
    id: int
    domain: str
    url: str
    crawl_profile: str
    source: str
    priority: int
    depth: int
    attempts: int


def jittered_backoff(attempts: int, base: int = DEFAULT_RETRY_BASE_SECONDS) -> int:
    """Exponential backoff with ±20% jitter, capped at DEFAULT_RETRY_MAX_SECONDS."""
    raw = base * (2 ** max(attempts - 1, 0))
    jittered = raw * random.uniform(0.8, 1.2)
    return int(min(jittered, DEFAULT_RETRY_MAX_SECONDS))


async def claim_domain_crawl_jobs(
    pool,
    *,
    worker_id: str,
    batch_size: int = DEFAULT_CLAIM_BATCH,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    crawl_profile: Optional[str] = None,
) -> list[ClaimedDomainJob]:
    if not worker_id:
        raise ValueError("worker_id is required")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            _SQL_CLAIM_DOMAIN_JOBS,
            batch_size,
            lease_seconds,
            worker_id,
            crawl_profile,
        )
    return [
        ClaimedDomainJob(
            id=row["id"],
            domain=row["domain"],
            url=row["url"],
            crawl_profile=row["crawl_profile"],
            source=row["source"],
            priority=row["priority"],
            depth=row["depth"],
            attempts=row["attempts"],
        )
        for row in rows
    ]


async def complete_domain_crawl_job(
    pool,
    job_id: int,
    *,
    content_hash: str,
    http_status: int,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            _SQL_COMPLETE_DOMAIN_JOB, job_id, content_hash, http_status
        )


async def retry_domain_crawl_job(
    pool,
    job_id: int,
    *,
    retry_in_seconds: int,
    last_error: str,
    http_status: Optional[int] = None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            _SQL_RETRY_DOMAIN_JOB,
            job_id,
            max(retry_in_seconds, 0),
            last_error,
            http_status,
        )


async def terminal_domain_crawl_job(
    pool,
    job_id: int,
    *,
    status: str,
    last_error: str | None = None,
    http_status: Optional[int] = None,
) -> None:
    if status not in TERMINAL_DOMAIN_JOB_STATUSES:
        raise ValueError(f"Invalid terminal status: {status!r}")
    async with pool.acquire() as conn:
        await conn.execute(
            _SQL_TERMINAL_DOMAIN_JOB, job_id, status, last_error, http_status
        )


async def release_stale_domain_jobs(
    pool,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> int:
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL_RELEASE_STALE_DOMAIN_JOBS, lease_seconds)
    return len(rows)


async def enqueue_domain_jobs_for_domain(
    pool,
    *,
    domain: str,
    homepage_url: str | None,
    source: str,
    priority: int,
    crawl_profile: str = "static_http",
    paths: list[str] | None = None,
) -> int:
    """Enqueue canonical paths for a verified domain. Returns count inserted."""
    if paths is None:
        paths = CANONICAL_PATHS
    base = homepage_url or f"https://{domain}"
    base = base.rstrip("/")
    inserted = 0
    async with pool.acquire() as conn:
        for path in paths:
            url = base + path if path != "/" else base + "/"
            row = await conn.fetchrow(
                _SQL_ENQUEUE_DOMAIN_JOBS,
                domain,
                url,
                crawl_profile,
                source,
                priority,
            )
            if row and row["inserted"]:
                inserted += 1
    return inserted


async def enqueue_playwright_jobs_for_zero_contact_domains(
    pool,
    *,
    source: str = "playwright_fallback",
    priority: int = 30,
    batch_size: int = 200,
) -> tuple[int, int]:
    """Enqueue playwright probe jobs for verified domains with zero static contacts.

    Returns (domains_seen, jobs_inserted). Low priority (default 30) keeps playwright
    well below static HTTP jobs (default 50).
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL_DOMAINS_FOR_PLAYWRIGHT, batch_size)
    domains_seen = 0
    jobs_inserted = 0
    for row in rows:
        domains_seen += 1
        count = await enqueue_domain_jobs_for_domain(
            pool,
            domain=row["domain"],
            homepage_url=row["homepage_url"],
            source=source,
            priority=priority,
            crawl_profile=PLAYWRIGHT_PROFILE,
            paths=PLAYWRIGHT_PROBE_PATHS,
        )
        jobs_inserted += count
    return domains_seen, jobs_inserted


async def enqueue_jobs_from_verified_domains(
    pool,
    *,
    source: str = "verified_domain",
    priority: int = 50,
    crawl_profile: str = "static_http",
    batch_size: int = 1000,
    cursor_id: int = 0,
) -> tuple[int, int]:
    """Iterate verified company_domains and enqueue jobs. Returns (domains_seen, jobs_inserted)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            _SQL_ENQUEUE_FROM_VERIFIED_DOMAINS, cursor_id, batch_size
        )
    domains_seen = 0
    jobs_inserted = 0
    for row in rows:
        domains_seen += 1
        count = await enqueue_domain_jobs_for_domain(
            pool,
            domain=row["domain"],
            homepage_url=row["homepage_url"],
            source=source,
            priority=priority,
            crawl_profile=crawl_profile,
        )
        jobs_inserted += count
    return domains_seen, jobs_inserted
