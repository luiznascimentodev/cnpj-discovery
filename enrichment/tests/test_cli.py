import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

import cli
from cli import (
    DEFAULT_INTERVAL_SECONDS,
    TickStats,
    build_parser,
    cmd_crawler,
    cmd_discovery,
    cmd_domain_crawler,
    cmd_enqueue_domain_jobs,
    cmd_enqueue_playwright_jobs,
    cmd_playwright_crawler,
    cmd_release_stale,
    cmd_demand_worker,
    cmd_trickle_worker,
    cmd_resolve_domain,
    cmd_seed,
    cmd_seed_phase1,
    cmd_seed_phase2,
    cmd_worker,
    default_worker_id,
    do_crawler,
    do_discovery,
    do_one_loop,
    do_release_stale,
    do_demand_tick,
    do_seed,
    do_seed_phase1,
    do_seed_phase2,
    do_trickle_loop,
    main,
)
from crawler.domain_runner import DomainRunStats
from crawler.runner import RunStats
from discovery.errors import SearchRateLimitError
from discovery.pipeline import DiscoveryOutcome
from resolver.domain_resolver import ResolveStats
from scheduler import ClaimedTarget


def _stub_client():
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))


class TestParser:
    def test_seed_targets_subcommand(self):
        args = build_parser().parse_args(["seed-targets", "--batch-size", "10"])

        assert args.command == "seed-targets"
        assert args.batch_size == 10

    def test_worker_subcommand_defaults(self):
        args = build_parser().parse_args(["worker", "--max-iters", "1"])

        assert args.command == "worker"
        assert args.interval == DEFAULT_INTERVAL_SECONDS

    def test_release_stale_subcommand(self):
        args = build_parser().parse_args(["release-stale"])

        assert args.lease_seconds == 600

    def test_default_worker_id_includes_hostname(self):
        worker_id = default_worker_id()
        assert worker_id


