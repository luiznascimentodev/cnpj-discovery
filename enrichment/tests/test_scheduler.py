import pytest

from scheduler import (
    ClaimedTarget,
    CursorState,
    DEFAULT_CLAIM_BATCH,
    DEFAULT_LEASE_SECONDS,
    DEFAULT_SEED_BATCH,
    claim_targets,
    complete_target,
    get_cursor,
    release_stale_locks,
    seed_active_targets,
    seed_phase1_targets,
    seed_phase2_targets,
)


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeTransaction:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        self.conn.transaction_open = True
        return self.conn

    async def __aexit__(self, exc_type, exc, traceback):
        self.conn.transaction_open = False
        return False


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return FakeAcquire(self.conn)


class FakeConnection:
    def __init__(self, *, fetchrow_results=None, fetch_results=None):
        self._fetchrow_results = list(fetchrow_results or [])
        self._fetch_results = list(fetch_results or [])
        self.fetchrow_calls = []
        self.fetch_calls = []
        self.execute_calls = []
        self.executemany_calls = []
        self.transaction_open = False

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        return self._fetchrow_results.pop(0) if self._fetchrow_results else None

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return self._fetch_results.pop(0) if self._fetch_results else []

    async def execute(self, query, *args):
        self.execute_calls.append((query, args, self.transaction_open))
        return "OK"

    async def executemany(self, query, args_list):
        self.executemany_calls.append((query, list(args_list), self.transaction_open))

    def transaction(self):
        return FakeTransaction(self)


class TestGetCursor:
    @pytest.mark.asyncio
    async def test_returns_default_state_when_cursor_missing(self):
        conn = FakeConnection(fetchrow_results=[None])

        cursor = await get_cursor(FakePool(conn), "missing_contacts")

        assert cursor == CursorState("00000000", "0000", "00", 0)

    @pytest.mark.asyncio
    async def test_returns_persisted_state_when_cursor_exists(self):
        conn = FakeConnection(
            fetchrow_results=[
                {
                    "last_cnpj_basico": "12345678",
                    "last_cnpj_ordem": "0001",
                    "last_cnpj_dv": "90",
                    "rows_seeded": 250,
                }
            ]
        )

        cursor = await get_cursor(FakePool(conn), "missing_contacts")

        assert cursor.last_cnpj_basico == "12345678"
        assert cursor.rows_seeded == 250


class TestSeedActiveTargets:
    @pytest.mark.asyncio
    async def test_rejects_invalid_batch_size(self):
        with pytest.raises(ValueError, match="batch_size"):
            await seed_active_targets(FakePool(FakeConnection()), batch_size=0)

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_new_rows(self):
        conn = FakeConnection(fetchrow_results=[None], fetch_results=[[]])

        rows_seen = await seed_active_targets(FakePool(conn))

        assert rows_seen == 0
        assert conn.executemany_calls == []

    @pytest.mark.asyncio
    async def test_uses_default_cursor_when_missing_and_persists_progress(self):
        conn = FakeConnection(
            fetchrow_results=[None],
            fetch_results=[
                [
                    {"cnpj_basico": "00000001", "cnpj_ordem": "0001", "cnpj_dv": "10"},
                    {"cnpj_basico": "00000002", "cnpj_ordem": "0001", "cnpj_dv": "20"},
                ]
            ],
        )

        rows_seen = await seed_active_targets(
            FakePool(conn),
            reason="missing_contacts",
            priority=70,
            batch_size=200,
        )

        assert rows_seen == 2
        select_args = conn.fetch_calls[0][1]
        assert select_args == ("00000000", "0000", "00", 200)

        executemany_query, payload, transactional = conn.executemany_calls[0]
        assert "INSERT INTO paid_enrichment.enrichment_targets" in executemany_query
        assert transactional is True
        assert payload[0] == ("00000001", "0001", "10", 70, "missing_contacts")
        assert payload[1] == ("00000002", "0001", "20", 70, "missing_contacts")

        cursor_query, cursor_args, cursor_transactional = conn.execute_calls[0]
        assert "enrichment_seed_cursor" in cursor_query
        assert cursor_args == ("missing_contacts", "00000002", "0001", "20", 2)
        assert cursor_transactional is True

    @pytest.mark.asyncio
    async def test_resumes_from_existing_cursor(self):
        conn = FakeConnection(
            fetchrow_results=[
                {
                    "last_cnpj_basico": "12345678",
                    "last_cnpj_ordem": "0001",
                    "last_cnpj_dv": "90",
                    "rows_seeded": 100,
                }
            ],
            fetch_results=[
                [
                    {"cnpj_basico": "12345678", "cnpj_ordem": "0002", "cnpj_dv": "00"},
                ]
            ],
        )

        rows_seen = await seed_active_targets(FakePool(conn), batch_size=10)

        assert rows_seen == 1
        select_args = conn.fetch_calls[0][1]
        assert select_args == ("12345678", "0001", "90", 10)


