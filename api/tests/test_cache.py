"""Testes para o módulo de cache Redis."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import cache as cache_module
from cache import cache_get, cache_set, close_cache, create_cache, make_cache_key


class TestMakeCacheKey:
    def test_produces_deterministic_key(self):
        k1 = make_cache_key("prospecting", {"uf": "SP", "limit": 50})
        k2 = make_cache_key("prospecting", {"limit": 50, "uf": "SP"})
        assert k1 == k2  # sort_keys=True ensures order independence

    def test_different_params_give_different_keys(self):
        k1 = make_cache_key("prospecting", {"uf": "SP"})
        k2 = make_cache_key("prospecting", {"uf": "RJ"})
        assert k1 != k2

    def test_different_prefixes_give_different_keys(self):
        k1 = make_cache_key("prospecting", {"uf": "SP"})
        k2 = make_cache_key("export", {"uf": "SP"})
        assert k1 != k2

    def test_key_contains_prefix(self):
        k = make_cache_key("prospecting", {})
        assert k.startswith("cnpj:prospecting:")


class TestCacheBypass:
    """Quando _redis é None, todas as operações são no-op."""

    @pytest.mark.asyncio
    async def test_cache_get_returns_none_when_no_redis(self):
        original = cache_module._redis
        cache_module._redis = None
        try:
            result = await cache_get("some-key")
        finally:
            cache_module._redis = original
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_set_noop_when_no_redis(self):
        original = cache_module._redis
        cache_module._redis = None
        try:
            await cache_set("some-key", {"data": 1})  # should not raise
        finally:
            cache_module._redis = original

    @pytest.mark.asyncio
    async def test_close_cache_noop_when_no_redis(self):
        original = cache_module._redis
        cache_module._redis = None
        try:
            await close_cache()  # should not raise
        finally:
            cache_module._redis = original


class TestCacheWithRedis:
    @pytest.mark.asyncio
    async def test_cache_get_returns_parsed_json(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps({"cnpj": "123"})
        original = cache_module._redis
        cache_module._redis = mock_redis
        try:
            result = await cache_get("key1")
        finally:
            cache_module._redis = original
        assert result == {"cnpj": "123"}

    @pytest.mark.asyncio
    async def test_cache_get_returns_none_for_missing_key(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        original = cache_module._redis
        cache_module._redis = mock_redis
        try:
            result = await cache_get("missing-key")
        finally:
            cache_module._redis = original
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_get_returns_none_on_error(self):
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("redis timeout")
        original = cache_module._redis
        cache_module._redis = mock_redis
        try:
            result = await cache_get("error-key")
        finally:
            cache_module._redis = original
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_set_calls_setex(self):
        mock_redis = AsyncMock()
        original = cache_module._redis
        cache_module._redis = mock_redis
        try:
            await cache_set("key2", [1, 2, 3], ttl=60)
        finally:
            cache_module._redis = original
        mock_redis.setex.assert_called_once_with("key2", 60, json.dumps([1, 2, 3]))

    @pytest.mark.asyncio
    async def test_cache_set_silently_ignores_error(self):
        mock_redis = AsyncMock()
        mock_redis.setex.side_effect = Exception("write error")
        original = cache_module._redis
        cache_module._redis = mock_redis
        try:
            await cache_set("key3", {"x": 1})  # should not raise
        finally:
            cache_module._redis = original

    @pytest.mark.asyncio
    async def test_close_cache_calls_aclose(self):
        mock_redis = AsyncMock()
        original = cache_module._redis
        cache_module._redis = mock_redis
        try:
            await close_cache()
        finally:
            cache_module._redis = original
        mock_redis.aclose.assert_called_once()
        assert cache_module._redis is None


class TestCreateCache:
    @pytest.mark.asyncio
    async def test_create_cache_success(self):
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with patch("cache.aioredis.from_url", return_value=mock_redis):
            await create_cache()

        assert cache_module._redis is mock_redis
        cache_module._redis = None  # cleanup

    @pytest.mark.asyncio
    async def test_create_cache_sets_none_on_connection_error(self):
        mock_redis = AsyncMock()
        mock_redis.ping.side_effect = Exception("connection refused")

        with patch("cache.aioredis.from_url", return_value=mock_redis):
            await create_cache()

        assert cache_module._redis is None