class TestDoFunctions:
    @pytest.mark.asyncio
    async def test_do_seed_proxies_to_scheduler(self):
        pool = object()
        with patch("cli.seed_active_targets", new_callable=AsyncMock, return_value=42) as m:
            result = await do_seed(pool, reason="r", priority=10, batch_size=5)

        assert result == 42
        m.assert_awaited_once_with(pool, reason="r", priority=10, batch_size=5)

    @pytest.mark.asyncio
    async def test_do_discovery_handles_targets_and_failures(self):
        targets = [
            ClaimedTarget(
                id=1, cnpj_basico="12345678", cnpj_ordem="0001", cnpj_dv="90",
                reason="r", attempts=1, priority=50,
            ),
            ClaimedTarget(
                id=2, cnpj_basico="22222222", cnpj_ordem="0001", cnpj_dv="00",
                reason="r", attempts=1, priority=50,
            ),
        ]

        async def discover_side_effect(pool, *, cnpj_basico, cnpj_ordem, cnpj_dv, client, external_search=None, dns_only=False):
            if cnpj_basico == "22222222":
                raise RuntimeError("boom")
            return DiscoveryOutcome(cnpj="x", domains_seen=2, crawl_requests_created=5)

        with (
            patch("cli.claim_targets", new_callable=AsyncMock, return_value=targets),
            patch("cli.discover_target", AsyncMock(side_effect=discover_side_effect)),
            patch("cli.complete_target", new_callable=AsyncMock) as complete,
        ):
            async with _stub_client() as client:
                claimed, created = await do_discovery(
                    object(),
                    client=client,
                    worker_id="w",
                    batch_size=10,
                    lease_seconds=300,
                )

        assert claimed == 2
        assert created == 5
        # second target should have been retried
        retry_calls = [c for c in complete.await_args_list if c.kwargs.get("status") == "retry"]
        done_calls = [c for c in complete.await_args_list if c.kwargs.get("status") == "done"]
        assert len(retry_calls) == 1
        assert len(done_calls) == 1

    @pytest.mark.asyncio
    async def test_do_discovery_returns_zeros_when_no_targets(self):
        with patch("cli.claim_targets", new_callable=AsyncMock, return_value=[]):
            async with _stub_client() as client:
                claimed, created = await do_discovery(
                    object(), client=client, worker_id="w", batch_size=10, lease_seconds=300
                )
        assert claimed == 0
        assert created == 0

    @pytest.mark.asyncio
    async def test_do_crawler_proxies_run_batch(self):
        with patch(
            "cli.run_crawl_batch",
            new_callable=AsyncMock,
            return_value=RunStats(
                requests_claimed=2,
                pages_fetched=2,
                contacts_published=3,
                requests_done=2,
            ),
        ):
            async with _stub_client() as client:
                done, contacts = await do_crawler(
                    object(),
                    client=client,
                    worker_id="w",
                    batch_size=10,
                    lease_seconds=600,
                    user_agent="UA",
                )

        assert done == 2
        assert contacts == 3

    @pytest.mark.asyncio
    async def test_do_release_stale_sums_targets_and_requests(self):
        with (
            patch("cli.release_stale_locks", new_callable=AsyncMock, return_value=2),
            patch("cli.release_stale_requests", new_callable=AsyncMock, return_value=3),
            patch("cli.release_stale_demand_items", new_callable=AsyncMock, return_value=4),
        ):
            total = await do_release_stale(object(), lease_seconds=300)

        assert total == 9

    @pytest.mark.asyncio
    async def test_do_demand_tick_processes_items(self):
        from demand_queue import DemandItem

        item = DemandItem(
            id=1,
            job_id=10,
            account_id="acct",
            cnpj_basico="12345678",
            cnpj_ordem="0001",
            cnpj_dv="90",
            attempts=1,
            priority=1000,
        )
        with (
            patch("cli.claim_demand_items", new_callable=AsyncMock, return_value=[item]),
            patch("cli.discover_target", new_callable=AsyncMock, return_value=DiscoveryOutcome(cnpj=item.cnpj, domains_seen=1, crawl_requests_created=0)),
            patch("cli.count_published_contacts", new_callable=AsyncMock, return_value=2),
            patch("cli.complete_demand_item", new_callable=AsyncMock) as complete,
            patch("cli._build_external_search", return_value=object()),
        ):
            async with _stub_client() as client:
                done, failed = await do_demand_tick(
                    object(),
                    client=client,
                    worker_id="w",
                    batch_size=5,
                    lease_seconds=600,
                    concurrency=1,
                )

        assert (done, failed) == (1, 0)
        assert complete.await_args.kwargs["status"] == "enriched"

    @pytest.mark.asyncio
    async def test_do_demand_tick_returns_zero_when_empty(self):
        with patch("cli.claim_demand_items", new_callable=AsyncMock, return_value=[]):
            async with _stub_client() as client:
                result = await do_demand_tick(
                    object(),
                    client=client,
                    worker_id="w",
                    batch_size=5,
                    lease_seconds=600,
                    concurrency=1,
                )

        assert result == (0, 0)

    @pytest.mark.asyncio
    async def test_do_demand_tick_handles_search_rate_limit(self):
        from demand_queue import DemandItem

        item = DemandItem(
            id=1,
            job_id=10,
            account_id="acct",
            cnpj_basico="12345678",
            cnpj_ordem="0001",
            cnpj_dv="90",
            attempts=1,
            priority=1000,
        )
        with (
            patch("cli.claim_demand_items", new_callable=AsyncMock, return_value=[item]),
            patch("cli.discover_target", new_callable=AsyncMock, side_effect=SearchRateLimitError("brave", retry_after=120)),
            patch("cli.complete_demand_item", new_callable=AsyncMock) as complete,
        ):
            cli._source_backoffs.clear()
            async with _stub_client() as client:
                done, failed = await do_demand_tick(
                    object(),
                    client=client,
                    worker_id="w",
                    batch_size=5,
                    lease_seconds=600,
                    concurrency=1,
                )

        assert (done, failed) == (0, 1)
        assert "brave" in cli._source_backoffs
        assert complete.await_args.kwargs["status"] == "failed_retryable"

    @pytest.mark.asyncio
    async def test_do_demand_tick_retries_failures(self):
        from demand_queue import DemandItem

        item = DemandItem(
            id=1,
            job_id=10,
            account_id="acct",
            cnpj_basico="12345678",
            cnpj_ordem="0001",
            cnpj_dv="90",
            attempts=1,
            priority=1000,
        )
        with (
            patch("cli.claim_demand_items", new_callable=AsyncMock, return_value=[item]),
            patch("cli.discover_target", new_callable=AsyncMock, side_effect=RuntimeError("boom")),
            patch("cli.complete_demand_item", new_callable=AsyncMock) as complete,
        ):
            async with _stub_client() as client:
                done, failed = await do_demand_tick(
                    object(),
                    client=client,
                    worker_id="w",
                    batch_size=5,
                    lease_seconds=600,
                    concurrency=1,
                )

        assert (done, failed) == (0, 1)
        assert complete.await_args.kwargs["status"] == "failed_retryable"

    @pytest.mark.asyncio
    async def test_do_trickle_loop_skips_when_demand_waits(self):
        args = SimpleNamespace(lease_seconds=600)
        with (
            patch("cli.has_pending_demand", new_callable=AsyncMock, return_value=True),
            patch("cli.do_release_stale", new_callable=AsyncMock, return_value=2),
        ):
            async with _stub_client() as client:
                stats = await do_trickle_loop(object(), client, args)

        assert stats.leases_released == 2
        assert stats.seeded == 0

    @pytest.mark.asyncio
    async def test_do_trickle_loop_runs_low_priority_work(self):
        args = SimpleNamespace(
            reason="trickle",
            priority=10,
            seed_batch_size=25,
            worker_id="w",
            discovery_batch_size=5,
            crawl_batch_size=5,
            lease_seconds=600,
            user_agent="UA",
            concurrency=1,
        )
        with (
            patch("cli.has_pending_demand", new_callable=AsyncMock, return_value=False),
            patch("cli.do_release_stale", new_callable=AsyncMock, return_value=1),
            patch("cli.do_seed", new_callable=AsyncMock, return_value=25),
            patch("cli.do_discovery", new_callable=AsyncMock, return_value=(5, 3)),
            patch("cli.do_crawler", new_callable=AsyncMock, return_value=(2, 2)),
            patch("cli._build_external_search", return_value=object()),
        ):
            async with _stub_client() as client:
                stats = await do_trickle_loop(object(), client, args)

        assert stats.seeded == 25
        assert stats.contacts_published == 2

    @pytest.mark.asyncio
    async def test_do_one_loop_aggregates_stats(self):
        args = SimpleNamespace(
            reason="r",
            priority=50,
            seed_batch_size=10,
            worker_id="w",
            discovery_batch_size=5,
            crawl_batch_size=5,
            lease_seconds=600,
            user_agent="UA",
        )

        with (
            patch("cli.do_seed", new_callable=AsyncMock, return_value=10),
            patch("cli.do_discovery", new_callable=AsyncMock, return_value=(3, 12)),
            patch("cli.do_crawler", new_callable=AsyncMock, return_value=(2, 4)),
            patch("cli.do_release_stale", new_callable=AsyncMock, return_value=1),
        ):
            async with _stub_client() as client:
                stats = await do_one_loop(object(), client, args)

        assert stats == TickStats(
            seeded=10,
            targets_claimed=3,
            crawl_requests_created=12,
            crawler_done=2,
            contacts_published=4,
            leases_released=1,
        )


