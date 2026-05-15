from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from modules.enrichment.schemas import (
    EnrichmentContact,
    EnrichmentDomain,
    PaidEnrichmentDetail,
)
from modules.enrichment.job_schemas import EnrichmentEstimateRequest, EnrichmentJobCreateRequest
from modules.enrichment.router import _normalize_cnpj, _require_account_id
from modules.enrichment.client import EnrichmentServiceError, fetch_paid_enrichment
from modules.enrichment.jobs import (
    Candidate,
    cancel_enrichment_job,
    create_enrichment_job,
    estimate_enrichment_job,
    export_enrichment_job_csv,
    get_enrichment_job,
    list_enrichment_job_items,
    list_enrichment_jobs,
)
from modules.enrichment.entitlements import has_entitlement


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


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeAsyncClient:
    next_response = FakeResponse(200, {})
    last_url = None
    last_headers = None

    def __init__(self, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def get(self, url, headers):
        FakeAsyncClient.last_url = url
        FakeAsyncClient.last_headers = headers
        return FakeAsyncClient.next_response


class FakeTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeJobConn:
    def __init__(self, *, rows=None, cache_rows=None, job_row=None, export_rows=None, item_rows=None):
        self.rows = rows or []
        self.cache_rows = cache_rows or []
        self.job_row = job_row or {
            "id": 77,
            "status": "queued",
            "created_at": None,
            "idempotency_key": "idem",
        }
        self.export_rows = export_rows or []
        self.item_rows = item_rows or [
            {
                "cnpj": "12345678000190",
                "status": "pending",
                "result_source": None,
                "attempts": 0,
                "last_error": None,
                "updated_at": None,
            }
        ]
        self.executed = []
        self.fetch_calls = []
        self.fetchrow_calls = []

    def transaction(self):
        return FakeTx()

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        if "string_agg" in query:
            return self.export_rows
        if "published_contacts" in query:
            return self.cache_rows
        if "enrichment_job_items" in query and "RETURNING id" in query:
            return [{"id": 1}, {"id": 2}]
        if "cnpj_basico || cnpj_ordem || cnpj_dv AS cnpj" in query:
            return self.item_rows
        if "FROM app_private.enrichment_jobs" in query:
            return self.rows
        return self.rows

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        if "INSERT INTO app_private.enrichment_jobs" in query:
            return self.job_row
        if "WHERE account_id = $1 AND id = $2" in query:
            return self.rows[0] if self.rows else None
        return self.job_row

    async def execute(self, query, *args):
        self.executed.append((query, args))


class TestModels:
    def test_paid_enrichment_detail_accepts_nested_payload(self):
        detail = PaidEnrichmentDetail(
            cnpj="12345678000190",
            status="done",
            domains=[
                EnrichmentDomain(
                    domain="example.com.br",
                    homepage_url="https://example.com.br",
                    source="official_site",
                    confidence=91,
                    status="verified",
                )
            ],
            contacts=[
                EnrichmentContact(
                    contact_type="email",
                    value="contato@example.com.br",
                    normalized_value="contato@example.com.br",
                    source="official_site",
                    confidence=95,
                )
            ],
        )
        assert detail.contacts[0].value == "contato@example.com.br"

    def test_estimate_request_normalizes_and_deduplicates_cnpjs(self):
        payload = EnrichmentEstimateRequest(
            cnpjs=["12.345.678/0001-90", "12345678000190"],
            max_items=10,
        )
        assert payload.cnpjs == ["12345678000190"]
        assert payload.source_type == "selection"

    def test_estimate_request_rejects_ambiguous_source(self):
        with pytest.raises(ValueError):
            EnrichmentEstimateRequest(cnpjs=["12345678000190"], filters={"uf": "SP"})

    def test_estimate_request_rejects_invalid_cnpj(self):
        with pytest.raises(ValueError, match="14 dígitos"):
            EnrichmentEstimateRequest(cnpjs=["123"])


class TestEntitlements:
    @pytest.mark.asyncio
    async def test_has_entitlement_returns_true(self):
        conn = AsyncMock()
        conn.fetchval.return_value = True
        result = await has_entitlement(FakePool(conn), "acct", "crawler_contacts")
        assert result is True
        conn.fetchval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_has_entitlement_returns_false(self):
        conn = AsyncMock()
        conn.fetchval.return_value = False
        result = await has_entitlement(FakePool(conn), "acct", "crawler_contacts")
        assert result is False


class TestEnrichmentClient:
    @pytest.mark.asyncio
    async def test_fetch_paid_enrichment_returns_model(self):
        payload = {
            "cnpj": "12345678000190",
            "status": "done",
            "domains": [],
            "contacts": [],
        }
        FakeAsyncClient.next_response = FakeResponse(200, payload)

        with patch("modules.enrichment.client.httpx.AsyncClient", FakeAsyncClient):
            detail = await fetch_paid_enrichment(
                "12345678000190",
                account_id="acct",
                request_id="req",
            )

        assert detail.cnpj == "12345678000190"
        assert FakeAsyncClient.last_url.endswith("/v1/enrichment/12345678000190")
        assert FakeAsyncClient.last_headers["X-Enrichment-Api-Key"]
        assert FakeAsyncClient.last_headers["X-Account-Id"] == "acct"
        assert FakeAsyncClient.last_headers["X-Request-Id"] == "req"

    @pytest.mark.asyncio
    async def test_fetch_paid_enrichment_omits_missing_request_id(self):
        FakeAsyncClient.next_response = FakeResponse(
            200,
            {"cnpj": "12345678000190", "status": "not_enriched", "domains": [], "contacts": []},
        )

        with patch("modules.enrichment.client.httpx.AsyncClient", FakeAsyncClient):
            await fetch_paid_enrichment("12345678000190", account_id="acct")

        assert "X-Request-Id" not in FakeAsyncClient.last_headers

    @pytest.mark.asyncio
    async def test_fetch_paid_enrichment_raises_for_4xx(self):
        FakeAsyncClient.next_response = FakeResponse(403, {"detail": "forbidden"})
        with patch("modules.enrichment.client.httpx.AsyncClient", FakeAsyncClient):
            with pytest.raises(EnrichmentServiceError, match="rejected"):
                await fetch_paid_enrichment("12345678000190", account_id="acct")

    @pytest.mark.asyncio
    async def test_fetch_paid_enrichment_raises_for_5xx(self):
        FakeAsyncClient.next_response = FakeResponse(503, {"detail": "down"})
        with patch("modules.enrichment.client.httpx.AsyncClient", FakeAsyncClient):
            with pytest.raises(EnrichmentServiceError, match="unavailable"):
                await fetch_paid_enrichment("12345678000190", account_id="acct")


class TestPaidRouterHelpers:
    def test_normalize_cnpj_accepts_punctuation(self):
        assert _normalize_cnpj("12.345.678/0001-90") == "12345678000190"

    def test_normalize_cnpj_rejects_invalid_value(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            _normalize_cnpj("123")
        assert exc.value.status_code == 422

    def test_require_account_id_strips_value(self):
        assert _require_account_id(" acct ") == "acct"

    def test_require_account_id_rejects_missing_value(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            _require_account_id(" ")
        assert exc.value.status_code == 401


class TestPaidRouter:
    @pytest.mark.asyncio
    async def test_paid_enrichment_requires_account_header(self, client):
        response = await client.get("/v1/paid/empresa/12345678000190/enrichment")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_paid_enrichment_rejects_invalid_cnpj_before_pool(self, client):
        with patch("modules.enrichment.router.get_pool", new_callable=AsyncMock) as get_pool:
            response = await client.get(
                "/v1/paid/empresa/123/enrichment",
                headers={"X-Account-Id": "acct"},
            )
        assert response.status_code == 422
        get_pool.assert_not_called()

    @pytest.mark.asyncio
    async def test_paid_enrichment_forbids_missing_entitlement(self, client, mock_pool):
        with patch("modules.enrichment.router.has_entitlement", new_callable=AsyncMock, return_value=False):
            response = await client.get(
                "/v1/paid/empresa/12345678000190/enrichment",
                headers={"X-Account-Id": "acct"},
            )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_paid_enrichment_returns_service_payload(self, client, mock_pool):
        detail = PaidEnrichmentDetail(cnpj="12345678000190", status="not_enriched")
        with (
            patch("modules.enrichment.router.has_entitlement", new_callable=AsyncMock, return_value=True),
            patch("modules.enrichment.router.fetch_paid_enrichment", new_callable=AsyncMock, return_value=detail) as fetch,
        ):
            response = await client.get(
                "/v1/paid/empresa/12345678000190/enrichment",
                headers={"X-Account-Id": "acct", "X-Request-Id": "req"},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "not_enriched"
        fetch.assert_awaited_once_with("12345678000190", account_id="acct", request_id="req")

    @pytest.mark.asyncio
    async def test_paid_enrichment_maps_service_errors_to_502(self, client):
        with (
            patch("modules.enrichment.router.has_entitlement", new_callable=AsyncMock, return_value=True),
            patch(
                "modules.enrichment.router.fetch_paid_enrichment",
                new_callable=AsyncMock,
                side_effect=EnrichmentServiceError("down"),
            ),
        ):
            response = await client.get(
                "/v1/paid/empresa/12345678000190/enrichment",
                headers={"X-Account-Id": "acct"},
            )

        assert response.status_code == 502

    @pytest.mark.asyncio
    async def test_estimate_job_requires_bulk_entitlement(self, client):
        with patch("modules.enrichment.router.has_entitlement", new_callable=AsyncMock, return_value=False):
            response = await client.post(
                "/v1/paid/enrichment/estimate",
                headers={"X-Account-Id": "acct"},
                json={"cnpjs": ["12345678000190"]},
            )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_estimate_job_returns_payload(self, client):
        estimate = {
            "source_type": "selection",
            "requested_count": 1,
            "eligible_count": 1,
            "cache_hit_count": 0,
            "new_count": 1,
            "skipped_inactive_count": 0,
            "cost_credits": 1,
            "estimated_seconds_min": 1,
            "estimated_seconds_max": 8,
        }
        with (
            patch("modules.enrichment.router.has_entitlement", new_callable=AsyncMock, return_value=True),
            patch("modules.enrichment.router.estimate_enrichment_job", new_callable=AsyncMock, return_value=estimate),
        ):
            response = await client.post(
                "/v1/paid/enrichment/estimate",
                headers={"X-Account-Id": "acct"},
                json={"cnpjs": ["12345678000190"]},
            )
        assert response.status_code == 200
        assert response.json()["new_count"] == 1

    @pytest.mark.asyncio
    async def test_create_job_route_returns_job(self, client):
        from modules.enrichment.job_schemas import EnrichmentJobResponse

        job = EnrichmentJobResponse(
            source_type="selection",
            requested_count=1,
            eligible_count=1,
            cache_hit_count=0,
            new_count=1,
            skipped_inactive_count=0,
            cost_credits=1,
            estimated_seconds_min=1,
            estimated_seconds_max=8,
            job_id=9,
            status="queued",
        )
        with (
            patch("modules.enrichment.router.has_entitlement", new_callable=AsyncMock, return_value=True),
            patch("modules.enrichment.router.create_enrichment_job", new_callable=AsyncMock, return_value=job) as create,
        ):
            response = await client.post(
                "/v1/paid/enrichment/jobs",
                headers={"X-Account-Id": "acct", "X-User-Id": "user", "Idempotency-Key": "idem"},
                json={"cnpjs": ["12345678000190"]},
            )
        assert response.status_code == 200
        assert response.json()["job_id"] == 9
        assert create.await_args.kwargs["created_by"] == "user"

    @pytest.mark.asyncio
    async def test_job_detail_404_when_missing(self, client):
        with (
            patch("modules.enrichment.router.has_entitlement", new_callable=AsyncMock, return_value=True),
            patch("modules.enrichment.router.get_enrichment_job", new_callable=AsyncMock, return_value=None),
        ):
            response = await client.get(
                "/v1/paid/enrichment/jobs/99",
                headers={"X-Account-Id": "acct"},
            )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_job_routes_return_success_payloads(self, client):
        from datetime import datetime
        from modules.enrichment.job_schemas import (
            EnrichmentJobCancelResponse,
            EnrichmentJobItemsResponse,
            EnrichmentJobItem,
            EnrichmentJobListResponse,
            EnrichmentJobSummary,
        )

        summary = EnrichmentJobSummary(
            id=1,
            status="queued",
            source_type="selection",
            requested_count=1,
            accepted_count=1,
            cache_hit_count=0,
            skipped_count=0,
            failed_count=0,
            ready_count=0,
            cost_credits=1,
            created_at=datetime.now(),
        )
        with (
            patch("modules.enrichment.router.has_entitlement", new_callable=AsyncMock, return_value=True),
            patch("modules.enrichment.router.list_enrichment_jobs", new_callable=AsyncMock, return_value=EnrichmentJobListResponse(jobs=[summary])),
            patch("modules.enrichment.router.get_enrichment_job", new_callable=AsyncMock, return_value=summary),
            patch("modules.enrichment.router.list_enrichment_job_items", new_callable=AsyncMock, return_value=EnrichmentJobItemsResponse(job_id=1, items=[EnrichmentJobItem(cnpj="12345678000190", status="pending")])),
            patch("modules.enrichment.router.cancel_enrichment_job", new_callable=AsyncMock, return_value=1),
            patch("modules.enrichment.router.export_enrichment_job_csv", new_callable=AsyncMock, return_value="cnpj\n123\n"),
        ):
            headers = {"X-Account-Id": "acct"}
            list_response = await client.get("/v1/paid/enrichment/jobs", headers=headers)
            detail_response = await client.get("/v1/paid/enrichment/jobs/1", headers=headers)
            items_response = await client.get("/v1/paid/enrichment/jobs/1/items", headers=headers)
            cancel_response = await client.post("/v1/paid/enrichment/jobs/1/cancel", headers=headers)
            export_response = await client.get("/v1/paid/enrichment/jobs/1/export.csv", headers=headers)

        assert list_response.status_code == 200
        assert detail_response.json()["id"] == 1
        assert items_response.json()["items"][0]["cnpj"] == "12345678000190"
        assert cancel_response.json() == EnrichmentJobCancelResponse(job_id=1, cancelled_items=1).model_dump()
        assert export_response.text == "cnpj\n123\n"


class TestEnrichmentJobsService:
    @pytest.mark.asyncio
    async def test_estimate_selected_counts_cache_and_inactive(self):
        conn = FakeJobConn(
            rows=[
                {"cnpj_basico": "12345678", "cnpj_ordem": "0001", "cnpj_dv": "90"},
            ],
            cache_rows=[{"cnpj": "12345678000190"}],
        )
        payload = EnrichmentEstimateRequest(cnpjs=["12345678000190", "00000000000100"])
        result = await estimate_enrichment_job(FakePool(conn), payload)

        assert result.eligible_count == 1
        assert result.cache_hit_count == 1
        assert result.new_count == 0
        assert result.skipped_inactive_count == 1

    @pytest.mark.asyncio
    async def test_estimate_filter_handles_empty_candidates_without_cache_query(self):
        conn = FakeJobConn(rows=[])
        payload = EnrichmentEstimateRequest(filters={"uf": "SP"}, max_items=50)

        result = await estimate_enrichment_job(FakePool(conn), payload)

        assert result.source_type == "filter"
        assert result.eligible_count == 0
        assert result.cache_hit_count == 0

    @pytest.mark.asyncio
    async def test_create_job_inserts_pending_and_cache_items(self):
        conn = FakeJobConn(
            rows=[
                {"cnpj_basico": "12345678", "cnpj_ordem": "0001", "cnpj_dv": "90"},
                {"cnpj_basico": "22222222", "cnpj_ordem": "0001", "cnpj_dv": "00"},
            ],
            cache_rows=[{"cnpj": "12345678000190"}],
        )
        payload = EnrichmentJobCreateRequest(cnpjs=["12345678000190", "22222222000100"])
        job = await create_enrichment_job(
            FakePool(conn),
            account_id="acct",
            created_by="user",
            payload=payload,
            idempotency_key="idem",
        )

        item_statuses = [args[5] for query, args in conn.executed if "enrichment_job_items" in query]
        assert job.job_id == 77
        assert item_statuses == ["cache_hit", "pending"]

    @pytest.mark.asyncio
    async def test_list_get_items_cancel_and_export(self):
        job_row = {
            "id": 1,
            "status": "queued",
            "source_type": "selection",
            "requested_count": 1,
            "accepted_count": 1,
            "cache_hit_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "ready_count": 0,
            "cost_credits": 1,
            "created_at": __import__("datetime").datetime.now(),
            "started_at": None,
            "completed_at": None,
            "cancelled_at": None,
        }
        conn = FakeJobConn(
            rows=[job_row],
            export_rows=[
                {
                    "cnpj": "12345678000190",
                    "status": "enriched",
                    "razao_social": "Teste",
                    "nome_fantasia": None,
                    "uf": "SP",
                    "municipio": "Sao Paulo",
                    "emails": "a@b.com",
                    "telefones": None,
                    "evidencias": "https://x.test",
                }
            ],
        )

        jobs = await list_enrichment_jobs(FakePool(conn), account_id="acct")
        job = await get_enrichment_job(FakePool(conn), account_id="acct", job_id=1)
        items = await list_enrichment_job_items(FakePool(conn), account_id="acct", job_id=1)
        cancelled = await cancel_enrichment_job(FakePool(conn), account_id="acct", job_id=1)
        csv_body = await export_enrichment_job_csv(FakePool(conn), account_id="acct", job_id=1)

        assert jobs.jobs[0].id == 1
        assert job.id == 1
        assert items.items[0].cnpj == "12345678000190"
        assert cancelled == 2
        assert "a@b.com" in csv_body
