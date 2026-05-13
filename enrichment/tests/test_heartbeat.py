import pytest

from heartbeat import beat, remove


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_):
        return False


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return FakeAcquire(self.conn)


class FakeConnection:
    def __init__(self):
        self.execute_calls = []

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


class TestBeat:
    @pytest.mark.asyncio
    async def test_executes_upsert(self):
        conn = FakeConnection()
        await beat(FakePool(conn), worker_id="w1", role="domain-crawler")
        assert len(conn.execute_calls) == 1
        _, args = conn.execute_calls[0]
        assert args[0] == "w1"
        assert args[1] == "domain-crawler"

    @pytest.mark.asyncio
    async def test_passes_stage_and_job(self):
        conn = FakeConnection()
        await beat(
            FakePool(conn),
            worker_id="w1",
            role="domain-crawler",
            current_stage="fetching",
            current_job_id=42,
        )
        _, args = conn.execute_calls[0]
        assert args[4] == "fetching"
        assert args[5] == 42

    @pytest.mark.asyncio
    async def test_metadata_serialized_as_json(self):
        conn = FakeConnection()
        await beat(
            FakePool(conn),
            worker_id="w1",
            role="resolver",
            metadata={"batch": 10},
        )
        _, args = conn.execute_calls[0]
        import json
        assert json.loads(args[6]) == {"batch": 10}


class TestRemove:
    @pytest.mark.asyncio
    async def test_executes_delete(self):
        conn = FakeConnection()
        await remove(FakePool(conn), worker_id="w1")
        assert len(conn.execute_calls) == 1
        _, args = conn.execute_calls[0]
        assert args[0] == "w1"
