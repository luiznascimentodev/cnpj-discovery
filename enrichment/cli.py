"""CLI do serviço de enriquecimento.

Comandos:
  seed-targets          — adiciona targets desde o cursor persistido (resume).
  discovery-tick        — descobre domínios para um lote de targets reclamados.
  crawler-tick          — processa lote da fila de crawl_requests (legado CNPJ-first).
  release-stale         — libera leases mortos (recovery após crash).
  worker                — loop combinando seed + discovery + crawler + release (legado).
  enqueue-domain-jobs   — enfileira jobs de domínio a partir de company_domains verificados.
  domain-crawler-tick   — processa lote da fila domain_crawl_jobs (domain-first).
  resolve-domain-tick   — resolve domain_contact_candidates -> enriched_contacts.

Resume é literal:
  - `seed-targets` continua de `paid_enrichment.enrichment_seed_cursor`.
  - `discovery-tick`/`crawler-tick` reclamam batches com `FOR UPDATE SKIP LOCKED`.
  - `domain-crawler-tick` usa `domain_crawl_jobs` com o mesmo padrão de lease.
  - `release-stale` retorna leases não confirmados à fila.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import socket
import time
from dataclasses import dataclass

from loguru import logger

from crawler.domain_queue import (
    enqueue_jobs_from_verified_domains,
    enqueue_playwright_jobs_for_zero_contact_domains,
    release_stale_domain_jobs,
)
from crawler.sitemap import discover_crawl_urls
from crawler.domain_runner import run_domain_batch
from crawler.playwright_runner import PlaywrightRunStats, run_playwright_batch
from crawler.queue import release_stale_requests
from crawler.runner import run_batch as run_crawl_batch
from database import close_pool, create_pool
from config import settings
from discovery.errors import SearchRateLimitError
from discovery.external_search import ExternalSearchClient
from heartbeat import beat as heartbeat_beat, remove as heartbeat_remove
from demand_queue import (
    claim_demand_items,
    complete_demand_item,
    count_published_contacts,
    has_pending_demand,
    release_stale_demand_items,
)

DISCOVERY_CONCURRENCY = settings.discovery_concurrency
from discovery.pipeline import process_target as discover_target
from discovery.website_probe import DEFAULT_USER_AGENT, make_default_client
from resolver.domain_resolver import resolve_domain_contacts
from scheduler import (
    claim_targets,
    complete_target,
    release_stale_locks,
    seed_active_targets,
    seed_phase1_targets,
    seed_phase2_targets,
)

DEFAULT_INTERVAL_SECONDS = 30

_PHASE1_REASON = "phase1_dns"
_PHASE2_REASON = "phase2_search"

# Per-process source backoff: source → epoch seconds when it may be used again.
# Set on SearchRateLimitError; read in _build_external_search each loop iteration.
_source_backoffs: dict[str, float] = {}


def default_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


@dataclass(frozen=True)
class TickStats:
    seeded: int = 0
    targets_claimed: int = 0
    crawl_requests_created: int = 0
    crawler_done: int = 0
    contacts_published: int = 0
    leases_released: int = 0
    demand_done: int = 0
    demand_failed: int = 0


async def do_seed(pool, *, reason: str, priority: int, batch_size: int) -> int:
    return await seed_active_targets(
        pool,
        reason=reason,
        priority=priority,
        batch_size=batch_size,
    )


async def do_seed_phase1(pool, *, batch_size: int = 50_000) -> int:
    return await seed_phase1_targets(pool, batch_size=batch_size)


async def do_seed_phase2(pool, *, batch_size: int = 10_000) -> int:
    return await seed_phase2_targets(pool, batch_size=batch_size)


async def do_discovery(
    pool,
    *,
    client,
    worker_id: str,
    batch_size: int,
    lease_seconds: int,
    concurrency: int = DISCOVERY_CONCURRENCY,
    external_search=None,
    dns_only: bool = False,
    reason: str | None = None,
) -> tuple[int, int]:
    targets = await claim_targets(
        pool,
        worker_id=worker_id,
        batch_size=batch_size,
        lease_seconds=lease_seconds,
        reason=reason,
    )
    if not targets:
        return 0, 0

    sem = asyncio.Semaphore(concurrency)

    async def _process(target) -> int:
        cnpj = f"{target.cnpj_basico}{target.cnpj_ordem}{target.cnpj_dv}"
        async with sem:
            try:
                outcome = await discover_target(
                    pool,
                    cnpj_basico=target.cnpj_basico,
                    cnpj_ordem=target.cnpj_ordem,
                    cnpj_dv=target.cnpj_dv,
                    client=client,
                    external_search=external_search,
                    dns_only=dns_only,
                )
                await complete_target(pool, target_id=target.id, status="done")
                return outcome.crawl_requests_created
            except SearchRateLimitError as exc:
                _source_backoffs[exc.source] = time.time() + exc.retry_after
                logger.warning(
                    "search_rate_limit cnpj={} source={} retry_after={}s backoff_until={}",
                    cnpj, exc.source, exc.retry_after,
                    time.strftime("%H:%M:%S", time.localtime(_source_backoffs[exc.source])),
                )
                await complete_target(
                    pool,
                    target_id=target.id,
                    status="retry",
                    retry_in_seconds=exc.retry_after,
                    last_error=str(exc),
                )
                return 0
            except Exception as exc:
                logger.error("discovery_error cnpj={} error={}: {}", cnpj, type(exc).__name__, exc)
                await complete_target(
                    pool,
                    target_id=target.id,
                    status="retry",
                    retry_in_seconds=300,
                    last_error=f"{type(exc).__name__}: {exc}",
                )
                return 0

    results = await asyncio.gather(*[_process(t) for t in targets])
    return len(targets), sum(results)


async def do_crawler(
    pool,
    *,
    client,
    worker_id: str,
    batch_size: int,
    lease_seconds: int,
    user_agent: str,
) -> tuple[int, int]:
    stats = await run_crawl_batch(
        pool,
        client=client,
        worker_id=worker_id,
        batch_size=batch_size,
        lease_seconds=lease_seconds,
        user_agent=user_agent,
    )
    return stats.requests_done, stats.contacts_published


async def do_release_stale(pool, *, lease_seconds: int) -> int:
    targets = await release_stale_locks(pool, lease_seconds=lease_seconds)
    requests = await release_stale_requests(pool, lease_seconds=lease_seconds)
    demand = await release_stale_demand_items(pool)
    return targets + requests + demand


async def do_demand_tick(
    pool,
    *,
    client,
    worker_id: str,
    batch_size: int,
    lease_seconds: int,
    concurrency: int,
) -> tuple[int, int]:
    items = await claim_demand_items(
        pool,
        worker_id=worker_id,
        batch_size=batch_size,
        lease_seconds=lease_seconds,
    )
    if not items:
        return 0, 0

    sem = asyncio.Semaphore(concurrency)

    async def _process(item) -> bool:
        async with sem:
            try:
                await discover_target(
                    pool,
                    cnpj_basico=item.cnpj_basico,
                    cnpj_ordem=item.cnpj_ordem,
                    cnpj_dv=item.cnpj_dv,
                    client=client,
                    external_search=_build_external_search(),
                    dns_only=False,
                )
                contacts = await count_published_contacts(pool, item)
                await complete_demand_item(
                    pool,
                    item_id=item.id,
                    status="enriched" if contacts else "no_public_contact",
                    result_source="fresh_crawl" if contacts else "none",
                )
                return True
            except SearchRateLimitError as exc:
                _source_backoffs[exc.source] = time.time() + exc.retry_after
                await complete_demand_item(
                    pool,
                    item_id=item.id,
                    status="failed_retryable",
                    last_error=str(exc),
                )
                return False
            except Exception as exc:
                logger.error("demand_enrichment_error cnpj={} error={}: {}", item.cnpj, type(exc).__name__, exc)
                await complete_demand_item(
                    pool,
                    item_id=item.id,
                    status="failed_retryable",
                    last_error=f"{type(exc).__name__}: {exc}",
                )
                return False

    results = await asyncio.gather(*[_process(item) for item in items])
    done = sum(1 for ok in results if ok)
    return done, len(items) - done


async def do_trickle_loop(pool, client, args) -> TickStats:
    demand_waiting = await has_pending_demand(pool)
    released = await do_release_stale(pool, lease_seconds=args.lease_seconds)
    if demand_waiting:
        return TickStats(leases_released=released)

    seeded = await do_seed(
        pool,
        reason=args.reason,
        priority=args.priority,
        batch_size=args.seed_batch_size,
    )
    claimed, crawl_created = await do_discovery(
        pool,
        client=client,
        worker_id=args.worker_id,
        batch_size=args.discovery_batch_size,
        lease_seconds=args.lease_seconds,
        concurrency=args.concurrency,
        external_search=_build_external_search(),
        reason=args.reason,
    )
    crawler_done, contacts = await do_crawler(
        pool,
        client=client,
        worker_id=args.worker_id,
        batch_size=args.crawl_batch_size,
        lease_seconds=args.lease_seconds,
        user_agent=args.user_agent,
    )
    return TickStats(
        seeded=seeded,
        targets_claimed=claimed,
        crawl_requests_created=crawl_created,
        crawler_done=crawler_done,
        contacts_published=contacts,
        leases_released=released,
    )


def _build_external_search() -> ExternalSearchClient:
    now = time.time()
    blocked = frozenset(src for src, until in _source_backoffs.items() if now < until)
    if blocked:
        logger.debug("external_search blocked_sources={}", sorted(blocked))
    return ExternalSearchClient(
        brasilapi_enabled=settings.brasilapi_enabled,
        brasilapi_base_url=settings.brasilapi_base_url,
        brave_api_key=settings.brave_search_api_key,
        brave_base_url=settings.brave_search_base_url,
        google_cse_api_key=settings.google_cse_api_key,
        google_cse_cx=settings.google_cse_cx,
        google_cse_base_url=settings.google_cse_base_url,
        searxng_url=settings.searxng_url,
        blocked_sources=blocked,
    )


async def do_one_loop(pool, client, args) -> TickStats:
    phase = getattr(args, "phase", 0)

    if phase == 1:
        seeded = await do_seed_phase1(pool, batch_size=args.seed_batch_size)
        claimed, crawl_created = await do_discovery(
            pool,
            client=client,
            worker_id=args.worker_id,
            batch_size=args.discovery_batch_size,
            lease_seconds=args.lease_seconds,
            dns_only=True,
            external_search=None,
            reason=_PHASE1_REASON,
        )
    elif phase == 2:
        seeded = await do_seed_phase2(pool, batch_size=args.seed_batch_size)
        claimed, crawl_created = await do_discovery(
            pool,
            client=client,
            worker_id=args.worker_id,
            batch_size=args.discovery_batch_size,
            lease_seconds=args.lease_seconds,
            dns_only=False,
            external_search=_build_external_search(),
            reason=_PHASE2_REASON,
        )
    else:
        seeded = await do_seed(
            pool,
            reason=args.reason,
            priority=args.priority,
            batch_size=args.seed_batch_size,
        )
        claimed, crawl_created = await do_discovery(
            pool,
            client=client,
            worker_id=args.worker_id,
            batch_size=args.discovery_batch_size,
            lease_seconds=args.lease_seconds,
            external_search=_build_external_search(),
        )

    # Phase 1 (DNS-only sweep) skips HTTP crawling — pure throughput mode.
    if phase != 1 and args.crawl_batch_size > 0:
        crawler_done, contacts = await do_crawler(
            pool,
            client=client,
            worker_id=args.worker_id,
            batch_size=args.crawl_batch_size,
            lease_seconds=args.lease_seconds,
            user_agent=args.user_agent,
        )
    else:
        crawler_done, contacts = 0, 0
    released = await do_release_stale(pool, lease_seconds=args.lease_seconds)
    return TickStats(
        seeded=seeded,
        targets_claimed=claimed,
        crawl_requests_created=crawl_created,
        crawler_done=crawler_done,
        contacts_published=contacts,
        leases_released=released,
    )


async def cmd_seed(args) -> None:
    pool = await create_pool()
    try:
        seeded = await do_seed(
            pool,
            reason=args.reason,
            priority=args.priority,
            batch_size=args.batch_size,
        )
        print(f"seed-targets reason={args.reason} rows={seeded}")
    finally:
        await close_pool()


async def cmd_seed_phase1(args) -> None:
    pool = await create_pool()
    try:
        seeded = await do_seed_phase1(pool, batch_size=args.batch_size)
        print(f"seed-phase1 rows={seeded}")
    finally:
        await close_pool()


async def cmd_seed_phase2(args) -> None:
    pool = await create_pool()
    try:
        seeded = await do_seed_phase2(pool, batch_size=args.batch_size)
        print(f"seed-phase2 rows={seeded}")
    finally:
        await close_pool()


async def cmd_discovery(args) -> None:
    pool = await create_pool()
    try:
        async with make_default_client(user_agent=args.user_agent) as client:
            claimed, created = await do_discovery(
                pool,
                client=client,
                worker_id=args.worker_id,
                batch_size=args.batch_size,
                lease_seconds=args.lease_seconds,
            )
        print(
            f"discovery-tick worker={args.worker_id} claimed={claimed} "
            f"crawl_requests_created={created}"
        )
    finally:
        await close_pool()


async def cmd_crawler(args) -> None:
    pool = await create_pool()
    try:
        async with make_default_client(user_agent=args.user_agent) as client:
            done, contacts = await do_crawler(
                pool,
                client=client,
                worker_id=args.worker_id,
                batch_size=args.batch_size,
                lease_seconds=args.lease_seconds,
                user_agent=args.user_agent,
            )
        print(
            f"crawler-tick worker={args.worker_id} done={done} contacts={contacts}"
        )
    finally:
        await close_pool()


async def cmd_release_stale(args) -> None:
    pool = await create_pool()
    try:
        released = await do_release_stale(pool, lease_seconds=args.lease_seconds)
        # Also release stale domain jobs
        domain_released = await release_stale_domain_jobs(
            pool, lease_seconds=args.lease_seconds
        )
        print(
            f"release-stale released={released + domain_released} "
            f"(cnpj_demand_and_legacy={released} domain={domain_released}) lease={args.lease_seconds}s"
        )
    finally:
        await close_pool()


async def cmd_enqueue_domain_jobs(args) -> None:
    pool = await create_pool()
    try:
        domains_seen, jobs_inserted = await enqueue_jobs_from_verified_domains(
            pool,
            source="verified_domain",
            priority=args.priority,
            batch_size=args.batch_size,
            cursor_id=args.cursor_id,
        )
        print(
            f"enqueue-domain-jobs domains={domains_seen} jobs_inserted={jobs_inserted}"
        )
    finally:
        await close_pool()


async def cmd_domain_crawler(args) -> None:
    pool = await create_pool()
    try:
        async with make_default_client(user_agent=args.user_agent) as client:
            iteration = 0
            enqueue_cursor = 0
            while True:
                await heartbeat_beat(
                    pool,
                    worker_id=args.worker_id,
                    role="domain-crawler",
                    current_stage="enqueue",
                )
                # Self-enqueue: every iteration, advance cursor through verified
                # company_domains so the crawl queue never starves. Uses sitemap.xml
                # to discover real URLs instead of guessing paths (avoids 70% 404s).
                async def _discover(homepage_url: str) -> list[str]:
                    return await discover_crawl_urls(client, homepage_url)

                domains_seen, jobs_inserted = await enqueue_jobs_from_verified_domains(
                    pool,
                    source="verified_domain",
                    priority=50,
                    batch_size=args.enqueue_batch_size,
                    cursor_id=enqueue_cursor,
                    url_discoverer=_discover,
                )
                if domains_seen > 0:
                    enqueue_cursor = await _max_company_domain_id_seen(
                        pool, after_id=enqueue_cursor, limit=args.enqueue_batch_size
                    )
                else:
                    # Restart from beginning so new verified domains get picked up.
                    enqueue_cursor = 0
                await heartbeat_beat(
                    pool,
                    worker_id=args.worker_id,
                    role="domain-crawler",
                    current_stage="crawl",
                    metadata={"enqueue_cursor": enqueue_cursor, "jobs_inserted": jobs_inserted},
                )
                stats = await run_domain_batch(
                    pool,
                    client=client,
                    worker_id=args.worker_id,
                    batch_size=args.batch_size,
                    lease_seconds=args.lease_seconds,
                    user_agent=args.user_agent,
                )
                logger.info(
                    "domain_crawler_loop iter={} enqueued_domains={} enqueued_jobs={} cursor={} "
                    "claimed={} done={} retried={} blocked={} errored={} budget_skipped={} contacts={}",
                    iteration, domains_seen, jobs_inserted, enqueue_cursor,
                    stats.jobs_claimed, stats.jobs_done, stats.jobs_retried,
                    stats.jobs_blocked, stats.jobs_errored, stats.budget_skipped,
                    stats.contacts_extracted,
                )
                iteration += 1
                if args.max_iters and iteration >= args.max_iters:
                    return
                await asyncio.sleep(args.interval)
    finally:
        try:
            await heartbeat_remove(pool, worker_id=args.worker_id)
        except Exception:  # pragma: no cover
            pass
        await close_pool()


async def _max_company_domain_id_seen(pool, *, after_id: int, limit: int) -> int:
    """Return the max company_domains.id within the next `limit` verified rows after `after_id`.
    Used by the self-enqueue loop in domain-crawler to advance its cursor."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT MAX(id) AS max_id FROM (
                SELECT id FROM paid_enrichment.company_domains
                WHERE status='verified' AND id > $1
                ORDER BY id LIMIT $2
            ) sub
            """,
            after_id, limit,
        )
    return int(row["max_id"]) if row and row["max_id"] is not None else after_id


async def cmd_resolve_domain(args) -> None:
    pool = await create_pool()
    worker_id = getattr(args, "worker_id", None) or default_worker_id()
    try:
        iteration = 0
        while True:
            await heartbeat_beat(
                pool, worker_id=worker_id, role="domain-resolver", current_stage="resolve",
            )
            stats = await resolve_domain_contacts(
                pool,
                batch_size=args.batch_size,
                cursor_id=args.cursor_id,
            )
            logger.info(
                "domain_resolver_loop iter={} domains={} shared_skip={} "
                "published={} suppressed={} below={}",
                iteration, stats.domains_processed, stats.domains_shared_skipped,
                stats.contacts_published, stats.contacts_suppressed,
                stats.contacts_below_threshold,
            )
            iteration += 1
            if args.max_iters and iteration >= args.max_iters:
                return
            await asyncio.sleep(args.interval)
    finally:
        try:
            await heartbeat_remove(pool, worker_id=worker_id)
        except Exception:  # pragma: no cover
            pass
        await close_pool()


async def cmd_enqueue_playwright_jobs(args) -> None:
    pool = await create_pool()
    try:
        domains_seen, jobs_inserted = await enqueue_playwright_jobs_for_zero_contact_domains(
            pool,
            batch_size=args.batch_size,
        )
        print(
            f"enqueue-playwright-jobs domains={domains_seen} jobs_inserted={jobs_inserted}"
        )
    finally:
        await close_pool()


async def cmd_playwright_crawler(args) -> None:
    from playwright.async_api import async_playwright

    pool = await create_pool()
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                stats = await run_playwright_batch(
                    pool,
                    browser=browser,
                    worker_id=args.worker_id,
                    batch_size=args.batch_size,
                    lease_seconds=args.lease_seconds,
                    user_agent=args.user_agent,
                )
            finally:
                await browser.close()
        print(
            f"playwright-crawler-tick worker={args.worker_id} "
            f"claimed={stats.jobs_claimed} done={stats.jobs_done} "
            f"retried={stats.jobs_retried} blocked={stats.jobs_blocked} "
            f"errored={stats.jobs_errored} contacts={stats.contacts_extracted}"
        )
    finally:
        await close_pool()


async def cmd_worker(args) -> None:
    pool = await create_pool()
    role = f"enrichment-phase{args.phase}" if args.phase in (1, 2) else "enrichment"
    try:
        async with make_default_client(user_agent=args.user_agent) as client:
            iteration = 0
            while True:
                await heartbeat_beat(
                    pool, worker_id=args.worker_id, role=role, current_stage="tick",
                    metadata={"phase": args.phase, "iter": iteration},
                )
                stats = await do_one_loop(pool, client, args)
                logger.info(
                    "worker_loop iter={} seeded={} claimed={} crawl_created={} done={} contacts={} released={}",
                    iteration,
                    stats.seeded,
                    stats.targets_claimed,
                    stats.crawl_requests_created,
                    stats.crawler_done,
                    stats.contacts_published,
                    stats.leases_released,
                )
                iteration += 1
                if args.max_iters and iteration >= args.max_iters:
                    return
                await asyncio.sleep(args.interval)
    finally:
        try:
            await heartbeat_remove(pool, worker_id=args.worker_id)
        except Exception:  # pragma: no cover
            pass
        await close_pool()


async def cmd_demand_worker(args) -> None:
    pool = await create_pool()
    try:
        async with make_default_client(user_agent=args.user_agent) as client:
            iteration = 0
            while True:
                await heartbeat_beat(
                    pool,
                    worker_id=args.worker_id,
                    role="enrichment-demand",
                    current_stage="tick",
                    metadata={"iter": iteration},
                )
                done, failed = await do_demand_tick(
                    pool,
                    client=client,
                    worker_id=args.worker_id,
                    batch_size=args.batch_size,
                    lease_seconds=args.lease_seconds,
                    concurrency=args.concurrency,
                )
                if iteration % max(args.release_every, 1) == 0:
                    released = await do_release_stale(pool, lease_seconds=args.lease_seconds)
                else:
                    released = 0
                logger.info(
                    "demand_worker_loop iter={} done={} failed={} released={}",
                    iteration, done, failed, released,
                )
                iteration += 1
                if args.max_iters and iteration >= args.max_iters:
                    return
                await asyncio.sleep(args.interval)
    finally:
        try:
            await heartbeat_remove(pool, worker_id=args.worker_id)
        except Exception:  # pragma: no cover
            pass
        await close_pool()


async def cmd_trickle_worker(args) -> None:
    pool = await create_pool()
    try:
        async with make_default_client(user_agent=args.user_agent) as client:
            iteration = 0
            while True:
                await heartbeat_beat(
                    pool,
                    worker_id=args.worker_id,
                    role="enrichment-trickle",
                    current_stage="tick",
                    metadata={"iter": iteration},
                )
                stats = await do_trickle_loop(pool, client, args)
                logger.info(
                    "trickle_worker_loop iter={} seeded={} claimed={} crawl_created={} done={} contacts={} released={}",
                    iteration,
                    stats.seeded,
                    stats.targets_claimed,
                    stats.crawl_requests_created,
                    stats.crawler_done,
                    stats.contacts_published,
                    stats.leases_released,
                )
                iteration += 1
                if args.max_iters and iteration >= args.max_iters:
                    return
                await asyncio.sleep(args.interval)
    finally:
        try:
            await heartbeat_remove(pool, worker_id=args.worker_id)
        except Exception:  # pragma: no cover
            pass
        await close_pool()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="enrichment", description="Enrichment CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed-targets")
    seed.add_argument("--reason", default="missing_contacts")
    seed.add_argument("--priority", type=int, default=50)
    seed.add_argument("--batch-size", type=int, default=1000)
    seed.set_defaults(func=cmd_seed)

    discovery = sub.add_parser("discovery-tick")
    discovery.add_argument("--worker-id", default=default_worker_id())
    discovery.add_argument("--batch-size", type=int, default=20)
    discovery.add_argument("--lease-seconds", type=int, default=300)
    discovery.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    discovery.set_defaults(func=cmd_discovery)

    crawler = sub.add_parser("crawler-tick")
    crawler.add_argument("--worker-id", default=default_worker_id())
    crawler.add_argument("--batch-size", type=int, default=20)
    crawler.add_argument("--lease-seconds", type=int, default=600)
    crawler.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    crawler.set_defaults(func=cmd_crawler)

    release = sub.add_parser("release-stale")
    release.add_argument("--lease-seconds", type=int, default=600)
    release.set_defaults(func=cmd_release_stale)

    enqueue = sub.add_parser("enqueue-domain-jobs")
    enqueue.add_argument("--priority", type=int, default=50)
    enqueue.add_argument("--batch-size", type=int, default=1000)
    enqueue.add_argument("--cursor-id", type=int, default=0)
    enqueue.set_defaults(func=cmd_enqueue_domain_jobs)

    domain_crawler = sub.add_parser("domain-crawler-tick")
    domain_crawler.add_argument("--worker-id", default=default_worker_id())
    domain_crawler.add_argument("--batch-size", type=int, default=20)
    domain_crawler.add_argument("--lease-seconds", type=int, default=600)
    domain_crawler.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    domain_crawler.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS)
    domain_crawler.add_argument("--max-iters", type=int, default=0, help="0 = sem limite")
    domain_crawler.add_argument("--enqueue-batch-size", type=int, default=25,
                                help="quantos verified domains enfileirar por iter")
    domain_crawler.set_defaults(func=cmd_domain_crawler)

    resolve = sub.add_parser("resolve-domain-tick")
    resolve.add_argument("--worker-id", default=default_worker_id())
    resolve.add_argument("--batch-size", type=int, default=1000)
    resolve.add_argument("--cursor-id", type=int, default=0)
    resolve.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS)
    resolve.add_argument("--max-iters", type=int, default=0, help="0 = sem limite")
    resolve.set_defaults(func=cmd_resolve_domain)

    enqueue_pw = sub.add_parser("enqueue-playwright-jobs")
    enqueue_pw.add_argument("--batch-size", type=int, default=200)
    enqueue_pw.set_defaults(func=cmd_enqueue_playwright_jobs)

    playwright = sub.add_parser("playwright-crawler-tick")
    playwright.add_argument("--worker-id", default=default_worker_id())
    playwright.add_argument("--batch-size", type=int, default=5)
    playwright.add_argument("--lease-seconds", type=int, default=600)
    playwright.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    playwright.set_defaults(func=cmd_playwright_crawler)

    worker = sub.add_parser("worker")
    worker.add_argument("--worker-id", default=default_worker_id())
    worker.add_argument("--reason", default="missing_contacts")
    worker.add_argument("--priority", type=int, default=50)
    worker.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS)
    worker.add_argument("--seed-batch-size", type=int, default=1000)
    worker.add_argument("--discovery-batch-size", type=int, default=20)
    worker.add_argument("--crawl-batch-size", type=int, default=20)
    worker.add_argument("--lease-seconds", type=int, default=600)
    worker.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    worker.add_argument("--max-iters", type=int, default=0, help="0 = sem limite")
    worker.add_argument("--phase", type=int, default=0,
                        help="1=dns-only sweep, 2=external search, 0=legacy")
    worker.set_defaults(func=cmd_worker)

    demand = sub.add_parser("demand-worker")
    demand.add_argument("--worker-id", default=default_worker_id())
    demand.add_argument("--batch-size", type=int, default=20)
    demand.add_argument("--concurrency", type=int, default=2)
    demand.add_argument("--interval", type=int, default=5)
    demand.add_argument("--lease-seconds", type=int, default=600)
    demand.add_argument("--release-every", type=int, default=60)
    demand.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    demand.add_argument("--max-iters", type=int, default=0, help="0 = sem limite")
    demand.set_defaults(func=cmd_demand_worker)

    trickle = sub.add_parser("trickle-worker")
    trickle.add_argument("--worker-id", default=default_worker_id())
    trickle.add_argument("--reason", default="trickle")
    trickle.add_argument("--priority", type=int, default=10)
    trickle.add_argument("--seed-batch-size", type=int, default=25)
    trickle.add_argument("--discovery-batch-size", type=int, default=5)
    trickle.add_argument("--crawl-batch-size", type=int, default=5)
    trickle.add_argument("--concurrency", type=int, default=1)
    trickle.add_argument("--interval", type=int, default=120)
    trickle.add_argument("--lease-seconds", type=int, default=600)
    trickle.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    trickle.add_argument("--max-iters", type=int, default=0, help="0 = sem limite")
    trickle.set_defaults(func=cmd_trickle_worker)

    seed_p1 = sub.add_parser("seed-phase1")
    seed_p1.add_argument("--batch-size", type=int, default=50_000)
    seed_p1.set_defaults(func=cmd_seed_phase1)

    seed_p2 = sub.add_parser("seed-phase2")
    seed_p2.add_argument("--batch-size", type=int, default=10_000)
    seed_p2.set_defaults(func=cmd_seed_phase2)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    asyncio.run(args.func(args))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
