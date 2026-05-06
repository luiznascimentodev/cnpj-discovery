"""Testes para os routers prospecting, export e status — 100% de cobertura."""
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch


# ─── Dados de apoio ────────────────────────────────────────────────────────────

EMPRESA_ROW = {
    "cnpj_basico": "12345678",
    "cnpj_ordem": "0001",
    "cnpj_dv": "00",
    "cnpj_completo": "123456780001 00",
    "razao_social": "EMPRESA TESTE LTDA",
    "nome_fantasia": "TESTE",
    "situacao_cadastral": 2,
    "cnae_principal": 6201500,
    "cnae_descricao": "Desenvolvimento de programas de computador sob encomenda",
    "uf": "SP",
    "municipio": 7107,
    "municipio_descricao": "SAO PAULO",
    "email": "contato@teste.com.br",
    "telefone1": "1199999999",
    "porte": 3,
    "capital_social": 100000.0,
    "data_inicio": None,
}


def make_mock_conn(
    fetch_return=None,
    fetchval_side_effect=None,
    cursor_rows=None,
):
    """Cria um mock de conexão asyncpg configurado para os testes."""
    mock_conn = AsyncMock()

    # fetch
    mock_conn.fetch.return_value = fetch_return if fetch_return is not None else []

    # fetchval — pode receber side_effect para retornar valores diferentes por chamada
    if fetchval_side_effect is not None:
        mock_conn.fetchval.side_effect = fetchval_side_effect

    # cursor — deve retornar um async iterator diretamente (não corrotina)
    # conn.cursor() é usado como `async for row in conn.cursor(...):`
    rows = cursor_rows if cursor_rows is not None else []

    async def _cursor_gen(*args, **kwargs):
        for row in rows:
            yield row

    # cursor deve ser MagicMock para que cursor() retorne o async generator
    # diretamente, sem ser awaited
    mock_conn.cursor = MagicMock(return_value=_cursor_gen())

    # transaction() — deve retornar um async context manager diretamente
    # (não pode ser AsyncMock pois transaction() não é awaited, é usado como
    # `async with conn.transaction():`)
    mock_txn = MagicMock()
    mock_txn.__aenter__ = AsyncMock(return_value=None)
    mock_txn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.transaction = MagicMock(return_value=mock_txn)

    return mock_conn


def setup_pool(mock_pool, mock_conn):
    """Configura mock_pool.acquire() como async context manager retornando mock_conn."""
    acquire_ctx = MagicMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    acquire_ctx.__aexit__ = AsyncMock(return_value=False)
    # acquire deve ser um MagicMock (não AsyncMock) para que pool.acquire()
    # retorne o ctx manager diretamente, sem ser uma corrotina
    mock_pool.acquire = MagicMock(return_value=acquire_ctx)


# ─── Prospecting router ────────────────────────────────────────────────────────

