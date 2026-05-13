"""Crawler runner que orquestra fila → fetch → publicação.

Política de resume: tudo flui através das primitivas do crawler/queue,
que usam `FOR UPDATE SKIP LOCKED` e *lease* via `updated_at`. Worker que
trava libera leases automaticamente quando o lease expira; reexecuções
nunca recomeçam do zero.

Backoff: 60s · 2^(attempts-1), com teto de 1h.
"""
import re as _re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib

import httpx
from loguru import logger

from crawler.queue import (
    ClaimedCrawlRequest,
    claim_crawl_requests,
    get_host_state,
    mark_request_done,
    mark_request_retry,
    mark_request_terminal,
    reset_host_failures,
    update_host_failures,
)
from crawler.robots import RobotsRules, fetch_robots, persist_host_robots
from extraction import extract_contacts_from_html
from resolution import resolve_contacts
from resolver.publisher import publish_resolved_contacts
from rf_baseline import (
    normalize_rf_email,
    normalize_rf_phone,
    public_normalized_values,
)

DEFAULT_USER_AGENT = "CNPJDiscoveryBot/1.0 (+https://cnpj-discovery.example/crawler)"
RETRY_BASE_SECONDS = 60
RETRY_MAX_SECONDS = 3600
MAX_ATTEMPTS = 4
BLOCK_AFTER_FAILURES = 5
HOST_BLOCK_DURATION = timedelta(hours=2)
BLOCKED_HTTP_STATUSES = frozenset({401, 403})
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

_SQL_FETCH_RF_FOR_RUNNER = """
    SELECT est.email, est.ddd1, est.telefone1, est.ddd2, est.telefone2
    FROM estabelecimentos est
    WHERE est.cnpj_basico = $1 AND est.cnpj_ordem = $2 AND est.cnpj_dv = $3
"""

_SQL_INSERT_CRAWL_PAGE = """
    INSERT INTO paid_enrichment.crawl_pages (
        crawl_request_id, url, domain, http_status, content_type, content_hash,
        title, fetched_at, html_excerpt
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, now(), $8)
    ON CONFLICT (url, content_hash) DO UPDATE SET fetched_at = now()
    RETURNING id
"""

_SQL_FETCH_TRUSTED_DOMAINS = """
    SELECT domain
    FROM paid_enrichment.company_domains
    WHERE cnpj_basico = $1 AND cnpj_ordem = $2 AND cnpj_dv = $3
      AND status = 'verified'
"""

_SQL_ENQUEUE_PLAYWRIGHT = """
    INSERT INTO paid_enrichment.domain_crawl_jobs
        (domain, url, crawl_profile, source, priority, status)
    VALUES ($1, $2, 'playwright_contact_probe', 'js_heavy_auto', 60, 'pending')
    ON CONFLICT (domain, url, crawl_profile) DO UPDATE
        SET priority = GREATEST(domain_crawl_jobs.priority, EXCLUDED.priority),
            updated_at = now()
"""

_SCRIPT_TAG_RE = _re.compile(r"<script[\s>]", _re.IGNORECASE)
_JS_HEAVY_THRESHOLD = 10


def _count_script_tags(html: str) -> int:
    return len(_SCRIPT_TAG_RE.findall(html))


def _is_js_heavy(html: str) -> bool:
    return _count_script_tags(html) > _JS_HEAVY_THRESHOLD


async def _enqueue_playwright_if_needed(conn, domain: str) -> None:
    await conn.execute(_SQL_ENQUEUE_PLAYWRIGHT, domain, f"https://{domain}/")


@dataclass(frozen=True)
class RunStats:
    requests_claimed: int = 0
    pages_fetched: int = 0
    contacts_published: int = 0
    requests_done: int = 0
    requests_retried: int = 0
    requests_blocked: int = 0
    requests_errored: int = 0


def retry_delay(attempts: int) -> int:
    delay = RETRY_BASE_SECONDS * (2 ** max(attempts - 1, 0))
    return min(delay, RETRY_MAX_SECONDS)