class TestCommandWrappers:
    @pytest.mark.asyncio
    async def test_cmd_seed_opens_and_closes_pool(self):
        args = SimpleNamespace(reason="r", priority=50, batch_size=10)
        pool = object()
        with (
            patch("cli.create_pool", AsyncMock(return_value=pool)) as create,
            patch("cli.close_pool", new_callable=AsyncMock) as close,
            patch("cli.do_seed", AsyncMock(return_value=10)),
        ):
            await cmd_seed(args)

        create.assert_awaited_once()
        close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cmd_discovery_uses_client_context(self):
        args = SimpleNamespace(
            user_agent="UA", worker_id="w", batch_size=5, lease_seconds=300
        )
        with (
            patch("cli.create_pool", AsyncMock(return_value=object())),
            patch("cli.close_pool", new_callable=AsyncMock),
            patch("cli.do_discovery", AsyncMock(return_value=(2, 4))),
        ):
            await cmd_discovery(args)

    @pytest.mark.asyncio
    async def test_cmd_crawler_uses_client_context(self):
        args = SimpleNamespace(
            user_agent="UA", worker_id="w", batch_size=5, lease_seconds=600
        )
        with (
            patch("cli.create_pool", AsyncMock(return_value=object())),
            patch("cli.close_pool", new_callable=AsyncMock),
            patch("cli.do_crawler", AsyncMock(return_value=(3, 9))),
        ):
            await cmd_crawler(args)

    @pytest.mark.asyncio
    async def test_cmd_release_stale_runs(self):
        args = SimpleNamespace(lease_seconds=300)
        with (
            patch("cli.create_pool", AsyncMock(return_value=object())),
            patch("cli.close_pool", new_callable=AsyncMock),
            patch("cli.do_release_stale", AsyncMock(return_value=4)),
            patch("cli.release_stale_domain_jobs", AsyncMock(return_value=2)),
        ):
            await cmd_release_stale(args)

    @pytest.mark.asyncio
    async def test_cmd_worker_runs_max_iters_then_exits(self):
        args = SimpleNamespace(
            user_agent="UA",
            worker_id="w",
            reason="r",
            priority=50,
            interval=0,
            seed_batch_size=10,
            discovery_batch_size=5,
            crawl_batch_size=5,
            lease_seconds=600,
            max_iters=2,
            phase=0,
        )
        empty_stats = TickStats()
        with (
            patch("cli.create_pool", AsyncMock(return_value=object())),
            patch("cli.close_pool", new_callable=AsyncMock),
            patch("cli.do_one_loop", AsyncMock(return_value=empty_stats)) as loop,
            patch("cli.heartbeat_beat", new_callable=AsyncMock),
            patch("cli.heartbeat_remove", new_callable=AsyncMock),
            patch("cli.asyncio.sleep", new_callable=AsyncMock),
        ):
            await cmd_worker(args)

        assert loop.await_count == 2

    @pytest.mark.asyncio
    async def test_cmd_worker_phase1_role(self):
        args = SimpleNamespace(
            user_agent="UA", worker_id="w", reason="r", priority=50, interval=0,
            seed_batch_size=10, discovery_batch_size=5, crawl_batch_size=0,
            lease_seconds=600, max_iters=1, phase=1,
        )
        with (
            patch("cli.create_pool", AsyncMock(return_value=object())),
            patch("cli.close_pool", new_callable=AsyncMock),
            patch("cli.do_one_loop", AsyncMock(return_value=TickStats())),
            patch("cli.heartbeat_beat", new_callable=AsyncMock) as hb,
            patch("cli.heartbeat_remove", new_callable=AsyncMock),
            patch("cli.asyncio.sleep", new_callable=AsyncMock),
        ):
            await cmd_worker(args)
        call_kwargs = hb.await_args.kwargs
        assert call_kwargs["role"] == "enrichment-phase1"

    @pytest.mark.asyncio
    async def test_cmd_demand_worker_runs_max_iters(self):
        args = SimpleNamespace(
            user_agent="UA",
            worker_id="w",
            batch_size=5,
            concurrency=1,
            lease_seconds=600,
            interval=0,
            release_every=1,
            max_iters=2,
        )
        with (
            patch("cli.create_pool", AsyncMock(return_value=object())),
            patch("cli.close_pool", new_callable=AsyncMock),
            patch("cli.do_demand_tick", AsyncMock(return_value=(1, 0))) as tick,
            patch("cli.do_release_stale", AsyncMock(return_value=0)),
            patch("cli.heartbeat_beat", new_callable=AsyncMock),
            patch("cli.heartbeat_remove", new_callable=AsyncMock),
            patch("cli.asyncio.sleep", new_callable=AsyncMock),
        ):
            await cmd_demand_worker(args)

        assert tick.await_count == 2

    @pytest.mark.asyncio
    async def test_cmd_demand_worker_skips_release_between_intervals(self):
        args = SimpleNamespace(
            user_agent="UA",
            worker_id="w",
            batch_size=5,
            concurrency=1,
            lease_seconds=600,
            interval=0,
            release_every=5,
            max_iters=2,
        )
        with (
            patch("cli.create_pool", AsyncMock(return_value=object())),
            patch("cli.close_pool", new_callable=AsyncMock),
            patch("cli.do_demand_tick", AsyncMock(return_value=(0, 0))),
            patch("cli.do_release_stale", AsyncMock(return_value=0)) as release,
            patch("cli.heartbeat_beat", new_callable=AsyncMock),
            patch("cli.heartbeat_remove", new_callable=AsyncMock),
            patch("cli.asyncio.sleep", new_callable=AsyncMock),
        ):
            await cmd_demand_worker(args)

        assert release.await_count == 1

    @pytest.mark.asyncio
    async def test_cmd_trickle_worker_runs_max_iters(self):
        args = SimpleNamespace(user_agent="UA", worker_id="w", interval=0, max_iters=2)
        with (
            patch("cli.create_pool", AsyncMock(return_value=object())),
            patch("cli.close_pool", new_callable=AsyncMock),
            patch("cli.do_trickle_loop", AsyncMock(return_value=TickStats())) as tick,
            patch("cli.heartbeat_beat", new_callable=AsyncMock),
            patch("cli.heartbeat_remove", new_callable=AsyncMock),
            patch("cli.asyncio.sleep", new_callable=AsyncMock),
        ):
            await cmd_trickle_worker(args)

        assert tick.await_count == 2


