from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from server import create_app


@pytest.fixture
async def client():
    app = create_app()
    with (
        patch("server.create_pool", new_callable=AsyncMock),
        patch("server.close_pool", new_callable=AsyncMock),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


@pytest.fixture(autouse=True)
def mock_dns_exists(monkeypatch):
    """DNS lookups always return True in tests (no actual network calls)."""
    async def _always_true(domain: str, *, timeout: float = 3.0) -> bool:
        return True

    monkeypatch.setattr("discovery.pipeline.dns_exists", _always_true)

