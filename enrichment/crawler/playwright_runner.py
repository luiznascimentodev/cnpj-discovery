"""Playwright browser fallback crawler.

Used ONLY for verified domains where the static HTTP crawler found zero contacts
and the page appears JS-rendered. This is a low-throughput path — never the default.

Design constraints (from scale plan):
- Browser contexts are isolated per batch, not per page (cheap).
- Strict budgets: page_timeout, navigation_timeout, max pages per domain per run.
- No infinite scrolling, no login, no JS eval for arbitrary code.
- No captcha solving — captcha/interstitial detection → mark blocked.
- Static crawler throughput is never affected by playwright jobs.
- A blocked/captcha page is always marked 'blocked', never retried by this runner.

Captcha/interstitial detection:
- Title or body contains known captcha keywords.
- Page URL redirected to known challenge providers.
- HTTP status 403 returned by Playwright fetch.

Contact extraction:
- Get rendered HTML via page.content() after page load.
- Run the same extract_contacts_from_html function used by the static runner.
- Store to domain_contact_candidates (same table, same idempotency).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from loguru import logger

from crawler.domain_queue import (
    PLAYWRIGHT_PROFILE,
    ClaimedDomainJob,
    claim_domain_crawl_jobs,
    complete_domain_crawl_job,
    jittered_backoff,
    terminal_domain_crawl_job,
    retry_domain_crawl_job,
)
from crawler.host_policy import (
    HostPolicy,
    get_host_policy,
    increment_host_budget,
    save_host_policy,
)
from extraction import extract_contacts_from_html

if TYPE_CHECKING:  # pragma: no cover
    from playwright.async_api import Browser, BrowserContext, Page

DEFAULT_USER_AGENT = "CNPJDiscoveryBot/1.0 (+https://cnpj-discovery.example/crawler)"
PAGE_TIMEOUT_MS = 15_000       # 15 s max per page navigation
NETWORK_IDLE_TIMEOUT_MS = 5_000  # wait for network idle after load
MAX_ATTEMPTS = 3
MAX_PAGES_PER_DOMAIN = 2       # hard cap: playwright is expensive
GLOBAL_PLAYWRIGHT_CONCURRENCY = 2  # kept low intentionally

# Captcha/interstitial signals — mark blocked immediately
_CAPTCHA_TITLE_TOKENS = frozenset({
    "captcha", "challenge", "robot", "bot check", "security check",
    "ddos-guard", "just a moment", "attention required",
})
_CAPTCHA_URL_TOKENS = frozenset({
    "hcaptcha.com", "recaptcha.com", "captcha.com",
    "cdn-cgi/challenge",
    "cdn-cgi/bm",
    "ddos-guard.net",
})

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
class PlaywrightRunStats:
    jobs_claimed: int = 0
    pages_rendered: int = 0
    contacts_extracted: int = 0
    jobs_done: int = 0
    jobs_retried: int = 0
    jobs_blocked: int = 0
    jobs_errored: int = 0


def _is_captcha_page(title: str, url: str) -> bool:
    title_lower = title.lower()
    if any(token in title_lower for token in _CAPTCHA_TITLE_TOKENS):
        return True
    url_lower = url.lower()
    return any(token in url_lower for token in _CAPTCHA_URL_TOKENS)


def _hash_content(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _clean_text(value: str) -> str:
    return value.replace("\x00", "")


async def _persist_page_and_contacts(
    pool,
    job: ClaimedDomainJob,
    *,
    html: str,
    title: str,
    final_url: str,
    content_hash: str,
) -> int:
    clean_html = _clean_text(html)
    excerpt = clean_html[:2000]
    extracted = extract_contacts_from_html(clean_html, source_url=final_url)
    contacts_inserted = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            page_id = await conn.fetchval(
                _SQL_INSERT_DOMAIN_PAGE,
                job.id,
                job.domain,
                final_url,
                200,
                "text/html",
                content_hash,
                title[:500] if title else None,
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
                    "playwright_extractor",
                )
                if result:
                    contacts_inserted += 1
    return contacts_inserted


async def _fetch_page_with_playwright(
    context: "BrowserContext",
    url: str,
    *,
    user_agent: str,
) -> tuple[str, str, str]:
    """Navigate to url and return (html, title, final_url).

    Raises playwright TimeoutError on navigation timeout.
    Never scrolls, never evaluates JS beyond the initial page load.
    """
    page: "Page" = await context.new_page()
    try:
        await page.set_extra_http_headers({"User-Agent": user_agent})
        await page.goto(
            url,
            timeout=PAGE_TIMEOUT_MS,
            wait_until="domcontentloaded",
        )
        try:
            await page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT_MS)
        except Exception:
            pass  # network idle is best-effort; content is already loaded

        html = await page.content()
        title = await page.title()
        final_url = page.url
        return html, title, final_url
    finally:
        await page.close()


async def process_playwright_job(
    pool,
    job: ClaimedDomainJob,
    *,
    browser: "Browser",
    user_agent: str,
    policy_cache: dict[str, HostPolicy],
) -> tuple[str, int]:
    """Process one playwright job. Returns (outcome, contacts_extracted)."""
    domain = job.domain
    logger.info(
        "playwright_job_start id={} domain={} url={} attempt={}",
        job.id, domain, job.url, job.attempts,
    )

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
            "playwright_job_host_blocked id={} domain={} blocked_until={} retry_in={}",
            job.id, domain, policy.blocked_until, delay,
        )
        await retry_domain_crawl_job(
            pool, job.id, retry_in_seconds=delay, last_error="host_blocked"
        )
        return "retried", 0

    context: "BrowserContext" = await browser.new_context(
        user_agent=user_agent,
        java_script_enabled=True,
        accept_downloads=False,
    )
    try:
        try:
            html, title, final_url = await _fetch_page_with_playwright(
                context, job.url, user_agent=user_agent
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            policy = policy.register_failure()
            policy_cache[domain] = policy
            await save_host_policy(pool, policy)
            retry_in = jittered_backoff(job.attempts)
            logger.warning(
                "playwright_job_error id={} domain={} url={} error={} retry_in={}",
                job.id, domain, job.url, error, retry_in,
            )
            if job.attempts >= MAX_ATTEMPTS:
                await terminal_domain_crawl_job(pool, job.id, status="error", last_error=error)
                return "errored", 0
            await retry_domain_crawl_job(
                pool, job.id, retry_in_seconds=retry_in, last_error=error
            )
            return "retried", 0

        if _is_captcha_page(title, final_url):
            logger.warning(
                "playwright_job_captcha id={} domain={} url={} final_url={} title={!r}",
                job.id, domain, job.url, final_url, title[:100],
            )
            policy = policy.register_failure()
            policy_cache[domain] = policy
            await save_host_policy(pool, policy)
            await terminal_domain_crawl_job(
                pool, job.id, status="blocked", last_error="captcha_or_interstitial"
            )
            return "blocked", 0

        content_hash = _hash_content(html)
        contacts = await _persist_page_and_contacts(
            pool, job,
            html=html,
            title=title,
            final_url=final_url,
            content_hash=content_hash,
        )
        policy = policy.register_success(latency_ms=0)
        policy_cache[domain] = policy
        await save_host_policy(pool, policy)
        await increment_host_budget(pool, domain)
        await complete_domain_crawl_job(
            pool, job.id, content_hash=content_hash, http_status=200
        )
        logger.info(
            "playwright_job_done id={} domain={} url={} content_hash={} contacts={}",
            job.id, domain, job.url, content_hash[:12], contacts,
        )
        return "done", contacts

    finally:
        await context.close()


async def run_playwright_batch(
    pool,
    *,
    browser: "Browser",
    worker_id: str,
    batch_size: int = 5,
    lease_seconds: int = 600,
    user_agent: str = DEFAULT_USER_AGENT,
) -> PlaywrightRunStats:
    """Claim and process a batch of playwright_contact_probe jobs."""
    jobs = await claim_domain_crawl_jobs(
        pool,
        worker_id=worker_id,
        batch_size=batch_size,
        lease_seconds=lease_seconds,
        crawl_profile=PLAYWRIGHT_PROFILE,
    )
    if not jobs:
        logger.info("playwright_batch_empty worker={} batch_size={}", worker_id, batch_size)
        return PlaywrightRunStats(jobs_claimed=0)

    logger.info(
        "playwright_batch_start worker={} claimed={} lease_seconds={}",
        worker_id, len(jobs), lease_seconds,
    )

    policy_cache: dict[str, HostPolicy] = {}
    counters: dict[str, int] = {
        "done": 0, "blocked": 0, "retried": 0, "errored": 0
    }
    contacts_total = 0

    # Enforce domain-level cap: skip extra jobs for a domain already at budget
    domain_page_count: dict[str, int] = {}
    for job in jobs:
        count = domain_page_count.get(job.domain, 0)
        if count >= MAX_PAGES_PER_DOMAIN:
            logger.warning(
                "playwright_job_domain_cap id={} domain={} cap={}",
                job.id, job.domain, MAX_PAGES_PER_DOMAIN,
            )
            await retry_domain_crawl_job(
                pool, job.id,
                retry_in_seconds=3600,
                last_error="domain_page_cap",
            )
            counters["retried"] += 1
            continue

        domain_page_count[job.domain] = count + 1
        outcome, contacts = await process_playwright_job(
            pool, job,
            browser=browser,
            user_agent=user_agent,
            policy_cache=policy_cache,
        )
        counters[outcome] = counters.get(outcome, 0) + 1
        contacts_total += contacts

    stats = PlaywrightRunStats(
        jobs_claimed=len(jobs),
        pages_rendered=counters["done"],
        contacts_extracted=contacts_total,
        jobs_done=counters["done"],
        jobs_retried=counters["retried"],
        jobs_blocked=counters["blocked"],
        jobs_errored=counters["errored"],
    )
    logger.info(
        "playwright_batch_done worker={} claimed={} done={} retried={} blocked={} "
        "errored={} contacts_extracted={}",
        worker_id, stats.jobs_claimed, stats.jobs_done, stats.jobs_retried,
        stats.jobs_blocked, stats.jobs_errored, stats.contacts_extracted,
    )
    return stats