class TestNewDomainCommands:
    @pytest.mark.asyncio
    async def test_cmd_enqueue_domain_jobs(self):
        args = SimpleNamespace(priority=70, batch_size=100, cursor_id=0)
        with (
            patch("cli.create_pool", AsyncMock(return_value=object())),
            patch("cli.close_pool", new_callable=AsyncMock),
            patch("cli.enqueue_jobs_from_verified_domains", AsyncMock(return_value=(5, 40))),
        ):
            await cmd_enqueue_domain_jobs(args)

    @pytest.mark.asyncio
    async def test_cmd_domain_crawler_tick(self):
        args = SimpleNamespace(
            user_agent="UA", worker_id="w", batch_size=10, lease_seconds=600,
            interval=0, max_iters=2, enqueue_batch_size=50,
        )
        stats = DomainRunStats(
            jobs_claimed=3, pages_fetched=3, contacts_extracted=5,
            jobs_done=3, jobs_retried=0, jobs_blocked=0, jobs_errored=0,
            budget_skipped=0,
        )

        async def fake_enqueue(*args, **kwargs):
            urls = await kwargs["url_discoverer"]("https://x.com")
            assert urls == ["https://x.com/", "https://x.com/contato"]
            return 5, 25

        with (
            patch("cli.create_pool", AsyncMock(return_value=object())),
            patch("cli.close_pool", new_callable=AsyncMock),
            patch("cli.run_domain_batch", AsyncMock(return_value=stats)),
            patch("cli.enqueue_jobs_from_verified_domains",
                  AsyncMock(side_effect=fake_enqueue)),
            patch("cli.discover_crawl_urls",
                  AsyncMock(return_value=["https://x.com/", "https://x.com/contato"])),
            patch("cli._max_company_domain_id_seen",
                  AsyncMock(return_value=42)),
            patch("cli.heartbeat_beat", new_callable=AsyncMock),
            patch("cli.heartbeat_remove", new_callable=AsyncMock),
            patch("cli.asyncio.sleep", new_callable=AsyncMock),
        ):
            await cmd_domain_crawler(args)

    @pytest.mark.asyncio
    async def test_cmd_domain_crawler_tick_resets_cursor_when_empty(self):
        args = SimpleNamespace(
            user_agent="UA", worker_id="w", batch_size=10, lease_seconds=600,
            interval=0, max_iters=1, enqueue_batch_size=50,
        )
        stats = DomainRunStats(
            jobs_claimed=0, pages_fetched=0, contacts_extracted=0,
            jobs_done=0, jobs_retried=0, jobs_blocked=0, jobs_errored=0,
            budget_skipped=0,
        )
        with (
            patch("cli.create_pool", AsyncMock(return_value=object())),
            patch("cli.close_pool", new_callable=AsyncMock),
            patch("cli.run_domain_batch", AsyncMock(return_value=stats)),
            patch("cli.enqueue_jobs_from_verified_domains",
                  AsyncMock(return_value=(0, 0))),
            patch("cli._max_company_domain_id_seen",
                  AsyncMock(return_value=99)),
            patch("cli.heartbeat_beat", new_callable=AsyncMock),
            patch("cli.heartbeat_remove", new_callable=AsyncMock),
            patch("cli.asyncio.sleep", new_callable=AsyncMock),
        ):
            await cmd_domain_crawler(args)

    @pytest.mark.asyncio
    async def test_max_company_domain_id_seen_returns_max(self):
        from cli import _max_company_domain_id_seen

        class FakeConn:
            async def fetchrow(self, q, *args):
                return {"max_id": 1234}

        class FakeAcquire:
            async def __aenter__(self): return FakeConn()
            async def __aexit__(self, *a): return False

        class FakePool:
            def acquire(self): return FakeAcquire()

        result = await _max_company_domain_id_seen(FakePool(), after_id=10, limit=100)
        assert result == 1234

    @pytest.mark.asyncio
    async def test_max_company_domain_id_seen_returns_after_id_when_null(self):
        from cli import _max_company_domain_id_seen

        class FakeConn:
            async def fetchrow(self, q, *args):
                return {"max_id": None}

        class FakeAcquire:
            async def __aenter__(self): return FakeConn()
            async def __aexit__(self, *a): return False

        class FakePool:
            def acquire(self): return FakeAcquire()

        result = await _max_company_domain_id_seen(FakePool(), after_id=77, limit=100)
        assert result == 77

    @pytest.mark.asyncio
    async def test_cmd_resolve_domain_tick(self):
        args = SimpleNamespace(
            worker_id="rw", batch_size=500, cursor_id=0, interval=0, max_iters=2,
        )
        stats = ResolveStats(
            domains_processed=2, contacts_published=10,
            contacts_suppressed=1, contacts_below_threshold=3,
        )
        with (
            patch("cli.create_pool", AsyncMock(return_value=object())),
            patch("cli.close_pool", new_callable=AsyncMock),
            patch("cli.resolve_domain_contacts", AsyncMock(return_value=stats)),
            patch("cli.heartbeat_beat", new_callable=AsyncMock),
            patch("cli.heartbeat_remove", new_callable=AsyncMock),
            patch("cli.asyncio.sleep", new_callable=AsyncMock),
        ):
            await cmd_resolve_domain(args)

    @pytest.mark.asyncio
    async def test_cmd_resolve_domain_tick_defaults_worker_id(self):
        args = SimpleNamespace(batch_size=500, cursor_id=0, interval=0, max_iters=1)
        stats = ResolveStats(
            domains_processed=0, contacts_published=0,
            contacts_suppressed=0, contacts_below_threshold=0,
        )
        with (
            patch("cli.create_pool", AsyncMock(return_value=object())),
            patch("cli.close_pool", new_callable=AsyncMock),
            patch("cli.resolve_domain_contacts", AsyncMock(return_value=stats)),
            patch("cli.heartbeat_beat", new_callable=AsyncMock) as hb,
            patch("cli.heartbeat_remove", new_callable=AsyncMock),
            patch("cli.asyncio.sleep", new_callable=AsyncMock),
            patch("cli.default_worker_id", return_value="auto-id"),
        ):
            await cmd_resolve_domain(args)
        assert hb.await_args.kwargs["worker_id"] == "auto-id"

    def test_parser_enqueue_domain_jobs(self):
        args = build_parser().parse_args(["enqueue-domain-jobs", "--batch-size", "500"])
        assert args.command == "enqueue-domain-jobs"
        assert args.batch_size == 500

    def test_parser_domain_crawler_tick(self):
        args = build_parser().parse_args(["domain-crawler-tick", "--batch-size", "10"])
        assert args.command == "domain-crawler-tick"
        assert args.batch_size == 10
        assert args.interval == DEFAULT_INTERVAL_SECONDS
        assert args.max_iters == 0

    def test_parser_resolve_domain_tick(self):
        args = build_parser().parse_args(["resolve-domain-tick", "--cursor-id", "100"])
        assert args.command == "resolve-domain-tick"
        assert args.cursor_id == 100
        assert args.interval == DEFAULT_INTERVAL_SECONDS
        assert args.max_iters == 0
        assert hasattr(args, "worker_id")

    def test_parser_domain_crawler_tick_enqueue_batch(self):
        args = build_parser().parse_args(
            ["domain-crawler-tick", "--enqueue-batch-size", "500"]
        )
        assert args.enqueue_batch_size == 500


