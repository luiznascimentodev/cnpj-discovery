"""Fixtures compartilhadas para testes da API."""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

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
    Injeta um pool mockado para evitar conexão real ao PostgreSQL.
    """
    app = create_app()

    with patch("main.create_pool", new_callable=AsyncMock) as mock_create:
        with patch("main.close_pool", new_callable=AsyncMock):
            with patch("database.get_pool", new_callable=AsyncMock, return_value=mock_pool):
                with patch("routers.prospecting.get_pool", new_callable=AsyncMock, return_value=mock_pool):
                    with patch("routers.export.get_pool", new_callable=AsyncMock, return_value=mock_pool):
                        with patch("routers.status.get_pool", new_callable=AsyncMock, return_value=mock_pool):
                            mock_create.return_value = mock_pool
                            async with AsyncClient(
                                transport=ASGITransport(app=app),
                                base_url="http://test",
                            ) as ac:
                                yield ac
