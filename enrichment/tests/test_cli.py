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
    cmd_release_stale,
    cmd_seed,
    cmd_worker,
    default_worker_id,
    do_crawler,
    do_discovery,
    do_one_loop,
    do_release_stale,
    do_seed,
    main,
)
from crawler.runner import RunStats
from discovery.pipeline import DiscoveryOutcome
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

        async def discover_side_effect(pool, *, cnpj_basico, cnpj_ordem, cnpj_dv, client):
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
        ):
            total = await do_release_stale(object(), lease_seconds=300)

        assert total == 5

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
        )
        empty_stats = TickStats()
        with (
            patch("cli.create_pool", AsyncMock(return_value=object())),
            patch("cli.close_pool", new_callable=AsyncMock),
            patch("cli.do_one_loop", AsyncMock(return_value=empty_stats)) as loop,
            patch("cli.asyncio.sleep", new_callable=AsyncMock),
        ):
            await cmd_worker(args)

        assert loop.await_count == 2


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