class TestPlaywrightCommands:
    @pytest.mark.asyncio
    async def test_cmd_enqueue_playwright_jobs(self):
        args = SimpleNamespace(batch_size=100)
        with (
            patch("cli.create_pool", AsyncMock(return_value=object())),
            patch("cli.close_pool", new_callable=AsyncMock),
            patch(
                "cli.enqueue_playwright_jobs_for_zero_contact_domains",
                AsyncMock(return_value=(3, 9)),
            ),
        ):
            await cmd_enqueue_playwright_jobs(args)

    @pytest.mark.asyncio
    async def test_cmd_playwright_crawler_tick(self):
        import sys
        from unittest.mock import MagicMock
        from crawler.playwright_runner import PlaywrightRunStats

        args = SimpleNamespace(
            worker_id="w", batch_size=5, lease_seconds=600, user_agent="UA"
        )
        stats = PlaywrightRunStats(jobs_claimed=2, jobs_done=2)

        mock_browser = AsyncMock()
        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_playwright_ctx = AsyncMock()
        mock_playwright_ctx.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_playwright_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_api_module = MagicMock()
        mock_api_module.async_playwright = MagicMock(return_value=mock_playwright_ctx)

        with (
            patch("cli.create_pool", AsyncMock(return_value=object())),
            patch("cli.close_pool", new_callable=AsyncMock),
            patch("cli.run_playwright_batch", AsyncMock(return_value=stats)),
            patch.dict(
                sys.modules,
                {"playwright": MagicMock(), "playwright.async_api": mock_api_module},
            ),
        ):
            await cmd_playwright_crawler(args)

    def test_parser_enqueue_playwright_jobs(self):
        args = build_parser().parse_args(["enqueue-playwright-jobs", "--batch-size", "50"])
        assert args.command == "enqueue-playwright-jobs"
        assert args.batch_size == 50

    def test_parser_playwright_crawler_tick(self):
        args = build_parser().parse_args(["playwright-crawler-tick", "--batch-size", "3"])
        assert args.command == "playwright-crawler-tick"
        assert args.batch_size == 3


