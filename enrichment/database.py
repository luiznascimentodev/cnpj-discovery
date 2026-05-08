from typing import Optional

import asyncpg
from loguru import logger

from config import settings

_pool: Optional[asyncpg.Pool] = None


async def create_pool() -> asyncpg.Pool:
    global _pool
    _pool = await asyncpg.create_pool(
        settings.dsn,
        min_size=1,
        max_size=10,
        command_timeout=60,
        statement_cache_size=0,
    )
    logger.info(
        f"Enrichment database pool created: {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )
    return _pool


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

