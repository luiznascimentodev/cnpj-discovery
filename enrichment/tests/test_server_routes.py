from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI

from api.schemas import EnrichmentDetailResponse, EvidenceResponse
from config import DEFAULT_INTERNAL_API_KEY
from server import create_app

HEADERS = {"X-Enrichment-Api-Key": DEFAULT_INTERNAL_API_KEY}
PAID_HEADERS = {
    "X-Enrichment-Api-Key": DEFAULT_INTERNAL_API_KEY,
    "X-Account-Id": "acct-1",
    "X-Request-Id": "req-1",
}


class TestServer:
    def test_create_app_returns_fastapi(self):
        assert isinstance(create_app(), FastAPI)

    def test_create_app_title(self):
        assert create_app().title == "CNPJ Enrichment Service"

    def test_main_exports_app(self):
        import main

        assert isinstance(main.app, FastAPI)


class TestRoutes:
    @pytest.mark.asyncio
    async def test_health_is_public(self, client):
        response = await client.get("/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "version": "0.1.0"}

    @pytest.mark.asyncio
    async def test_status_requires_internal_api_key(self, client):
        response = await client.get("/v1/status")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_status_accepts_internal_api_key(self, client):
        response = await client.get("/v1/status", headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_openapi_contains_enrichment_tag(self, client):
        response = await client.get("/openapi.json")
        tag_names = [tag["name"] for tag in response.json()["tags"]]
        assert "enrichment" in tag_names

    @pytest.mark.asyncio
    async def test_enqueue_validates_cnpj_before_pool_access(self, client):
        with patch("api.routes.get_pool", new_callable=AsyncMock) as get_pool:
            response = await client.post(
                "/v1/enrichment/123/enqueue",
                json={"reason": "manual"},
                headers=HEADERS,
            )
        assert response.status_code == 422
        get_pool.assert_not_called()

    @pytest.mark.asyncio
    async def test_enqueue_calls_repository(self, client):
        pool = object()
        with (
            patch("api.routes.get_pool", new_callable=AsyncMock, return_value=pool),
            patch("api.routes.enqueue_target", new_callable=AsyncMock, return_value="12345678000190") as enqueue,
        ):
            response = await client.post(
                "/v1/enrichment/12345678000190/enqueue",
                json={"reason": "manual", "priority": 80},
                headers=HEADERS,
            )

        assert response.status_code == 202
        assert response.json()["cnpj"] == "12345678000190"
        enqueue.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lifespan_opens_and_closes_pool(self):
        with (
            patch("server.create_pool", new_callable=AsyncMock) as create_pool_mock,
            patch("server.close_pool", new_callable=AsyncMock) as close_pool_mock,
        ):
            app = create_app()
            async with app.router.lifespan_context(app):
                pass

        create_pool_mock.assert_awaited_once()
        close_pool_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_enrichment_requires_account_context(self, client):
        response = await client.get("/v1/enrichment/12345678000190", headers=HEADERS)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_enrichment_returns_detail_and_audits(self, client):
        pool = object()
        detail = EnrichmentDetailResponse(cnpj="12345678000190", status="not_enriched")
        with (
            patch("api.routes.get_pool", new_callable=AsyncMock, return_value=pool),
            patch("api.routes.fetch_enrichment_detail", new_callable=AsyncMock, return_value=detail) as fetch_detail,
            patch("api.routes.insert_access_audit", new_callable=AsyncMock) as insert_audit,
        ):
            response = await client.get(
                "/v1/enrichment/12345678000190",
                headers=PAID_HEADERS,
            )

        assert response.status_code == 200
        assert response.json()["status"] == "not_enriched"
        fetch_detail.assert_awaited_once_with(pool, "12345678000190")
        insert_audit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_evidence_returns_items_and_audits(self, client):
        pool = object()
        evidence = EvidenceResponse(cnpj="12345678000190", items=[])
        with (
            patch("api.routes.get_pool", new_callable=AsyncMock, return_value=pool),
            patch("api.routes.fetch_evidence", new_callable=AsyncMock, return_value=evidence) as fetch_evidence,
            patch("api.routes.insert_access_audit", new_callable=AsyncMock) as insert_audit,
        ):
            response = await client.get(
                "/v1/enrichment/12345678000190/evidence?limit=10",
                headers=PAID_HEADERS,
            )

        assert response.status_code == 200
        assert response.json()["items"] == []
        fetch_evidence.assert_awaited_once_with(pool, "12345678000190", limit=10)
        insert_audit.assert_awaited_once()