class TestMainEntrypoint:
    def test_main_dispatches_to_subcommand(self, monkeypatch):
        called = {}

        async def fake_func(args):
            called["args"] = args

        monkeypatch.setattr(cli, "cmd_seed", fake_func)

        # rebuild the parser so the new fake_func is used
        def patched_build():
            parser = build_parser.__wrapped__() if hasattr(build_parser, "__wrapped__") else build_parser()
            return parser

        # easier: invoke main() with seed-targets and patch cmd_seed via monkeypatch
        rc = main(["seed-targets", "--reason", "r", "--priority", "10", "--batch-size", "5"])
        assert rc == 0
        assert called["args"].reason == "r"
        assert called["args"].priority == 10
        assert called["args"].batch_size == 5


class TestPhaseSeedFunctions:
    @pytest.mark.asyncio
    async def test_do_seed_phase1_calls_seed_phase1_targets(self):
        pool = object()
        with patch("cli.seed_phase1_targets", new_callable=AsyncMock, return_value=50000) as m:
            result = await do_seed_phase1(pool, batch_size=50000)
        assert result == 50000
        m.assert_awaited_once_with(pool, batch_size=50000)

    @pytest.mark.asyncio
    async def test_do_seed_phase2_calls_seed_phase2_targets(self):
        pool = object()
        with patch("cli.seed_phase2_targets", new_callable=AsyncMock, return_value=10000) as m:
            result = await do_seed_phase2(pool, batch_size=10000)
        assert result == 10000
        m.assert_awaited_once_with(pool, batch_size=10000)


