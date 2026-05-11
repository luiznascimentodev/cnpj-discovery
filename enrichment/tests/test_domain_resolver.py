from unittest.mock import AsyncMock, patch

import pytest

from resolver.domain_resolver import (
    PUBLISH_THRESHOLD,
    SHARED_DOMAIN_MAX_CNPJS,
    ResolveStats,
    _resolve_domain,
    resolve_domain_contacts,
)


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
    def __init__(self, *, fetchval_results=None, fetch_results=None):
        self._fetchval = list(fetchval_results or [])
        self._fetch = list(fetch_results or [])
        self.execute_calls = []
        self.fetchval_calls = []
        self.fetch_calls = []

    async def fetchval(self, query, *args):
        self.fetchval_calls.append((query, args))
        return self._fetchval.pop(0) if self._fetchval else None

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return self._fetch.pop(0) if self._fetch else []

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


class TestResolveDomain:
    @pytest.mark.asyncio
    async def test_shared_domain_skips(self):
        conn = FakeConnection(
            fetchval_results=[SHARED_DOMAIN_MAX_CNPJS + 1],
        )
        pub, supp, below, shared = await _resolve_domain(
            conn, "shared.com.br", publish_threshold=PUBLISH_THRESHOLD
        )
        assert shared == 1
        assert pub == 0

    @pytest.mark.asyncio
    async def test_no_cnpjs_returns_zeros(self):
        conn = FakeConnection(
            fetchval_results=[0],
            fetch_results=[[]],
        )
        result = await _resolve_domain(
            conn, "nobody.com.br", publish_threshold=PUBLISH_THRESHOLD
        )
        assert result == (0, 0, 0, 0)

    @pytest.mark.asyncio
    async def test_no_candidates_returns_zeros(self):
        conn = FakeConnection(
            fetchval_results=[1],
            fetch_results=[
                [{"cnpj_basico": "11111111", "cnpj_ordem": "0001", "cnpj_dv": "00"}],
                [],
            ],
        )
        result = await _resolve_domain(
            conn, "acme.com.br", publish_threshold=PUBLISH_THRESHOLD
        )
        assert result == (0, 0, 0, 0)

    @pytest.mark.asyncio
    async def test_publishes_high_confidence_contact(self):
        conn = FakeConnection(
            fetchval_results=[
                1,   # cnpj count
                None,  # no suppression
            ],
            fetch_results=[
                [{"cnpj_basico": "11111111", "cnpj_ordem": "0001", "cnpj_dv": "00"}],
                [
                    {
                        "id": 10,
                        "contact_type": "email",
                        "raw_value": "contact@acme.com.br",
                        "normalized_value": "contact@acme.com.br",
                        "label": None,
                        "context": None,
                        "confidence": 90,
                        "domain_page_id": 5,
                    }
                ],
            ],
        )
        pub, supp, below, shared = await _resolve_domain(
            conn, "acme.com.br", publish_threshold=PUBLISH_THRESHOLD
        )
        assert pub == 1
        assert supp == 0
        assert below == 0
        assert len(conn.execute_calls) == 1

    @pytest.mark.asyncio
    async def test_skips_below_threshold(self):
        conn = FakeConnection(
            fetchval_results=[1],
            fetch_results=[
                [{"cnpj_basico": "11111111", "cnpj_ordem": "0001", "cnpj_dv": "00"}],
                [
                    {
                        "id": 10,
                        "contact_type": "email",
                        "raw_value": "x@acme.com.br",
                        "normalized_value": "x@acme.com.br",
                        "label": None,
                        "context": None,
                        "confidence": PUBLISH_THRESHOLD - 1,
                        "domain_page_id": 5,
                    }
                ],
            ],
        )
        pub, supp, below, shared = await _resolve_domain(
            conn, "acme.com.br", publish_threshold=PUBLISH_THRESHOLD
        )
        assert pub == 0
        assert below == 1
        assert len(conn.execute_calls) == 0

    @pytest.mark.asyncio
    async def test_suppressed_contact_not_published(self):
        conn = FakeConnection(
            fetchval_results=[
                1,    # cnpj count
                True, # suppressed
            ],
            fetch_results=[
                [{"cnpj_basico": "11111111", "cnpj_ordem": "0001", "cnpj_dv": "00"}],
                [
                    {
                        "id": 10,
                        "contact_type": "phone",
                        "raw_value": "11999990000",
                        "normalized_value": "11999990000",
                        "label": None,
                        "context": None,
                        "confidence": 95,
                        "domain_page_id": 5,
                    }
                ],
            ],
        )
        pub, supp, below, shared = await _resolve_domain(
            conn, "acme.com.br", publish_threshold=PUBLISH_THRESHOLD
        )
        assert pub == 0
        assert supp == 1
        assert len(conn.execute_calls) == 0


class TestResolveDomainContacts:
    @pytest.mark.asyncio
    async def test_empty_batch_returns_zero_stats(self):
        conn = FakeConnection(fetch_results=[[]])
        stats = await resolve_domain_contacts(FakePool(conn))
        assert stats == ResolveStats()

    @pytest.mark.asyncio
    async def test_aggregates_stats_across_domains(self):
        domain_rows = [
            {"domain": "alpha.com.br"},
            {"domain": "beta.com.br"},
        ]

        async def fake_resolve(conn, domain, *, publish_threshold):
            if domain == "alpha.com.br":
                return 2, 0, 0, 0
            return 0, 0, 0, 1  # shared

        conn = FakeConnection(fetch_results=[domain_rows])

        with patch("resolver.domain_resolver._resolve_domain", side_effect=fake_resolve):
            stats = await resolve_domain_contacts(FakePool(conn))

        assert stats.domains_processed == 2
        assert stats.contacts_published == 2
        assert stats.domains_shared_skipped == 1

    @pytest.mark.asyncio
    async def test_passes_cursor_and_batch_size(self):
        conn = FakeConnection(fetch_results=[[]])
        await resolve_domain_contacts(FakePool(conn), cursor_id=50, batch_size=100)
        _, args = conn.fetch_calls[0]
        assert args == (50, 100)
