import httpx
import pytest

from discovery.brasilapi import BrasilAPIResult, fetch_cnpj


def _make_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=httpx.Timeout(5.0))


class TestFetchCnpj:
    @pytest.mark.asyncio
    async def test_returns_result_on_200(self):
        def handler(_request):
            return httpx.Response(200, json={
                "email": "contato@empresa.com.br",
                "ddd_telefone_1": "11 12345678",
                "ddd_telefone_2": "",
            })

        async with _make_client(handler) as client:
            result = await fetch_cnpj("12345678000190", client=client)

        assert result == BrasilAPIResult(
            email="contato@empresa.com.br",
            ddd_telefone_1="11 12345678",
            ddd_telefone_2=None,
        )

    @pytest.mark.asyncio
    async def test_returns_none_on_429(self):
        def handler(_request):
            return httpx.Response(429)

        async with _make_client(handler) as client:
            result = await fetch_cnpj("12345678000190", client=client)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_404(self):
        def handler(_request):
            return httpx.Response(404, json={"message": "CNPJ não encontrado"})

        async with _make_client(handler) as client:
            result = await fetch_cnpj("00000000000000", client=client)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_http_error(self):
        def handler(request):
            raise httpx.ConnectError("connection refused", request=request)

        async with _make_client(handler) as client:
            result = await fetch_cnpj("12345678000190", client=client)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_malformed_json(self):
        def handler(_request):
            return httpx.Response(200, content=b"not-json", headers={"content-type": "text/plain"})

        async with _make_client(handler) as client:
            result = await fetch_cnpj("12345678000190", client=client)

        assert result is None

    @pytest.mark.asyncio
    async def test_uses_custom_base_url(self):
        seen_urls = []

        def handler(request):
            seen_urls.append(str(request.url))
            return httpx.Response(200, json={"email": None, "ddd_telefone_1": None, "ddd_telefone_2": None})

        async with _make_client(handler) as client:
            await fetch_cnpj("12345678000190", client=client, base_url="http://mock-api")

        assert seen_urls[0] == "http://mock-api/cnpj/v1/12345678000190"

    @pytest.mark.asyncio
    async def test_handles_missing_fields_as_none(self):
        def handler(_request):
            return httpx.Response(200, json={"razao_social": "Empresa Sem Email LTDA"})

        async with _make_client(handler) as client:
            result = await fetch_cnpj("12345678000190", client=client)

        assert result == BrasilAPIResult(email=None, ddd_telefone_1=None, ddd_telefone_2=None)

    @pytest.mark.asyncio
    async def test_extracts_qsa_names(self):
        def handler(_request):
            return httpx.Response(200, json={
                "email": "contato@empresa.com.br",
                "ddd_telefone_1": "11 12345678",
                "ddd_telefone_2": None,
                "qsa": [
                    {"nome_socio": "João da Silva", "qual_socio": "49-Sócio-Administrador"},
                    {"nome_socio": "Maria Souza", "qual_socio": "22-Sócio"},
                ],
            })

        async with _make_client(handler) as client:
            result = await fetch_cnpj("12345678000190", client=client)

        assert result.qsa_names == ["João da Silva", "Maria Souza"]

    @pytest.mark.asyncio
    async def test_qsa_names_empty_when_missing(self):
        def handler(_request):
            return httpx.Response(200, json={
                "email": None,
                "ddd_telefone_1": None,
                "ddd_telefone_2": None,
            })

        async with _make_client(handler) as client:
            result = await fetch_cnpj("12345678000190", client=client)

        assert result.qsa_names == []

    @pytest.mark.asyncio
    async def test_qsa_names_skips_blank_entries(self):
        def handler(_request):
            return httpx.Response(200, json={
                "email": None,
                "ddd_telefone_1": None,
                "ddd_telefone_2": None,
                "qsa": [
                    {"nome_socio": "", "qual_socio": "22-Sócio"},
                    {"nome_socio": "Pedro Lima"},
                ],
            })

        async with _make_client(handler) as client:
            result = await fetch_cnpj("12345678000190", client=client)

        assert result.qsa_names == ["Pedro Lima"]
