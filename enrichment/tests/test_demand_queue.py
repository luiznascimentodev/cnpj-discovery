from unittest.mock import AsyncMock

import pytest

from demand_queue import (
    DemandItem,
    claim_demand_items,
    complete_demand_item,
    count_published_contacts,
    has_pending_demand,
    release_stale_demand_items,
)


class FakeTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return FakeAcquire(self.conn)


def _row(**overrides):
    row = {
        "id": 1,
        "job_id": 2,
        "account_id": "acct",
        "cnpj_basico": "12345678",
        "cnpj_ordem": "0001",
        "cnpj_dv": "90",
        "attempts": 1,
        "priority": 1000,
    }
    row.update(overrides)
    return row


class TestDemandQueue:
    @pytest.mark.asyncio
    async def test_has_pending_demand(self):
        conn = AsyncMock()
        conn.fetchval.return_value = True
        assert await has_pending_demand(FakePool(conn)) is True

    @pytest.mark.asyncio
    async def test_claim_demand_items_maps_rows(self):
        conn = AsyncMock()
        conn.fetch.return_value = [_row()]

        items = await claim_demand_items(
            FakePool(conn),
            worker_id="w",
            batch_size=10,
            lease_seconds=600,
        )

        assert items == [
            DemandItem(
                id=1,
                job_id=2,
                account_id="acct",
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                attempts=1,
                priority=1000,
            )
        ]
        assert items[0].cnpj == "12345678000190"

    @pytest.mark.asyncio
    async def test_claim_validates_inputs(self):
        with pytest.raises(ValueError):
            await claim_demand_items(FakePool(AsyncMock()), worker_id="", batch_size=1, lease_seconds=1)
        with pytest.raises(ValueError):
            await claim_demand_items(FakePool(AsyncMock()), worker_id="w", batch_size=0, lease_seconds=1)

    @pytest.mark.asyncio
    async def test_complete_item_refreshes_counters(self):
        conn = AsyncMock()
        conn.transaction = lambda: FakeTx()
        conn.fetchrow.return_value = {"job_id": 9}

        await complete_demand_item(
            FakePool(conn),
            item_id=1,
            status="enriched",
            result_source="fresh_crawl",
        )

        conn.fetchrow.assert_awaited_once()
        conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_complete_item_rejects_invalid_status(self):
        with pytest.raises(ValueError):
            await complete_demand_item(FakePool(AsyncMock()), item_id=1, status="bad")

    @pytest.mark.asyncio
    async def test_complete_item_handles_missing_row(self):
        conn = AsyncMock()
        conn.transaction = lambda: FakeTx()
        conn.fetchrow.return_value = None

        await complete_demand_item(FakePool(conn), item_id=1, status="failed_retryable")

        conn.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_release_stale_demand_items_counts_rows(self):
        conn = AsyncMock()
        conn.fetch.return_value = [{"id": 1}, {"id": 2}]
        assert await release_stale_demand_items(FakePool(conn)) == 2

    @pytest.mark.asyncio
    async def test_count_published_contacts(self):
        conn = AsyncMock()
        conn.fetchval.return_value = 3
        item = DemandItem(1, 2, "acct", "12345678", "0001", "90", 1, 1000)

        assert await count_published_contacts(FakePool(conn), item) == 3
