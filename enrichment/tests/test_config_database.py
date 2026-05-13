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

    def test_discovery_concurrency_default(self):
        settings = Settings()
        assert settings.discovery_concurrency == 25

    def test_discovery_concurrency_accepts_custom_value(self):
        settings = Settings(discovery_concurrency=10)
        assert settings.discovery_concurrency == 10


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

    @pytest.mark.asyncio
    async def test_create_pool_retries_on_connection_error_then_succeeds(self):
        import asyncpg
        import database

        pool = AsyncMock()
        attempts = {"n": 0}

        async def flaky_create_pool(*args, **kwargs):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise asyncpg.CannotConnectNowError("starting up")
            return pool

        sleeps: list[float] = []

        async def fake_sleep(delay):
            sleeps.append(delay)

        with patch("database.asyncpg.create_pool", side_effect=flaky_create_pool), \
             patch("database._sleep", side_effect=fake_sleep):
            result = await database.create_pool(base_delay=0.1, max_delay=1.0)
        assert result is pool
        assert attempts["n"] == 3
        assert len(sleeps) == 2
        assert sleeps[0] == pytest.approx(0.1)
        assert sleeps[1] == pytest.approx(0.2)
        await database.close_pool()

    @pytest.mark.asyncio
    async def test_create_pool_retries_on_gaierror(self):
        import database

        pool = AsyncMock()
        attempts = {"n": 0}

        async def flaky_create_pool(*args, **kwargs):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise OSError("Temporary failure in name resolution")
            return pool

        async def fake_sleep(delay):
            pass

        with patch("database.asyncpg.create_pool", side_effect=flaky_create_pool), \
             patch("database._sleep", side_effect=fake_sleep):
            result = await database.create_pool()
        assert result is pool
        assert attempts["n"] == 2
        await database.close_pool()

    @pytest.mark.asyncio
    async def test_create_pool_exhausts_retries_and_raises(self):
        import asyncpg
        import database

        async def always_fail(*args, **kwargs):
            raise asyncpg.CannotConnectNowError("nope")

        async def fake_sleep(delay):
            pass

        with patch("database.asyncpg.create_pool", side_effect=always_fail), \
             patch("database._sleep", side_effect=fake_sleep):
            with pytest.raises(asyncpg.CannotConnectNowError):
                await database.create_pool(max_attempts=3)

    @pytest.mark.asyncio
    async def test_create_pool_rejects_zero_attempts(self):
        import database

        with pytest.raises(ValueError, match="max_attempts"):
            await database.create_pool(max_attempts=0)

    @pytest.mark.asyncio
    async def test_create_pool_caps_delay_at_max(self):
        import asyncpg
        import database

        attempts = {"n": 0}

        async def flaky(*args, **kwargs):
            attempts["n"] += 1
            if attempts["n"] < 5:
                raise asyncpg.CannotConnectNowError("starting up")
            return AsyncMock()

        sleeps: list[float] = []

        async def fake_sleep(delay):
            sleeps.append(delay)

        with patch("database.asyncpg.create_pool", side_effect=flaky), \
             patch("database._sleep", side_effect=fake_sleep):
            await database.create_pool(base_delay=10.0, max_delay=15.0)
        # delays would be 10, 20, 40, 80 — capped at 15 each after first
        assert sleeps[0] == pytest.approx(10.0)
        assert max(sleeps[1:]) <= 15.0
        await database.close_pool()

    @pytest.mark.asyncio
    async def test_sleep_calls_asyncio_sleep(self):
        import database

        with patch("database.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await database._sleep(0.05)
        mock_sleep.assert_awaited_once_with(0.05)

