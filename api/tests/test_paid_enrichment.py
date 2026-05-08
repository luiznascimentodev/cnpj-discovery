from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.enrichment import (
    EnrichmentContact,
    EnrichmentDomain,
    PaidEnrichmentDetail,
)
from routers.paid_enrichment import _normalize_cnpj, _require_account_id
from services.enrichment_client import EnrichmentServiceError, fetch_paid_enrichment
from services.entitlements import has_entitlement


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

        with patch("services.enrichment_client.httpx.AsyncClient", FakeAsyncClient):
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

        with patch("services.enrichment_client.httpx.AsyncClient", FakeAsyncClient):
            await fetch_paid_enrichment("12345678000190", account_id="acct")

        assert "X-Request-Id" not in FakeAsyncClient.last_headers

    @pytest.mark.asyncio
    async def test_fetch_paid_enrichment_raises_for_4xx(self):
        FakeAsyncClient.next_response = FakeResponse(403, {"detail": "forbidden"})
        with patch("services.enrichment_client.httpx.AsyncClient", FakeAsyncClient):
            with pytest.raises(EnrichmentServiceError, match="rejected"):
                await fetch_paid_enrichment("12345678000190", account_id="acct")

    @pytest.mark.asyncio
    async def test_fetch_paid_enrichment_raises_for_5xx(self):
        FakeAsyncClient.next_response = FakeResponse(503, {"detail": "down"})
        with patch("services.enrichment_client.httpx.AsyncClient", FakeAsyncClient):
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
        with patch("routers.paid_enrichment.get_pool", new_callable=AsyncMock) as get_pool:
            response = await client.get(
                "/v1/paid/empresa/123/enrichment",
                headers={"X-Account-Id": "acct"},
            )
        assert response.status_code == 422
        get_pool.assert_not_called()

    @pytest.mark.asyncio
    async def test_paid_enrichment_forbids_missing_entitlement(self, client, mock_pool):
        with patch("routers.paid_enrichment.has_entitlement", new_callable=AsyncMock, return_value=False):
            response = await client.get(
                "/v1/paid/empresa/12345678000190/enrichment",
                headers={"X-Account-Id": "acct"},
            )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_paid_enrichment_returns_service_payload(self, client, mock_pool):
        detail = PaidEnrichmentDetail(cnpj="12345678000190", status="not_enriched")
        with (
            patch("routers.paid_enrichment.has_entitlement", new_callable=AsyncMock, return_value=True),
            patch("routers.paid_enrichment.fetch_paid_enrichment", new_callable=AsyncMock, return_value=detail) as fetch,
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
            patch("routers.paid_enrichment.has_entitlement", new_callable=AsyncMock, return_value=True),
            patch(
                "routers.paid_enrichment.fetch_paid_enrichment",
                new_callable=AsyncMock,
                side_effect=EnrichmentServiceError("down"),
            ),
        ):
            response = await client.get(
                "/v1/paid/empresa/12345678000190/enrichment",
                headers={"X-Account-Id": "acct"},
            )

        assert response.status_code == 502
