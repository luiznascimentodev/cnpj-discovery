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
from dataclasses import dataclass

DISCOVERY_CONCURRENCY = 10  # parallel HTTP probes per worker instance

from loguru import logger

from crawler.domain_queue import (
    enqueue_jobs_from_verified_domains,
    enqueue_playwright_jobs_for_zero_contact_domains,
    release_stale_domain_jobs,
)
from crawler.domain_runner import run_domain_batch
from crawler.playwright_runner import PlaywrightRunStats, run_playwright_batch
from crawler.queue import release_stale_requests
from crawler.runner import run_batch as run_crawl_batch
from database import close_pool, create_pool
from config import settings
from discovery.external_search import ExternalSearchClient
from discovery.pipeline import process_target as discover_target
from discovery.website_probe import DEFAULT_USER_AGENT, make_default_client
from resolver.domain_resolver import resolve_domain_contacts
from scheduler import (
    claim_targets,
    complete_target,
    release_stale_locks,
    seed_active_targets,
)

DEFAULT_INTERVAL_SECONDS = 30


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


async def do_seed(pool, *, reason: str, priority: int, batch_size: int) -> int:
    return await seed_active_targets(
        pool,
        reason=reason,
        priority=priority,
        batch_size=batch_size,
    )


async def do_discovery(
    pool,
    *,
    client,
    worker_id: str,
    batch_size: int,
    lease_seconds: int,
    concurrency: int = DISCOVERY_CONCURRENCY,
    external_search=None,
) -> tuple[int, int]:
    targets = await claim_targets(
        pool,
        worker_id=worker_id,
        batch_size=batch_size,
        lease_seconds=lease_seconds,
    )
    if not targets:
        return 0, 0

    sem = asyncio.Semaphore(concurrency)

    async def _process(target) -> int:
        async with sem:
            try:
                outcome = await discover_target(
                    pool,
                    cnpj_basico=target.cnpj_basico,
                    cnpj_ordem=target.cnpj_ordem,
                    cnpj_dv=target.cnpj_dv,
                    client=client,
                    external_search=external_search,
                )
                await complete_target(pool, target_id=target.id, status="done")
                return outcome.crawl_requests_created
            except Exception as exc:
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
    return targets + requests


def _build_external_search() -> ExternalSearchClient:
    return ExternalSearchClient(
        brasilapi_enabled=settings.brasilapi_enabled,
        brasilapi_base_url=settings.brasilapi_base_url,
        brave_api_key=settings.brave_search_api_key,
        brave_base_url=settings.brave_search_base_url,
        google_cse_api_key=settings.google_cse_api_key,
        google_cse_cx=settings.google_cse_cx,
        google_cse_base_url=settings.google_cse_base_url,
        searxng_url=settings.searxng_url,
    )


async def do_one_loop(pool, client, args) -> TickStats:
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
    crawler_done, contacts = await do_crawler(
        pool,
        client=client,
        worker_id=args.worker_id,
        batch_size=args.crawl_batch_size,
        lease_seconds=args.lease_seconds,
        user_agent=args.user_agent,
    )
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
            f"(cnpj={released} domain={domain_released}) lease={args.lease_seconds}s"
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
            while True:
                stats = await run_domain_batch(
                    pool,
                    client=client,
                    worker_id=args.worker_id,
                    batch_size=args.batch_size,
                    lease_seconds=args.lease_seconds,
                    user_agent=args.user_agent,
                )
                logger.info(
                    "domain_crawler_loop iter={} claimed={} done={} retried={} blocked={} "
                    "errored={} budget_skipped={} contacts={}",
                    iteration, stats.jobs_claimed, stats.jobs_done, stats.jobs_retried,
                    stats.jobs_blocked, stats.jobs_errored, stats.budget_skipped,
                    stats.contacts_extracted,
                )
                iteration += 1
                if args.max_iters and iteration >= args.max_iters:
                    return
                await asyncio.sleep(args.interval)
    finally:
        await close_pool()


async def cmd_resolve_domain(args) -> None:
    pool = await create_pool()
    try:
        iteration = 0
        while True:
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
    try:
        async with make_default_client(user_agent=args.user_agent) as client:
            iteration = 0
            while True:
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
    domain_crawler.set_defaults(func=cmd_domain_crawler)

    resolve = sub.add_parser("resolve-domain-tick")
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
    worker.set_defaults(func=cmd_worker)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    asyncio.run(args.func(args))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
