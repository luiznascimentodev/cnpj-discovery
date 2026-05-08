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

