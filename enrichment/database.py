from __future__ import annotations

import asyncio
from typing import Optional

import asyncpg
from loguru import logger

from config import settings

_pool: Optional[asyncpg.Pool] = None

# Retry asyncpg pool creation when postgres restarts: name resolution can
# transiently fail (gaierror), and the server may report "starting up"
# (CannotConnectNowError) before its boot is complete. Without retry the
# worker exits, docker restarts it, and the cycle storms until pg is ready.
_CREATE_POOL_RETRY_EXCEPTIONS = (
    OSError,  # covers socket.gaierror
    asyncpg.CannotConnectNowError,
    asyncpg.PostgresConnectionError,
    ConnectionError,
)


async def _sleep(delay: float) -> None:
    await asyncio.sleep(delay)


async def create_pool(
    *,
    max_attempts: int = 10,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> asyncpg.Pool:
    global _pool
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    attempt = 0
    while True:
        attempt += 1
        try:
            _pool = await asyncpg.create_pool(
                settings.dsn,
                min_size=1,
                max_size=10,
                command_timeout=60,
                statement_cache_size=0,
            )
            logger.info(
                f"Enrichment database pool created: {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
                f" (attempt={attempt})"
            )
            return _pool
        except _CREATE_POOL_RETRY_EXCEPTIONS as exc:
            if attempt >= max_attempts:
                logger.error(
                    "create_pool exhausted retries attempts={} error={}: {}",
                    attempt, type(exc).__name__, exc,
                )
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            logger.warning(
                "create_pool retry attempt={}/{} delay={:.1f}s error={}: {}",
                attempt, max_attempts, delay, type(exc).__name__, exc,
            )
            await _sleep(delay)


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Enrichment database pool closed")


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Enrichment database pool not initialized. Call create_pool() first.")
    return _pool
