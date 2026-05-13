"""Fixtures compartilhadas para testes da API."""
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from main import create_app


@pytest.fixture
async def mock_pool():
    """Pool asyncpg mockado para testes que não precisam do banco."""
    pool = AsyncMock()
    return pool


@pytest.fixture
async def client(mock_pool):
    """
    Cliente HTTP assíncrono para testar a API sem subir servidor real.
    Injeta um pool mockado para evitar conexão real ao PostgreSQL ou Redis.
    """
    app = create_app()

    patchers = [
        patch("main.create_pool", new_callable=AsyncMock),
        patch("main.close_pool", new_callable=AsyncMock),
        patch("main.create_cache", new_callable=AsyncMock),
        patch("main.close_cache", new_callable=AsyncMock),
        patch("database.get_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("routers.prospecting.get_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("routers.export.get_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("routers.status.get_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("routers.cnaes.get_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("routers.empresa.get_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("routers.bairros.get_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("routers.paid_enrichment.get_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("routers.billing_webhook.get_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("routers.prospecting.cache_get", new_callable=AsyncMock, return_value=None),
        patch("routers.prospecting.cache_set", new_callable=AsyncMock),
        patch("routers.cnaes.cache_get", new_callable=AsyncMock, return_value=None),
        patch("routers.cnaes.cache_set", new_callable=AsyncMock),
        patch("routers.empresa.cache_get", new_callable=AsyncMock, return_value=None),
        patch("routers.empresa.cache_set", new_callable=AsyncMock),
        patch("routers.bairros.cache_get", new_callable=AsyncMock, return_value=None),
        patch("routers.bairros.cache_set", new_callable=AsyncMock),
    ]

    with ExitStack() as stack:
        mocks = [stack.enter_context(patcher) for patcher in patchers]
        mock_create = mocks[0]
        mock_create.return_value = mock_pool
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