def hash_body(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()


def extract_title(body: str) -> str | None:
    body_lower = body.lower()
    open_idx = body_lower.find("<title>")
    if open_idx == -1:
        return None
    close_idx = body_lower.find("</title>", open_idx + 7)
    if close_idx == -1:
        return None
    return body[open_idx + 7 : close_idx].strip()[:500] or None


def clean_postgres_text(value: str) -> str:
    return value.replace("\x00", "")


async def _trusted_domains(conn, cnpj_basico, cnpj_ordem, cnpj_dv) -> set[str]:
    rows = await conn.fetch(
        _SQL_FETCH_TRUSTED_DOMAINS, cnpj_basico, cnpj_ordem, cnpj_dv
    )
    return {row["domain"] for row in rows}


async def _baseline_blacklist(conn, cnpj_basico, cnpj_ordem, cnpj_dv) -> set[str]:
    row = await conn.fetchrow(
        _SQL_FETCH_RF_FOR_RUNNER, cnpj_basico, cnpj_ordem, cnpj_dv
    )
    if not row:
        return set()
    rf_email = normalize_rf_email(row["email"])
    rf_phone1 = normalize_rf_phone(row["ddd1"], row["telefone1"])
    rf_phone2 = normalize_rf_phone(row["ddd2"], row["telefone2"])
    return public_normalized_values(rf_email, rf_phone1, rf_phone2)


async def _persist_success(
    pool,
    request: ClaimedCrawlRequest,
    *,
    response: httpx.Response,
    body: str,
    content_hash: str,
) -> int:
    """Insert crawl_pages, run extraction+resolution+publisher in a transaction."""
    clean_body = clean_postgres_text(body)
    title = extract_title(clean_body)
    excerpt = clean_body[:2000]
    async with pool.acquire() as conn:
        async with conn.transaction():
            page_id = await conn.fetchval(
                _SQL_INSERT_CRAWL_PAGE,
                request.id,
                request.url,
                request.domain,
                response.status_code,
                response.headers.get("content-type", ""),
                content_hash,
                title,
                excerpt,
            )

            trusted = await _trusted_domains(
                conn, request.cnpj_basico, request.cnpj_ordem, request.cnpj_dv
            )
            blacklist = await _baseline_blacklist(
                conn, request.cnpj_basico, request.cnpj_ordem, request.cnpj_dv
            )
            extracted = extract_contacts_from_html(clean_body, source_url=request.url)
            resolved = resolve_contacts(
                extracted,
                verified_domains=trusted,
                public_normalized_values=blacklist,
            )
            stats = await publish_resolved_contacts(
                conn,
                cnpj_basico=request.cnpj_basico,
                cnpj_ordem=request.cnpj_ordem,
                cnpj_dv=request.cnpj_dv,
                crawl_page_id=page_id,
                contacts=resolved,
            )
            if _is_js_heavy(clean_body) and len(resolved) < 2:
                await _enqueue_playwright_if_needed(conn, request.domain)
            return stats.contacts_published


async def _handle_failure(
    pool,
    request: ClaimedCrawlRequest,
    *,
    error: str,
) -> None:
    host_state = await get_host_state(pool, request.domain)
    failures = (host_state.consecutive_failures if host_state else 0) + 1
    blocked_until = None
    if failures >= BLOCK_AFTER_FAILURES:
        blocked_until = datetime.now(timezone.utc) + HOST_BLOCK_DURATION
    await update_host_failures(
        pool,
        request.domain,
        consecutive_failures=failures,
        blocked_until=blocked_until,
        last_fetch_at=datetime.now(timezone.utc),
    )
    if request.attempts >= MAX_ATTEMPTS:
        logger.error(
            "crawler_request_failed_terminal id={} domain={} url={} attempts={} error={} host_failures={} blocked_until={}",
            request.id,
            request.domain,
            request.url,
            request.attempts,
            error,
            failures,
            blocked_until,
        )
        await mark_request_terminal(
            pool, request.id, status="error", last_error=error
        )
        return
    retry_in_seconds = retry_delay(request.attempts)
    logger.warning(
        "crawler_request_retry id={} domain={} url={} attempts={} retry_in_seconds={} error={} host_failures={} blocked_until={}",
        request.id,
        request.domain,
        request.url,
        request.attempts,
        retry_in_seconds,
        error,
        failures,
        blocked_until,
    )
    await mark_request_retry(
        pool,
        request.id,
        retry_in_seconds=retry_in_seconds,
        last_error=error,
    )


async def process_request(
    pool,
    request: ClaimedCrawlRequest,
    *,
    client: httpx.AsyncClient,
    user_agent: str,
    robots_cache: dict[str, RobotsRules],
) -> tuple[str, int]:
    """Returns (outcome, contacts_published) where outcome is one of
    'blocked', 'retried', 'errored', 'done'."""
    domain = request.domain
    logger.info(
        "crawler_request_start id={} domain={} url={} attempt={} source={} depth={}",
        request.id,
        request.domain,
        request.url,
        request.attempts,
        request.source,
        request.depth,
    )

    rules = robots_cache.get(domain)
    if rules is None:
        rules = await fetch_robots(domain, client=client, user_agent=user_agent)
        robots_cache[domain] = rules
        await persist_host_robots(pool, rules)
        logger.info(
            "crawler_robots_checked domain={} status={} crawl_delay={}",
            domain,
            rules.fetched_status,
            rules.crawl_delay,
        )

    if not rules.can_fetch(request.url, user_agent):
        logger.warning(
            "crawler_request_blocked id={} domain={} url={} reason=robots_disallow",
            request.id,
            request.domain,
            request.url,
        )
        await mark_request_terminal(
            pool, request.id, status="blocked", last_error="robots_disallow"
        )
        return "blocked", 0

    host_state = await get_host_state(pool, domain)
    now = datetime.now(timezone.utc)
    if host_state and host_state.blocked_until and host_state.blocked_until > now:
        delay = max(int((host_state.blocked_until - now).total_seconds()), 1)
        logger.warning(
            "crawler_request_requeued id={} domain={} url={} reason=host_blocked retry_in_seconds={} blocked_until={}",
            request.id,
            request.domain,
            request.url,
            delay,
            host_state.blocked_until,
        )
        await mark_request_retry(
            pool, request.id, retry_in_seconds=delay, last_error="host_blocked"
        )
        return "retried", 0

    try:
        response = await client.get(request.url, follow_redirects=True)
    except httpx.HTTPError as exc:
        await _handle_failure(pool, request, error=f"{type(exc).__name__}: {exc}")
        outcome = "retried" if request.attempts < MAX_ATTEMPTS else "errored"
        return outcome, 0

    status_code = response.status_code
    if status_code in BLOCKED_HTTP_STATUSES:
        logger.warning(
            "crawler_request_blocked id={} domain={} url={} reason=http_{}",
            request.id,
            request.domain,
            request.url,
            status_code,
        )
        await mark_request_terminal(
            pool, request.id, status="blocked", last_error=f"http_{status_code}"
        )
        return "blocked", 0

    if status_code in RETRYABLE_HTTP_STATUSES or status_code >= 500:
        await _handle_failure(pool, request, error=f"http_{status_code}")
        outcome = "retried" if request.attempts < MAX_ATTEMPTS else "errored"
        return outcome, 0

    if status_code >= 400:
        logger.error(
            "crawler_request_error id={} domain={} url={} status_code={}",
            request.id,
            request.domain,
            request.url,
            status_code,
        )
        await mark_request_terminal(
            pool, request.id, status="error", last_error=f"http_{status_code}"
        )
        return "errored", 0

    body = response.text
    content_hash = hash_body(body)
    contacts_published = await _persist_success(
        pool, request, response=response, body=body, content_hash=content_hash
    )
    await mark_request_done(pool, request.id, content_hash)
    await reset_host_failures(pool, request.domain)
    logger.info(
        "crawler_request_done id={} domain={} url={} status_code={} bytes={} content_hash={} contacts_published={}",
        request.id,
        request.domain,
        request.url,
        status_code,
        len(response.content),
        content_hash[:12],
        contacts_published,
    )
    return "done", contacts_published


async def run_batch(
    pool,
    *,
    client: httpx.AsyncClient,
    worker_id: str,
    batch_size: int = 20,
    lease_seconds: int = 600,
    user_agent: str = DEFAULT_USER_AGENT,
) -> RunStats:
    requests = await claim_crawl_requests(
        pool,
        worker_id=worker_id,
        batch_size=batch_size,
        lease_seconds=lease_seconds,
    )
    if not requests:
        logger.info("crawler_batch_empty worker={} batch_size={}", worker_id, batch_size)
        return RunStats(requests_claimed=0)

    logger.info(
        "crawler_batch_start worker={} claimed={} lease_seconds={}",
        worker_id,
        len(requests),
        lease_seconds,
    )
    robots_cache: dict[str, RobotsRules] = {}
    counters: dict[str, int] = {
        "done": 0,
        "blocked": 0,
        "retried": 0,
        "errored": 0,
    }
    contacts_published = 0

    for request in requests:
        outcome, contacts = await process_request(
            pool,
            request,
            client=client,
            user_agent=user_agent,
            robots_cache=robots_cache,
        )
        counters[outcome] += 1
        contacts_published += contacts

    stats = RunStats(
        requests_claimed=len(requests),
        pages_fetched=counters["done"],
        contacts_published=contacts_published,
        requests_done=counters["done"],
        requests_retried=counters["retried"],
        requests_blocked=counters["blocked"],
        requests_errored=counters["errored"],
    )
    logger.info(
        "crawler_batch_done worker={} claimed={} done={} retried={} blocked={} errored={} contacts_published={}",
        worker_id,
        stats.requests_claimed,
        stats.requests_done,
        stats.requests_retried,
        stats.requests_blocked,
        stats.requests_errored,
        stats.contacts_published,
    )
    return stats
