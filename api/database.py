"""
Gerenciamento do pool de conexões asyncpg.

O pool é criado no startup da aplicação (lifespan) e fechado no shutdown.
Cada requisição HTTP obtém uma conexão do pool via `get_pool()`.
"""
from typing import Optional

import asyncpg
from loguru import logger

from config import settings

_pool: Optional[asyncpg.Pool] = None


async def create_pool() -> asyncpg.Pool:
    """Cria o pool de conexões PostgreSQL."""
    global _pool
    _pool = await asyncpg.create_pool(
        settings.dsn,
        min_size=5,
        max_size=20,
        command_timeout=60,
        statement_cache_size=0,  # necessário para pgbouncer compatibility
    )
    logger.info(f"Database pool created: {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}")
    return _pool


async def close_pool() -> None:
    """Fecha o pool de conexões."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")


async def get_pool() -> asyncpg.Pool:
    """
    Retorna o pool ativo. Deve ser chamado após o startup da aplicação.
    Raises RuntimeError se o pool não foi inicializado.
    """
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call create_pool() first.")
    return _pool
