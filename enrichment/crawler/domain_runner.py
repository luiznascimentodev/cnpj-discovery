"""Domain-first crawler runner.

Fetches jobs from `domain_crawl_jobs`, persists pages to `domain_pages`,
extracts contacts to `domain_contact_candidates`. Does NOT publish directly —
publication is done by the resolver (Phase 5).

Resume semantics:
- Each domain_crawl_jobs row is a checkpoint (status/locked_at/next_run_at).
- domain_pages has UNIQUE(domain, url, content_hash) so re-fetching unchanged
  pages is a no-op at the DB level.
- domain_contact_candidates has UNIQUE(domain, contact_type, normalized_value,
  domain_page_id) so re-running extraction is idempotent.

Backpressure:
- Uses host_policy for circuit breaker, budget, and adaptive delay.
- Never decreases delay after non-200 responses.
- Respects Retry-After header.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx
from loguru import logger

from crawler.domain_queue import (
    ClaimedDomainJob,
    claim_domain_crawl_jobs,
    complete_domain_crawl_job,
    jittered_backoff,
    release_stale_domain_jobs,
    retry_domain_crawl_job,
    terminal_domain_crawl_job,
)
from crawler.host_policy import (
    HostPolicy,
    get_host_policy,
    increment_host_budget,
    jittered_retry_delay,
    save_host_policy,
)
from crawler.robots import RobotsRules, fetch_robots, persist_host_robots
from extraction import extract_contacts_from_html

DEFAULT_USER_AGENT = "CNPJDiscoveryBot/1.0 (+https://cnpj-discovery.example/crawler)"
MAX_ATTEMPTS = 4
BLOCKED_HTTP_STATUSES = frozenset({401, 403})
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

_SQL_INSERT_DOMAIN_PAGE = """
    INSERT INTO paid_enrichment.domain_pages (
        domain_crawl_job_id, domain, url, http_status, content_type,
        content_hash, title, html_excerpt, fetched_at
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())
    ON CONFLICT (domain, url, content_hash) DO UPDATE
        SET fetched_at = now()
    RETURNING id