class TestPhaseAwareDiscovery:
    @pytest.mark.asyncio
    async def test_do_discovery_phase1_passes_dns_only_true(self):
        """Phase 1: dns_only=True must reach discover_target."""
        targets = [
            ClaimedTarget(id=1, cnpj_basico="12345678", cnpj_ordem="0001", cnpj_dv="90",
                          reason="phase1_dns", attempts=1, priority=60),
        ]
        received_kwargs = {}

        async def discover_side_effect(pool, *, cnpj_basico, cnpj_ordem, cnpj_dv, client,
                                       external_search=None, dns_only=False):
            received_kwargs["dns_only"] = dns_only
            received_kwargs["external_search"] = external_search
            return DiscoveryOutcome(cnpj="x", domains_seen=0, crawl_requests_created=0)

        with (
            patch("cli.claim_targets", new_callable=AsyncMock, return_value=targets),
            patch("cli.discover_target", AsyncMock(side_effect=discover_side_effect)),
            patch("cli.complete_target", new_callable=AsyncMock),
        ):
            async with _stub_client() as client:
                await do_discovery(
                    object(), client=client, worker_id="w",
                    batch_size=10, lease_seconds=300,
                    dns_only=True, external_search=None,
                )

        assert received_kwargs["dns_only"] is True
        assert received_kwargs["external_search"] is None

    @pytest.mark.asyncio
    async def test_do_discovery_phase2_passes_dns_only_false(self):
        """Phase 2: dns_only=False and external_search is forwarded."""
        targets = [
            ClaimedTarget(id=1, cnpj_basico="12345678", cnpj_ordem="0001", cnpj_dv="90",
                          reason="phase2_search", attempts=1, priority=50),
        ]
        received_kwargs = {}

        class FakeSearch:
            pass

        async def discover_side_effect(pool, *, cnpj_basico, cnpj_ordem, cnpj_dv, client,
                                       external_search=None, dns_only=False):
            received_kwargs["dns_only"] = dns_only
            received_kwargs["external_search"] = external_search
            return DiscoveryOutcome(cnpj="x", domains_seen=0, crawl_requests_created=0)

        fake_search = FakeSearch()
        with (
            patch("cli.claim_targets", new_callable=AsyncMock, return_value=targets),
            patch("cli.discover_target", AsyncMock(side_effect=discover_side_effect)),
            patch("cli.complete_target", new_callable=AsyncMock),
        ):
            async with _stub_client() as client:
                await do_discovery(
                    object(), client=client, worker_id="w",
                    batch_size=10, lease_seconds=300,
                    dns_only=False, external_search=fake_search,
                )

        assert received_kwargs["dns_only"] is False
        assert received_kwargs["external_search"] is fake_search


class TestPhaseAwareWorkerLoop:
    @pytest.mark.asyncio
    async def test_do_one_loop_phase1_uses_seed_phase1_and_dns_only(self):
        import types
        args = types.SimpleNamespace(
            phase=1,
            seed_batch_size=50000,
            worker_id="w",
            discovery_batch_size=500,
            lease_seconds=600,
            crawl_batch_size=20,
            user_agent="UA",
        )
        with (
            patch("cli.do_seed_phase1", new_callable=AsyncMock, return_value=50000),
            patch("cli.do_discovery", new_callable=AsyncMock, return_value=(500, 0)) as disc,
            patch("cli.do_crawler", new_callable=AsyncMock, return_value=(0, 0)),
            patch("cli.do_release_stale", new_callable=AsyncMock, return_value=0),
        ):
            async with _stub_client() as client:
                stats = await do_one_loop(object(), client, args)

        disc_call = disc.await_args
        assert disc_call.kwargs["dns_only"] is True
        assert disc_call.kwargs["reason"] == "phase1_dns"
        assert disc_call.kwargs["external_search"] is None

    @pytest.mark.asyncio
    async def test_do_one_loop_phase2_uses_seed_phase2_and_external_search(self):
        import types
        args = types.SimpleNamespace(
            phase=2,
            seed_batch_size=10000,
            worker_id="w",
            discovery_batch_size=50,
            lease_seconds=600,
            crawl_batch_size=20,
            user_agent="UA",
        )
        with (
            patch("cli.do_seed_phase2", new_callable=AsyncMock, return_value=10000),
            patch("cli.do_discovery", new_callable=AsyncMock, return_value=(50, 0)) as disc,
            patch("cli.do_crawler", new_callable=AsyncMock, return_value=(0, 0)),
            patch("cli.do_release_stale", new_callable=AsyncMock, return_value=0),
            patch("cli._build_external_search", return_value=object()),
        ):
            async with _stub_client() as client:
                stats = await do_one_loop(object(), client, args)

        disc_call = disc.await_args
        assert disc_call.kwargs["dns_only"] is False
        assert disc_call.kwargs["reason"] == "phase2_search"


