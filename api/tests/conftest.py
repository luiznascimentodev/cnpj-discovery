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
        patch("core.db.get_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("modules.prospecting.router.get_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("modules.export.router.get_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("modules.status.router.get_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("modules.cnaes.router.get_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("modules.empresa.router.get_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("modules.bairros.router.get_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("modules.enrichment.router.get_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("routers.billing_webhook.get_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("modules.prospecting.router.cache_get", new_callable=AsyncMock, return_value=None),
        patch("modules.prospecting.router.cache_set", new_callable=AsyncMock),
        patch("modules.cnaes.router.cache_get", new_callable=AsyncMock, return_value=None),
        patch("modules.cnaes.router.cache_set", new_callable=AsyncMock),
        patch("modules.empresa.router.cache_get", new_callable=AsyncMock, return_value=None),
        patch("modules.empresa.router.cache_set", new_callable=AsyncMock),
        patch("modules.bairros.router.cache_get", new_callable=AsyncMock, return_value=None),
        patch("modules.bairros.router.cache_set", new_callable=AsyncMock),
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