class TestClaimTargets:
    @pytest.mark.asyncio
    async def test_rejects_empty_worker_id(self):
        with pytest.raises(ValueError, match="worker_id"):
            await claim_targets(FakePool(FakeConnection()), worker_id="")

    @pytest.mark.asyncio
    async def test_rejects_invalid_batch_size(self):
        with pytest.raises(ValueError, match="batch_size"):
            await claim_targets(FakePool(FakeConnection()), worker_id="w", batch_size=0)

    @pytest.mark.asyncio
    async def test_maps_rows_to_claimed_targets(self):
        conn = FakeConnection(
            fetch_results=[
                [
                    {
                        "id": 1,
                        "cnpj_basico": "12345678",
                        "cnpj_ordem": "0001",
                        "cnpj_dv": "90",
                        "reason": "missing_contacts",
                        "attempts": 1,
                        "priority": 50,
                    }
                ]
            ]
        )

        targets = await claim_targets(
            FakePool(conn),
            worker_id="worker-1",
            batch_size=20,
            lease_seconds=120,
        )

        assert targets == [
            ClaimedTarget(
                id=1,
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                reason="missing_contacts",
                attempts=1,
                priority=50,
            )
        ]
        assert conn.fetch_calls[0][1] == ("worker-1", 120, 20, None)

    @pytest.mark.asyncio
    async def test_uses_default_lease_and_batch_when_omitted(self):
        conn = FakeConnection(fetch_results=[[]])

        targets = await claim_targets(FakePool(conn), worker_id="worker-1")

        assert targets == []
        assert conn.fetch_calls[0][1] == ("worker-1", DEFAULT_LEASE_SECONDS, DEFAULT_CLAIM_BATCH, None)


class TestCompleteTarget:
    @pytest.mark.asyncio
    async def test_rejects_invalid_status(self):
        with pytest.raises(ValueError, match="Invalid target status"):
            await complete_target(FakePool(FakeConnection()), target_id=1, status="bogus")

    @pytest.mark.asyncio
    async def test_writes_status_with_clamped_retry_delay(self):
        conn = FakeConnection()

        await complete_target(
            FakePool(conn),
            target_id=42,
            status="retry",
            retry_in_seconds=-30,
            last_error="timeout",
        )

        query, args, _ = conn.execute_calls[0]
        assert "UPDATE paid_enrichment.enrichment_targets" in query
        assert args == (42, "retry", 0, "timeout")

    @pytest.mark.asyncio
    async def test_done_status_uses_zero_delay_by_default(self):
        conn = FakeConnection()

        await complete_target(FakePool(conn), target_id=42, status="done")

        _, args, _ = conn.execute_calls[0]
        assert args == (42, "done", 0, None)


class TestReleaseStaleLocks:
    @pytest.mark.asyncio
    async def test_returns_number_of_released_rows(self):
        conn = FakeConnection(fetch_results=[[{"id": 1}, {"id": 2}, {"id": 3}]])

        released = await release_stale_locks(FakePool(conn), lease_seconds=600)

        assert released == 3
        assert conn.fetch_calls[0][1] == (600,)


class TestModuleConstants:
    def test_default_seed_batch_is_positive(self):
        assert DEFAULT_SEED_BATCH > 0


