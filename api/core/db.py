"""
Gerenciamento do pool de conexões asyncpg.

O pool é criado no startup da aplicação (lifespan) e fechado no shutdown.
Cada requisição HTTP obtém uma conexão do pool via `get_pool()`.

InstrumentedConnection conta queries por request (via contextvar) para o
N+1 detector de middleware.
"""
import contextvars
from typing import Optional

import asyncpg
from loguru import logger

from core.config import settings

_pool: Optional[asyncpg.Pool] = None

# Incrementado por InstrumentedConnection a cada query executada no contexto da request atual.
# Lido e zerado pelo N1DetectorMiddleware.
query_count: contextvars.ContextVar[int] = contextvars.ContextVar("db_query_count", default=0)


class InstrumentedConnection(asyncpg.Connection):
    """Subtipo de Connection que incrementa query_count a cada query executada."""

    def _inc(self):  # pragma: no cover
        query_count.set(query_count.get() + 1)

    async def fetch(self, query, *args, **kwargs):  # pragma: no cover
        self._inc()
        return await super().fetch(query, *args, **kwargs)

    async def fetchrow(self, query, *args, **kwargs):  # pragma: no cover
        self._inc()
        return await super().fetchrow(query, *args, **kwargs)

    async def fetchval(self, query, *args, **kwargs):  # pragma: no cover
        self._inc()
        return await super().fetchval(query, *args, **kwargs)

    async def execute(self, query, *args, **kwargs):  # pragma: no cover
        self._inc()
        return await super().execute(query, *args, **kwargs)

    def cursor(self, query, *args, **kwargs):  # pragma: no cover
        self._inc()
        return super().cursor(query, *args, **kwargs)


async def create_pool() -> asyncpg.Pool:
    global _pool
    _pool = await asyncpg.create_pool(
        settings.dsn,
        min_size=5,
        max_size=20,
        command_timeout=60,
        statement_cache_size=0,  # necessário para pgbouncer compatibility
        connection_class=InstrumentedConnection,
    )
    logger.info(f"Database pool created: {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call create_pool() first.")
    return _pool