"""

_SQL_INSERT_DOMAIN_CONTACT = """
    INSERT INTO paid_enrichment.domain_contact_candidates (
        domain_page_id, domain, contact_type, raw_value, normalized_value,
        label, context, confidence, extractor
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    ON CONFLICT (domain, contact_type, normalized_value, domain_page_id) DO NOTHING
    RETURNING id
"""


@dataclass(frozen=True)
class DomainRunStats:
    jobs_claimed: int = 0
    pages_fetched: int = 0
    contacts_extracted: int = 0
    jobs_done: int = 0
    jobs_retried: int = 0
    jobs_blocked: int = 0
    jobs_errored: int = 0
    budget_skipped: int = 0


def _hash_body(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()


def _extract_title(body: str) -> Optional[str]:
    body_lower = body.lower()
    open_idx = body_lower.find("<title>")
    if open_idx == -1:
        return None
    close_idx = body_lower.find("</title>", open_idx + 7)
    if close_idx == -1:
        return None
    return body[open_idx + 7 : close_idx].strip()[:500] or None


def _clean_text(value: str) -> str:
    return value.replace("\x00", "")


def _parse_retry_after(headers: httpx.Headers) -> Optional[int]:
    raw = headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(int(raw), 0)
    except ValueError:
        return None


async def _persist_page_and_contacts(
    pool,
    job: ClaimedDomainJob,
    *,
    http_status: int,
    content_type: str,
    body: str,
    content_hash: str,
) -> int:
    clean_body = _clean_text(body)
    title = _extract_title(clean_body)
    excerpt = clean_body[:2000]
    extracted = extract_contacts_from_html(clean_body, source_url=job.url)
    contacts_inserted = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            page_id = await conn.fetchval(
                _SQL_INSERT_DOMAIN_PAGE,
                job.id,
                job.domain,
                job.url,
                http_status,
                content_type,
                content_hash,
                title,
                excerpt,
            )
            for contact in extracted:
                result = await conn.fetchrow(
                    _SQL_INSERT_DOMAIN_CONTACT,
                    page_id,
                    job.domain,
                    contact.contact_type,
                    contact.value,
                    contact.normalized_value,
                    contact.label,
                    contact.context,
                    contact.confidence,
                    "html_extractor",
                )
                if result:
                    contacts_inserted += 1
    return contacts_inserted


async def process_domain_job(
    pool,
    job: ClaimedDomainJob,
    *,
    client: httpx.AsyncClient,
    user_agent: str,
    robots_cache: dict[str, RobotsRules],
    policy_cache: dict[str, HostPolicy],
) -> tuple[str, int]:
    """Process one domain crawl job. Returns (outcome, contacts_extracted)."""
    domain = job.domain
    logger.info(
        "domain_job_start id={} domain={} url={} attempt={} profile={}",
        job.id, domain, job.url, job.attempts, job.crawl_profile,
    )

    # Load host policy (cached per batch)
    policy = policy_cache.get(domain)
    if policy is None:
        policy = await get_host_policy(pool, domain)
        policy_cache[domain] = policy

    if policy.is_blocked():
        now = datetime.now(timezone.utc)
        delay = 60
        if policy.blocked_until and policy.blocked_until > now:
            delay = max(int((policy.blocked_until - now).total_seconds()), 1)
        logger.warning(
            "domain_job_host_blocked id={} domain={} blocked_until={} retry_in={}",
            job.id, domain, policy.blocked_until, delay,
        )
        await retry_domain_crawl_job(
            pool, job.id, retry_in_seconds=delay, last_error="host_blocked"
        )
        return "retried", 0

    if policy.budget_exhausted:
        logger.warning(
            "domain_job_budget_exhausted id={} domain={} budget={} used={}",
            job.id, domain, policy.crawl_budget_per_day, policy.crawl_budget_used,
        )
        await retry_domain_crawl_job(
            pool, job.id, retry_in_seconds=3600, last_error="budget_exhausted"
        )
        return "budget_skipped", 0

    # Robots check
    rules = robots_cache.get(domain)
    if rules is None:
        rules = await fetch_robots(domain, client=client, user_agent=user_agent)
        robots_cache[domain] = rules
        await persist_host_robots(pool, rules)
        logger.info(
            "domain_robots_checked domain={} status={} crawl_delay={}",
            domain, rules.fetched_status, rules.crawl_delay,
        )

    if not rules.can_fetch(job.url, user_agent):
        logger.warning(
            "domain_job_blocked id={} domain={} url={} reason=robots_disallow",
            job.id, domain, job.url,
        )
        await terminal_domain_crawl_job(
            pool, job.id, status="blocked", last_error="robots_disallow"
        )
        return "blocked", 0

    # HTTP fetch
    start = datetime.now(timezone.utc)
    try:
        response = await client.get(job.url, follow_redirects=True)
    except httpx.HTTPError as exc:
        error = f"{type(exc).__name__}: {exc}"
        policy = policy.register_failure()
        policy_cache[domain] = policy
        await save_host_policy(pool, policy)
        retry_in = jittered_retry_delay(job.attempts)
        logger.warning(
            "domain_job_error id={} domain={} url={} error={} retry_in={}",
            job.id, domain, job.url, error, retry_in,
        )
        if job.attempts >= MAX_ATTEMPTS:
            await terminal_domain_crawl_job(pool, job.id, status="error", last_error=error)
            return "errored", 0
        await retry_domain_crawl_job(
            pool, job.id, retry_in_seconds=retry_in, last_error=error
        )
        return "retried", 0

    elapsed_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
    status_code = response.status_code

    if status_code in BLOCKED_HTTP_STATUSES:
        logger.warning(
            "domain_job_blocked id={} domain={} url={} reason=http_{}",
            job.id, domain, job.url, status_code,
        )
        policy = policy.register_failure(http_status=status_code)
        policy_cache[domain] = policy
        await save_host_policy(pool, policy)
        await terminal_domain_crawl_job(
            pool, job.id, status="blocked", last_error=f"http_{status_code}",
            http_status=status_code,
        )
        return "blocked", 0

    if status_code in RETRYABLE_HTTP_STATUSES or status_code >= 500:
        retry_after = _parse_retry_after(response.headers)
        policy = policy.register_failure(
            http_status=status_code, retry_after_seconds=retry_after
        )
        policy_cache[domain] = policy
        await save_host_policy(pool, policy)
        retry_in = retry_after if retry_after else jittered_retry_delay(job.attempts)
        logger.warning(
            "domain_job_retry id={} domain={} url={} status={} retry_in={} failures={}",
            job.id, domain, job.url, status_code, retry_in, policy.consecutive_failures,
        )
        if job.attempts >= MAX_ATTEMPTS:
            await terminal_domain_crawl_job(
                pool, job.id, status="error",
                last_error=f"http_{status_code}", http_status=status_code,
            )
            return "errored", 0
        await retry_domain_crawl_job(
            pool, job.id, retry_in_seconds=retry_in,
            last_error=f"http_{status_code}", http_status=status_code,
        )
        return "retried", 0

    if status_code >= 400:
        logger.error(
            "domain_job_error id={} domain={} url={} status={}",
            job.id, domain, job.url, status_code,
        )
        await terminal_domain_crawl_job(
            pool, job.id, status="error",
            last_error=f"http_{status_code}", http_status=status_code,
        )
        return "errored", 0

    # Success
    body = response.text
    content_hash = _hash_body(body)
    content_type = response.headers.get("content-type", "")

    contacts = await _persist_page_and_contacts(
        pool, job,
        http_status=status_code,
        content_type=content_type,
        body=body,
        content_hash=content_hash,
    )

    policy = policy.register_success(latency_ms=elapsed_ms)
    policy_cache[domain] = policy
    await save_host_policy(pool, policy)
    await increment_host_budget(pool, domain)
    await complete_domain_crawl_job(
        pool, job.id, content_hash=content_hash, http_status=status_code
    )

    logger.info(
        "domain_job_done id={} domain={} url={} status={} elapsed_ms={} "
        "content_hash={} contacts_extracted={}",
        job.id, domain, job.url, status_code, elapsed_ms,
        content_hash[:12], contacts,
    )
    return "done", contacts


async def run_domain_batch(
    pool,
    *,
    client: httpx.AsyncClient,
    worker_id: str,
    batch_size: int = 20,
    lease_seconds: int = 600,
    user_agent: str = DEFAULT_USER_AGENT,
) -> DomainRunStats:
    jobs = await claim_domain_crawl_jobs(
        pool,
        worker_id=worker_id,
        batch_size=batch_size,
        lease_seconds=lease_seconds,
        crawl_profile="static_http",
    )
    if not jobs:
        logger.info("domain_batch_empty worker={} batch_size={}", worker_id, batch_size)
        return DomainRunStats(jobs_claimed=0)

    logger.info(
        "domain_batch_start worker={} claimed={} lease_seconds={}",
        worker_id, len(jobs), lease_seconds,
    )

    robots_cache: dict[str, RobotsRules] = {}
    policy_cache: dict[str, HostPolicy] = {}
    counters: dict[str, int] = {
        "done": 0, "blocked": 0, "retried": 0, "errored": 0, "budget_skipped": 0
    }
    contacts_total = 0

    for job in jobs:
        outcome, contacts = await process_domain_job(
            pool, job,
            client=client,
            user_agent=user_agent,
            robots_cache=robots_cache,
            policy_cache=policy_cache,
        )
        counters[outcome] = counters.get(outcome, 0) + 1
        contacts_total += contacts

    stats = DomainRunStats(
        jobs_claimed=len(jobs),
        pages_fetched=counters["done"],
        contacts_extracted=contacts_total,
        jobs_done=counters["done"],
        jobs_retried=counters["retried"],
        jobs_blocked=counters["blocked"],
        jobs_errored=counters["errored"],
        budget_skipped=counters["budget_skipped"],
    )
    logger.info(
        "domain_batch_done worker={} claimed={} done={} retried={} blocked={} "
        "errored={} budget_skipped={} contacts_extracted={}",
        worker_id, stats.jobs_claimed, stats.jobs_done, stats.jobs_retried,
        stats.jobs_blocked, stats.jobs_errored, stats.budget_skipped,
        stats.contacts_extracted,
    )
    return stats
