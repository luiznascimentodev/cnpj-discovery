"""Testes para api/main.py e api/config.py — 100% de cobertura."""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

from config import Settings
from main import create_app


# ─── config.py tests ─────────────────────────────────────────────────────────

class TestSettings:
    def test_dsn_property(self):
        s = Settings(
            postgres_host="db", postgres_port=5432,
            postgres_db="mydb", postgres_user="user", postgres_password="pass"
        )
        assert s.dsn == "postgresql://user:pass@db:5432/mydb"

    def test_cors_origins_list_single(self):
        s = Settings(cors_origins="http://localhost:3000", postgres_password="x")
        assert s.cors_origins_list == ["http://localhost:3000"]

    def test_cors_origins_list_multiple(self):
        s = Settings(cors_origins="http://a.com,http://b.com", postgres_password="x")
        assert s.cors_origins_list == ["http://a.com", "http://b.com"]

    def test_cors_origins_list_strips_whitespace(self):
        s = Settings(cors_origins=" http://a.com , http://b.com ", postgres_password="x")
        assert s.cors_origins_list == ["http://a.com", "http://b.com"]

    def test_cors_origins_list_ignores_empty(self):
        s = Settings(cors_origins="", postgres_password="x")
        assert s.cors_origins_list == []

    def test_default_environment(self):
        s = Settings(postgres_password="x")
        assert s.environment == "development"


# ─── database.py tests ───────────────────────────────────────────────────────

class TestDatabase:
    @pytest.mark.asyncio
    async def test_get_pool_raises_when_not_initialized(self):
        import database
        original = database._pool
        database._pool = None
        with pytest.raises(RuntimeError, match="not initialized"):
            await database.get_pool()
        database._pool = original

    @pytest.mark.asyncio
    async def test_close_pool_noop_when_none(self):
        import database
        original = database._pool
        database._pool = None
        await database.close_pool()  # não deve levantar erro
        assert database._pool is None
        database._pool = original

    @pytest.mark.asyncio
    async def test_create_and_close_pool(self):
        import database
        with patch("database.asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
            mock_pool = AsyncMock()
            mock_create.return_value = mock_pool
            pool = await database.create_pool()
            assert pool is mock_pool
            assert database._pool is mock_pool
            await database.close_pool()
            assert database._pool is None
            mock_pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_pool_returns_pool_when_initialized(self):
        import database
        mock_pool = AsyncMock()
        original = database._pool
        database._pool = mock_pool
        result = await database.get_pool()
        assert result is mock_pool
        database._pool = original


# ─── FastAPI app tests ────────────────────────────────────────────────────────

class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, client: AsyncClient):
        response = await client.get("/v1/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_returns_ok_status(self, client: AsyncClient):
        response = await client.get("/v1/health")
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_returns_version(self, client: AsyncClient):
        response = await client.get("/v1/health")
        data = response.json()
        assert "version" in data
        assert data["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_health_content_type_json(self, client: AsyncClient):
        response = await client.get("/v1/health")
        assert "application/json" in response.headers["content-type"]


class TestOpenAPISchema:
    @pytest.mark.asyncio
    async def test_openapi_endpoint_available(self, client: AsyncClient):
        response = await client.get("/openapi.json")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_openapi_has_title(self, client: AsyncClient):
        response = await client.get("/openapi.json")
        schema = response.json()
        assert schema["info"]["title"] == "CNPJ Discovery API"

    @pytest.mark.asyncio
    async def test_openapi_has_version(self, client: AsyncClient):
        response = await client.get("/openapi.json")
        schema = response.json()
        assert schema["info"]["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_docs_endpoint_available(self, client: AsyncClient):
        response = await client.get("/docs")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_tag_present(self, client: AsyncClient):
        response = await client.get("/openapi.json")
        schema = response.json()
        tag_names = [t["name"] for t in schema["tags"]]
        assert "health" in tag_names
        assert "prospecting" in tag_names


class TestCORSHeaders:
    @pytest.mark.asyncio
    async def test_cors_header_present_for_allowed_origin(self, client: AsyncClient):
        response = await client.get(
            "/v1/health",
            headers={"Origin": "http://localhost:3000"},
        )
        assert "access-control-allow-origin" in response.headers

    @pytest.mark.asyncio
    async def test_cors_allow_get_method(self, client: AsyncClient):
        response = await client.options(
            "/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code in (200, 204)


class TestCreateApp:
    def test_returns_fastapi_instance(self):
        from fastapi import FastAPI
        app = create_app()
        assert isinstance(app, FastAPI)

    def test_app_has_correct_title(self):
        app = create_app()
        assert app.title == "CNPJ Discovery API"


class TestLifespan:
    @pytest.mark.asyncio
    async def test_lifespan_calls_create_and_close_pool(self):
        """Exercises lines 28-30 in main.py (lifespan body)."""
        with patch("main.create_pool", new_callable=AsyncMock) as mock_create, \
             patch("main.close_pool", new_callable=AsyncMock) as mock_close, \
             patch("main.create_cache", new_callable=AsyncMock), \
             patch("main.close_cache", new_callable=AsyncMock):
            app = create_app()
            async with AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=True),
                base_url="http://test",
            ) as ac:
                # Trigger lifespan manually via the app's router lifespan
                async with app.router.lifespan_context(app):
                    response = await ac.get("/v1/health")
                    assert response.status_code == 200
            mock_create.assert_called_once()
            mock_close.assert_called_once()
