"""
Cache Redis para resultados de queries frequentes.

Transparente: se o Redis não estiver disponível, todas as operações são no-op
e as requests caem direto no PostgreSQL sem erro.
"""
import hashlib
import json
from typing import Any, Optional

from loguru import logger

try:
    import redis.asyncio as aioredis
    _REDIS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _REDIS_AVAILABLE = False

from core.config import settings

_redis: Optional[Any] = None


async def create_cache() -> None:
    global _redis
    if not _REDIS_AVAILABLE:  # pragma: no cover
        logger.warning("redis package not installed — caching disabled")
        return
    try:
        _redis = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
        await _redis.ping()
        logger.info(f"Redis cache connected: {settings.redis_url}")
    except Exception as exc:
        logger.warning(f"Redis unavailable ({exc}) — caching disabled")
        _redis = None


async def close_cache() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def get_redis():
    return _redis


def make_cache_key(prefix: str, params: dict) -> str:
    raw = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"cnpj:{prefix}:{digest}"


async def cache_get(key: str) -> Optional[Any]:
    if _redis is None:
        return None
    try:
        val = await _redis.get(key)
        return json.loads(val) if val is not None else None
    except Exception as exc:
        logger.debug(f"Cache GET error ({key}): {exc}")
        return None


async def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    if _redis is None:
        return
    try:
        await _redis.setex(key, ttl, json.dumps(value, default=str))
    except Exception as exc:
        logger.debug(f"Cache SET error ({key}): {exc}")
