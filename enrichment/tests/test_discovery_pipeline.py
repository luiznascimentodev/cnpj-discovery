import httpx
import pytest

from discovery.pipeline import (
    PRIORITY_PATHS,
    DiscoveryOutcome,
    _initial_confidence,
    _initial_status,
    process_target,
)
from discovery.website_probe import ProbeResult
from domain_discovery import DomainCandidate


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


class FakeConnection:
    def __init__(self, fetchrow_result=None):
        self._fetchrow_result = fetchrow_result
        self.execute_calls = []

    async def fetchrow(self, query, *args):
        return self._fetchrow_result

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


def _httpx_client(handler):
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        timeout=httpx.Timeout(5.0),
    )


def _ok_handler(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=b"<html>OK</html>", headers={"content-type": "text/html"})


def _parked_handler(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=b"This domain is for sale!")


def _error_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down", request=request)


class TestHelpers:
    def test_initial_status_rejected_when_parked(self):
        probe = ProbeResult("d", "https://d/", 200, "text/html", "x", parked=True)

        assert _initial_status(probe) == "rejected"

    def test_initial_status_candidate_when_ok(self):
        probe = ProbeResult("d", "https://d/", 200, "text/html", "x", parked=False)

        assert _initial_status(probe) == "candidate"

    def test_initial_confidence_clamps_parked(self):
        candidate = DomainCandidate(domain="x", source="rf_email_domain", confidence=90)
        probe = ProbeResult("x", "https://x/", 200, "text/html", "y", parked=True)

        assert _initial_confidence(candidate, probe) == 5

    def test_initial_confidence_clamps_when_not_ok(self):
        candidate = DomainCandidate(domain="x", source="brand_slug", confidence=45)
        probe = ProbeResult("x", "https://x/", 0, "", "", parked=False, error="dead")

        assert _initial_confidence(candidate, probe) == 30

    def test_initial_confidence_keeps_when_ok(self):
        candidate = DomainCandidate(domain="x", source="rf_email_domain", confidence=90)
        probe = ProbeResult("x", "https://x/", 200, "text/html", "y", parked=False)

        assert _initial_confidence(candidate, probe) == 90


class TestProcessTarget:
    @pytest.mark.asyncio
    async def test_returns_zero_when_estabelecimento_missing(self):
        conn = FakeConnection(fetchrow_result=None)

        async with _httpx_client(_ok_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="00000000",
                cnpj_ordem="0000",
                cnpj_dv="00",
                client=client,
            )

        assert outcome == DiscoveryOutcome(cnpj="00000000000000", domains_seen=0, crawl_requests_created=0)
        assert conn.execute_calls == []

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_candidates(self):
        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "AA",
                "nome_fantasia": "BB",
                "email": "contato@gmail.com",
                "uf": "SP",
                "municipio": 1,
                "cep": "00000000",
            }
        )

        async with _httpx_client(_ok_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="00000001",
                cnpj_ordem="0001",
                cnpj_dv="10",
                client=client,
            )

        assert outcome.domains_seen == 0
        assert outcome.crawl_requests_created == 0

    @pytest.mark.asyncio
    async def test_creates_crawl_requests_for_ok_domain(self):
        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "Acme LTDA",
                "nome_fantasia": "Acme",
                "email": "contato@acme.com.br",
                "uf": "SP",
                "municipio": 1,
                "cep": "00000000",
            }
        )

        async with _httpx_client(_ok_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        assert outcome.domains_seen >= 1
        assert outcome.crawl_requests_created == outcome.domains_seen * len(PRIORITY_PATHS)

        upsert_calls = [c for c in conn.execute_calls if "company_domains" in c[0]]
        crawl_calls = [c for c in conn.execute_calls if "crawl_requests" in c[0]]
        assert len(upsert_calls) == outcome.domains_seen
        assert len(crawl_calls) == outcome.crawl_requests_created

        first_url = crawl_calls[0][1][3]
        assert first_url.startswith("https://acme.com.br")

    @pytest.mark.asyncio
    async def test_marks_parked_and_skips_crawl_requests(self):
        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "Acme LTDA",
                "nome_fantasia": "Acme",
                "email": "contato@acme.com.br",
                "uf": "SP",
                "municipio": 1,
                "cep": "00000000",
            }
        )

        async with _httpx_client(_parked_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        crawl_calls = [c for c in conn.execute_calls if "crawl_requests" in c[0]]
        upsert_calls = [c for c in conn.execute_calls if "company_domains" in c[0]]
        assert outcome.crawl_requests_created == 0
        assert crawl_calls == []
        assert all("rejected" in str(call[1]) for call in upsert_calls)

    @pytest.mark.asyncio
    async def test_marks_unreachable_domain_as_candidate_with_low_confidence(self):
        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "Acme LTDA",
                "nome_fantasia": "Acme",
                "email": "contato@acme.com.br",
                "uf": "SP",
                "municipio": 1,
                "cep": "00000000",
            }
        )

        async with _httpx_client(_error_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        crawl_calls = [c for c in conn.execute_calls if "crawl_requests" in c[0]]
        upsert_calls = [c for c in conn.execute_calls if "company_domains" in c[0]]
        assert outcome.crawl_requests_created == 0
        assert crawl_calls == []
        for call in upsert_calls:
            confidence_arg = call[1][6]
            status_arg = call[1][7]
            assert confidence_arg <= 30
            assert status_arg == "candidate"