class TestSeedPhase1:
    @pytest.mark.asyncio
    async def test_seeds_all_active_companies_no_email_filter(self):
        """Phase 1 seeds ALL active companies — no missing-email/phone filter."""
        rows_inserted = []

        class FakeConn:
            async def fetchrow(self, q, *a):
                return None  # no cursor yet
            async def fetch(self, q, *a):
                return [
                    {"cnpj_basico": "00000001", "cnpj_ordem": "0001", "cnpj_dv": "10"},
                    {"cnpj_basico": "00000002", "cnpj_ordem": "0001", "cnpj_dv": "20"},
                ]
            async def executemany(self, q, records):
                rows_inserted.extend(records)
            async def execute(self, q, *a):
                pass
            def transaction(self):
                return _FakeTx()

        class _FakeTx:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass

        class FakePool:
            def acquire(self): return _Ctx(FakeConn())

        class _Ctx:
            def __init__(self, c): self._c = c
            async def __aenter__(self): return self._c
            async def __aexit__(self, *a): pass

        n = await seed_phase1_targets(FakePool(), batch_size=100)
        assert n == 2
        reasons = [r[4] for r in rows_inserted]
        assert all(r == "phase1_dns" for r in reasons)

    @pytest.mark.asyncio
    async def test_phase1_sql_has_no_email_phone_condition(self):
        """_SQL_SELECT_PHASE1 must not contain email/telefone filter."""
        from scheduler import _SQL_SELECT_PHASE1
        assert "email" not in _SQL_SELECT_PHASE1.lower()
        assert "telefone" not in _SQL_SELECT_PHASE1.lower()

    @pytest.mark.asyncio
    async def test_phase2_sql_filters_companies_without_domain(self):
        """_SQL_SELECT_PHASE2 must reference company_domains with status filter."""
        from scheduler import _SQL_SELECT_PHASE2
        assert "company_domains" in _SQL_SELECT_PHASE2.lower()
        assert "verified" in _SQL_SELECT_PHASE2.lower()
        assert "candidate" in _SQL_SELECT_PHASE2.lower()
        assert "not exists" in _SQL_SELECT_PHASE2.lower()

    @pytest.mark.asyncio
    async def test_seed_phase2_uses_phase2_reason(self):
        """seed_phase2_targets seeds with reason='phase2_search'."""
        rows_inserted = []

        class FakeConn:
            async def fetchrow(self, q, *a):
                return None
            async def fetch(self, q, *a):
                return [
                    {"cnpj_basico": "00000003", "cnpj_ordem": "0001", "cnpj_dv": "30"},
                ]
            async def executemany(self, q, records):
                rows_inserted.extend(records)
            async def execute(self, q, *a):
                pass
            def transaction(self):
                return _FakeTx2()

        class _FakeTx2:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass

        class FakePool:
            def acquire(self): return _Ctx(FakeConn())

        class _Ctx:
            def __init__(self, c): self._c = c
            async def __aenter__(self): return self._c
            async def __aexit__(self, *a): pass

        n = await seed_phase2_targets(FakePool(), batch_size=100)
        assert n == 1
        assert rows_inserted[0][4] == "phase2_search"


class TestClaimTargetsReasonFilter:
    @pytest.mark.asyncio
    async def test_claim_with_reason_passes_reason_to_sql(self):
        """claim_targets(reason='phase1_dns') only claims matching targets."""
        fetched_args = []

        class FakeConn:
            async def fetch(self, q, *a):
                fetched_args.extend(a)
                return []

        class FakePool:
            def acquire(self): return _Ctx(FakeConn())

        class _Ctx:
            def __init__(self, c): self._c = c
            async def __aenter__(self): return self._c
            async def __aexit__(self, *a): pass

        await claim_targets(FakePool(), worker_id="w", batch_size=10, lease_seconds=60, reason="phase1_dns")
        assert "phase1_dns" in fetched_args

    @pytest.mark.asyncio
    async def test_claim_without_reason_passes_none(self):
        """claim_targets() without reason passes None (claims any target)."""
        fetched_args = []

        class FakeConn:
            async def fetch(self, q, *a):
                fetched_args.extend(a)
                return []

        class FakePool:
            def acquire(self): return _Ctx(FakeConn())

        class _Ctx:
            def __init__(self, c): self._c = c
            async def __aenter__(self): return self._c
            async def __aexit__(self, *a): pass

        await claim_targets(FakePool(), worker_id="w", batch_size=10, lease_seconds=60)
        assert None in fetched_args
