from unittest.mock import AsyncMock, patch

import pytest

from config import DEFAULT_INTERNAL_API_KEY, Settings


class TestSettings:
    def test_dsn_property(self):
        settings = Settings(
            postgres_host="postgres",
            postgres_port=5433,
            postgres_db="cnpj_test",
            postgres_user="user",
            postgres_password="secret",
        )
        assert settings.dsn == "postgresql://user:secret@postgres:5433/cnpj_test"

    def test_is_production_false_for_development(self):
        settings = Settings(environment="development")
        assert settings.is_production is False

    def test_is_production_true_for_uppercase_production(self):
        settings = Settings(environment="PRODUCTION")
        assert settings.is_production is True

    def test_validate_runtime_security_accepts_development_default_key(self):
        settings = Settings(environment="development")
        settings.validate_runtime_security()

    def test_validate_runtime_security_rejects_production_default_key(self):
        settings = Settings(
            environment="production",
            enrichment_api_key=DEFAULT_INTERNAL_API_KEY,
        )
        with pytest.raises(RuntimeError, match="must be changed"):
            settings.validate_runtime_security()

    def test_validate_runtime_security_accepts_production_custom_key(self):
        settings = Settings(environment="production", enrichment_api_key="custom-key")
        settings.validate_runtime_security()

    def test_external_search_defaults(self):
        settings = Settings()
        assert settings.brasilapi_enabled is True
        assert settings.brasilapi_base_url == "https://brasilapi.com.br/api"
        assert settings.brave_search_api_key == ""
        assert settings.brave_search_base_url == "https://api.search.brave.com"

    def test_google_cse_enabled_false_when_empty(self):
        settings = Settings()
        assert settings.google_cse_enabled is False

    def test_google_cse_enabled_true_when_both_set(self):
        settings = Settings(google_cse_api_key="key", google_cse_cx="cx")
        assert settings.google_cse_enabled is True

    def test_searxng_url_default_is_empty(self):
        settings = Settings()
        assert settings.searxng_url == ""

    def test_searxng_url_accepts_custom_value(self):
        settings = Settings(searxng_url="http://searxng:8080")
        assert settings.searxng_url == "http://searxng:8080"


class TestDatabase:
    @pytest.mark.asyncio
    async def test_get_pool_raises_when_not_initialized(self):
        import database

        original_pool = database._pool
        database._pool = None
        with pytest.raises(RuntimeError, match="not initialized"):
            await database.get_pool()
        database._pool = original_pool

    @pytest.mark.asyncio
    async def test_close_pool_noop_when_not_initialized(self):
        import database

        original_pool = database._pool
        database._pool = None
        await database.close_pool()
        assert database._pool is None
        database._pool = original_pool

    @pytest.mark.asyncio
    async def test_create_pool_and_close_pool(self):
        import database

        with patch("database.asyncpg.create_pool", new_callable=AsyncMock) as create_pool:
            pool = AsyncMock()
            create_pool.return_value = pool

            result = await database.create_pool()
            assert result is pool
            assert database._pool is pool

            await database.close_pool()
            assert database._pool is None
            pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_pool_returns_initialized_pool(self):
        import database

        original_pool = database._pool
        pool = AsyncMock()
        database._pool = pool
        assert await database.get_pool() is pool
        database._pool = original_pool