class TestNewPhaseCommands:
    def test_parser_seed_phase1(self):
        args = build_parser().parse_args(["seed-phase1", "--batch-size", "50000"])
        assert args.command == "seed-phase1"
        assert args.batch_size == 50000

    def test_parser_seed_phase2(self):
        args = build_parser().parse_args(["seed-phase2", "--batch-size", "10000"])
        assert args.command == "seed-phase2"
        assert args.batch_size == 10000

    def test_parser_worker_phase_flag(self):
        args = build_parser().parse_args(["worker", "--phase", "1", "--max-iters", "1"])
        assert args.phase == 1

    def test_parser_worker_phase_default(self):
        args = build_parser().parse_args(["worker", "--max-iters", "1"])
        assert args.phase == 0

    def test_parser_demand_worker(self):
        args = build_parser().parse_args(["demand-worker", "--batch-size", "7"])
        assert args.command == "demand-worker"
        assert args.batch_size == 7
        assert args.concurrency == 2

    def test_parser_trickle_worker(self):
        args = build_parser().parse_args(["trickle-worker", "--interval", "60"])
        assert args.command == "trickle-worker"
        assert args.interval == 60
        assert args.priority == 10

    @pytest.mark.asyncio
    async def test_cmd_seed_phase1_runs(self):
        args = SimpleNamespace(batch_size=50000)
        with (
            patch("cli.create_pool", AsyncMock(return_value=object())),
            patch("cli.close_pool", new_callable=AsyncMock),
            patch("cli.do_seed_phase1", AsyncMock(return_value=50000)),
        ):
            await cmd_seed_phase1(args)

    @pytest.mark.asyncio
    async def test_cmd_seed_phase2_runs(self):
        args = SimpleNamespace(batch_size=10000)
        with (
            patch("cli.create_pool", AsyncMock(return_value=object())),
            patch("cli.close_pool", new_callable=AsyncMock),
            patch("cli.do_seed_phase2", AsyncMock(return_value=10000)),
        ):
            await cmd_seed_phase2(args)


class TestRateLimitHandling:
    @pytest.mark.asyncio
    async def test_rate_limit_marks_target_retry_with_correct_delay(self):
        """SearchRateLimitError marks target as retry with provider's retry_after."""
        target = ClaimedTarget(
            id=99, cnpj_basico="12345678", cnpj_ordem="0001", cnpj_dv="90",
            reason="phase2_search", attempts=1, priority=50,
        )

        async def discover_side_effect(pool, *, cnpj_basico, **kwargs):
            raise SearchRateLimitError("brave", retry_after=900)

        with (
            patch("cli.claim_targets", AsyncMock(return_value=[target])),
            patch("cli.discover_target", AsyncMock(side_effect=discover_side_effect)),
            patch("cli.complete_target", new_callable=AsyncMock) as complete,
        ):
            # Reset global backoff state before test
            cli._source_backoffs.clear()
            async with _stub_client() as client:
                claimed, created = await do_discovery(
                    object(), client=client, worker_id="w",
                    batch_size=10, lease_seconds=300,
                )

        assert claimed == 1
        assert created == 0
        retry_call = complete.await_args_list[0]
        assert retry_call.kwargs["status"] == "retry"
        assert retry_call.kwargs["retry_in_seconds"] == 900
        assert "brave" in retry_call.kwargs["last_error"]

    @pytest.mark.asyncio
    async def test_rate_limit_sets_source_backoff(self):
        """After SearchRateLimitError, the source is added to _source_backoffs."""
        target = ClaimedTarget(
            id=99, cnpj_basico="12345678", cnpj_ordem="0001", cnpj_dv="90",
            reason="phase2_search", attempts=1, priority=50,
        )

        async def discover_side_effect(pool, *, cnpj_basico, cnpj_ordem, cnpj_dv, client, external_search=None, dns_only=False):
            raise SearchRateLimitError("google_cse", retry_after=3600)

        with (
            patch("cli.claim_targets", AsyncMock(return_value=[target])),
            patch("cli.discover_target", AsyncMock(side_effect=discover_side_effect)),
            patch("cli.complete_target", new_callable=AsyncMock),
        ):
            cli._source_backoffs.clear()
            before = time.time()
            async with _stub_client() as client:
                await do_discovery(
                    object(), client=client, worker_id="w",
                    batch_size=10, lease_seconds=300,
                )

        assert "google_cse" in cli._source_backoffs
        assert cli._source_backoffs["google_cse"] >= before + 3600

    @pytest.mark.asyncio
    async def test_blocked_sources_passed_to_external_search(self):
        """_build_external_search passes currently-backed-off sources as blocked."""
        cli._source_backoffs.clear()
        cli._source_backoffs["brave"] = time.time() + 9999

        es = cli._build_external_search()
        assert "brave" in es.blocked_sources

        cli._source_backoffs.clear()

    @pytest.mark.asyncio
    async def test_expired_backoffs_not_blocked(self):
        """Sources whose backoff has passed are not in blocked_sources."""
        cli._source_backoffs.clear()
        cli._source_backoffs["brave"] = time.time() - 1  # already expired

        es = cli._build_external_search()
        assert "brave" not in es.blocked_sources

        cli._source_backoffs.clear()