class TestProspectingRouter:
    @pytest.mark.asyncio
    async def test_search_returns_200(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(fetch_return=[EMPRESA_ROW])
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/prospecting")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_returns_list(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(fetch_return=[EMPRESA_ROW])
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/prospecting")
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

    @pytest.mark.asyncio
    async def test_search_returns_empresa_fields(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(fetch_return=[EMPRESA_ROW])
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/prospecting")
        empresa = response.json()[0]
        assert empresa["cnpj_basico"] == "12345678"
        assert empresa["razao_social"] == "EMPRESA TESTE LTDA"
        assert empresa["uf"] == "SP"

    @pytest.mark.asyncio
    async def test_search_empty_result(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(fetch_return=[])
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/prospecting")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_search_with_uf_filter(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(fetch_return=[EMPRESA_ROW])
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/prospecting?uf=SP")
        assert response.status_code == 200
        mock_conn.fetch.assert_called_once()
        sql, *params = mock_conn.fetch.call_args[0]
        assert "SP" in params

    @pytest.mark.asyncio
    async def test_search_with_situacao_cadastral(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(fetch_return=[EMPRESA_ROW])
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/prospecting?situacao_cadastral=2")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_with_limit(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(fetch_return=[EMPRESA_ROW])
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/prospecting?limit=10")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_with_multiple_filters(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(fetch_return=[EMPRESA_ROW])
        setup_pool(mock_pool, mock_conn)

        response = await client.get(
            "/v1/prospecting?uf=SP&situacao_cadastral=2&porte=3&limit=20"
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_multiple_rows(self, client: AsyncClient, mock_pool):
        second_row = dict(EMPRESA_ROW)
        second_row["cnpj_basico"] = "87654321"
        mock_conn = make_mock_conn(fetch_return=[EMPRESA_ROW, second_row])
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/prospecting")
        assert len(response.json()) == 2

    @pytest.mark.asyncio
    async def test_search_response_matches_empresa_schema(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(fetch_return=[EMPRESA_ROW])
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/prospecting")
        empresa = response.json()[0]
        # Verifica campos obrigatórios do EmpresaOut
        for field in ("cnpj_basico", "cnpj_ordem", "cnpj_dv", "cnpj_completo", "razao_social"):
            assert field in empresa

    @pytest.mark.asyncio
    async def test_search_with_cursor_pagination(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(fetch_return=[EMPRESA_ROW])
        setup_pool(mock_pool, mock_conn)

        response = await client.get(
            "/v1/prospecting?cursor_cnpj_basico=12345678&cursor_cnpj_ordem=0001"
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_with_capital_social(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(fetch_return=[EMPRESA_ROW])
        setup_pool(mock_pool, mock_conn)

        response = await client.get(
            "/v1/prospecting?capital_social_min=1000&capital_social_max=999999"
        )
        assert response.status_code == 200


# ─── Export router ─────────────────────────────────────────────────────────────

class TestExportRouter:
    @pytest.mark.asyncio
    async def test_export_returns_200(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(cursor_rows=[EMPRESA_ROW])
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/export/csv")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_export_content_type_csv(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(cursor_rows=[EMPRESA_ROW])
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/export/csv")
        assert "text/csv" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_export_content_disposition(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(cursor_rows=[EMPRESA_ROW])
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/export/csv")
        assert response.headers["content-disposition"] == "attachment; filename=leads.csv"

    @pytest.mark.asyncio
    async def test_export_has_header_row(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(cursor_rows=[EMPRESA_ROW])
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/export/csv")
        content = response.content.decode("utf-8-sig")
        first_line = content.splitlines()[0]
        assert "cnpj_basico" in first_line
        assert "razao_social" in first_line

    @pytest.mark.asyncio
    async def test_export_has_data_row(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(cursor_rows=[EMPRESA_ROW])
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/export/csv")
        content = response.content.decode("utf-8-sig")
        lines = content.splitlines()
        assert len(lines) >= 2
        assert "12345678" in lines[1]

    @pytest.mark.asyncio
    async def test_export_empty_result(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(cursor_rows=[])
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/export/csv")
        assert response.status_code == 200
        assert response.content == b""

    @pytest.mark.asyncio
    async def test_export_with_filters(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(cursor_rows=[EMPRESA_ROW])
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/export/csv?uf=SP&situacao_cadastral=2")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_export_limit_overridden_to_100k(self, client: AsyncClient, mock_pool):
        """Verifica que o limit do filtro é sempre 100_000 no export."""
        mock_conn = make_mock_conn(cursor_rows=[EMPRESA_ROW])
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/export/csv?limit=10")
        assert response.status_code == 200
        # O SQL gerado deve conter LIMIT 100000
        call_args = mock_conn.cursor.call_args[0]
        sql = call_args[0]
        assert "LIMIT 100000" in sql

    @pytest.mark.asyncio
    async def test_export_logs_and_reraises_db_error(self, client: AsyncClient, mock_pool):
        """Erro durante o stream é logado e re-lançado (HTTP 200 já enviado, truncamento silencioso)."""
        mock_conn = AsyncMock()

        async def _failing_cursor(*args, **kwargs):
            raise RuntimeError("DB explodiu durante o stream")
            yield  # torna a função async generator sem chegar aqui

        mock_conn.cursor = MagicMock(return_value=_failing_cursor())
        mock_txn = MagicMock()
        mock_txn.__aenter__ = AsyncMock(return_value=None)
        mock_txn.__aexit__ = AsyncMock(return_value=False)
        mock_conn.transaction = MagicMock(return_value=mock_txn)
        setup_pool(mock_pool, mock_conn)

        with pytest.raises(RuntimeError, match="DB explodiu"):
            await client.get("/v1/export/csv")


# ─── Status router ─────────────────────────────────────────────────────────────

class TestStatusRouter:
    @pytest.mark.asyncio
    async def test_status_returns_200(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(fetchval_side_effect=[1000000, 5000000])
        mock_conn.fetch.return_value = []
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/status")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_status_returns_total_empresas(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(fetchval_side_effect=[1000000, 5000000])
        mock_conn.fetch.return_value = []
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/status")
        data = response.json()
        assert data["total_empresas"] == 1000000

    @pytest.mark.asyncio
    async def test_status_returns_total_estabelecimentos(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(fetchval_side_effect=[1000000, 5000000])
        mock_conn.fetch.return_value = []
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/status")
        data = response.json()
        assert data["total_estabelecimentos"] == 5000000

    @pytest.mark.asyncio
    async def test_status_returns_etl_files(self, client: AsyncClient, mock_pool):
        etl_row = {"arquivo": "Empresas0.zip", "status": "done", "loaded_at": None}
        mock_conn = make_mock_conn(fetchval_side_effect=[100, 500])
        mock_conn.fetch.return_value = [etl_row]
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/status")
        data = response.json()
        assert "etl_files" in data
        assert isinstance(data["etl_files"], list)
        assert data["etl_files"][0]["arquivo"] == "Empresas0.zip"

    @pytest.mark.asyncio
    async def test_status_etl_files_empty(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(fetchval_side_effect=[0, 0])
        mock_conn.fetch.return_value = []
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/status")
        data = response.json()
        assert data["etl_files"] == []

    @pytest.mark.asyncio
    async def test_status_has_all_keys(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(fetchval_side_effect=[42, 99])
        mock_conn.fetch.return_value = []
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/status")
        data = response.json()
        assert "total_empresas" in data
        assert "total_estabelecimentos" in data
        assert "etl_files" in data
