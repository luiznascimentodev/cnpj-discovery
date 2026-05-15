"""Testes para os routers prospecting, export e status — 100% de cobertura."""
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

import random

from modules.prospecting.router import _shuffle_preserving_demais_last, _sort_demais_last


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

    # cursor — asyncpg cursor factory is used directly as an async iterator.
    rows = cursor_rows if cursor_rows is not None else []

    async def _cursor_gen(*args, **kwargs):
        for row in rows:
            yield row

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

class TestProspectingSort:
    def test_sort_demais_last_preserves_other_rows_order(self):
        rows = [
            {"cnpj_completo": "1", "porte": 5},
            {"cnpj_completo": "2", "porte": 1},
            {"cnpj_completo": "3", "porte": 3},
            {"cnpj_completo": "4", "porte": 5},
        ]

        result = _sort_demais_last(rows)

        assert [row["cnpj_completo"] for row in result] == ["2", "3", "1", "4"]

    def test_shuffle_preserves_demais_at_the_end(self):
        rows = [
            {"cnpj_completo": "a", "porte": 1},
            {"cnpj_completo": "b", "porte": 3},
            {"cnpj_completo": "c", "porte": 2},
            {"cnpj_completo": "x", "porte": 5},
            {"cnpj_completo": "y", "porte": 5},
        ]

        result = _shuffle_preserving_demais_last(rows, random.Random(42))

        # primeiros 3 devem ser todos os não-demais, últimos 2 todos demais
        assert {row["cnpj_completo"] for row in result[:3]} == {"a", "b", "c"}
        assert {row["cnpj_completo"] for row in result[3:]} == {"x", "y"}
        # com seed fixo a ordem é determinística — protege contra regressão silenciosa
        assert [row["cnpj_completo"] for row in result] == ["b", "a", "c", "y", "x"]


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
        # Primeira página randomizada faz duas queries (enriched + non_enriched).
        # Ambas devem passar o filtro de UF=SP.
        assert mock_conn.fetch.call_count == 2
        for call in mock_conn.fetch.call_args_list:
            params = list(call.args[1:])
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

        response = await client.get("/v1/prospecting?limit=50")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_with_multiple_filters(self, client: AsyncClient, mock_pool):
        mock_conn = make_mock_conn(fetch_return=[EMPRESA_ROW])
        setup_pool(mock_pool, mock_conn)

        response = await client.get(
            "/v1/prospecting?uf=SP&situacao_cadastral=2&porte=3&limit=50"
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
    async def test_legacy_path_returns_cached_list_when_present(self, mock_pool):
        # Caminho não-randomizado (cursor): cache antigo em formato lista
        # deve continuar funcionando sem reconsultar o banco.
        app = __import__("main", fromlist=["create_app"]).create_app()
        from httpx import AsyncClient, ASGITransport
        from unittest.mock import AsyncMock, patch

        with patch("main.create_pool", new_callable=AsyncMock, return_value=mock_pool), \
             patch("main.close_pool", new_callable=AsyncMock), \
             patch("main.create_cache", new_callable=AsyncMock), \
             patch("main.close_cache", new_callable=AsyncMock), \
             patch("modules.prospecting.router.cache_get", new_callable=AsyncMock, return_value=[EMPRESA_ROW]), \
             patch("modules.prospecting.router.cache_set", new_callable=AsyncMock), \
             patch("modules.prospecting.router.get_pool", new_callable=AsyncMock, return_value=mock_pool):

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.get(
                    "/v1/prospecting?cursor_cnpj_basico=12345678&cursor_cnpj_ordem=0001"
                )

        assert response.status_code == 200
        assert len(response.json()) == 1

    @pytest.mark.asyncio
    async def test_search_with_direct_cnpj_skips_randomization(self, client: AsyncClient, mock_pool):
        # Quando o filtro é um CNPJ específico, a randomização da primeira página
        # deve ser desligada (faz lookup direto, sem inflar o pool).
        mock_conn = make_mock_conn(fetch_return=[EMPRESA_ROW])
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/prospecting?cnpj=12345678000190")
        assert response.status_code == 200

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

    @pytest.mark.asyncio
    async def test_search_returns_cache_hit(self, mock_pool):
        """Quando o cache Redis tem resultado, retorna sem ir ao banco."""
        app = __import__("main", fromlist=["create_app"]).create_app()
        from httpx import AsyncClient, ASGITransport
        from unittest.mock import AsyncMock, patch

        # Formato v2 do cache: dois pools (enriquecidas / não-enriquecidas) que
        # o router embaralha e concatena na resposta.
        cached_data = {"enriched": [EMPRESA_ROW], "non_enriched": []}

        with patch("main.create_pool", new_callable=AsyncMock, return_value=mock_pool), \
             patch("main.close_pool", new_callable=AsyncMock), \
             patch("main.create_cache", new_callable=AsyncMock), \
             patch("main.close_cache", new_callable=AsyncMock), \
             patch("modules.prospecting.router.cache_get", new_callable=AsyncMock, return_value=cached_data), \
             patch("modules.prospecting.router.cache_set", new_callable=AsyncMock), \
             patch("modules.prospecting.router.get_pool", new_callable=AsyncMock, return_value=mock_pool):

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.get("/v1/prospecting")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["cnpj_basico"] == "12345678"


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
    async def test_export_batches_large_result(self, client: AsyncClient, mock_pool):
        """Verifica que linhas são emitidas em batches quando ultrapassam _BATCH_ROWS."""
        from modules.export.router import _BATCH_ROWS
        rows = [EMPRESA_ROW] * (_BATCH_ROWS + 1)
        mock_conn = make_mock_conn(cursor_rows=rows)
        setup_pool(mock_pool, mock_conn)

        response = await client.get("/v1/export/csv")
        assert response.status_code == 200
        content = response.content.decode("utf-8-sig")
        data_lines = [l for l in content.splitlines() if l.strip()]
        assert len(data_lines) == _BATCH_ROWS + 2  # header + _BATCH_ROWS+1 data rows

    @pytest.mark.asyncio
    async def test_export_ignores_limit_and_cursor(self, client: AsyncClient, mock_pool):
        """Export must stream all rows for the filter, independent of visible pagination."""
        mock_conn = make_mock_conn(cursor_rows=[EMPRESA_ROW])
        setup_pool(mock_pool, mock_conn)

        response = await client.get(
            "/v1/export/csv?limit=10&cursor_cnpj_basico=12345678&cursor_cnpj_ordem=0001"
        )
        assert response.status_code == 200
        call_args = mock_conn.cursor.call_args[0]
        sql = call_args[0]
        assert "LIMIT" not in sql
        assert "(est.cnpj_basico, est.cnpj_ordem) >" not in sql

    @pytest.mark.asyncio
    async def test_export_logs_and_reraises_db_error(self, client: AsyncClient, mock_pool):
        """Erro durante o stream é logado e re-lançado (HTTP 200 já enviado, truncamento silencioso).

        Starlette 0.37+ / anyio 4+ executa o body generator num TaskGroup, então a
        exceção é relançada como ExceptionGroup — usamos Exception base para capturar ambos.
        """
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

        with pytest.raises(Exception):
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


# ─── /v1/cnaes ─────────────────────────────────────────────────────────────────


class TestCnaesRouter:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_data(self, client: AsyncClient):
        cached = {
            "all": [{"codigo": 6201500, "descricao": "Dev"}],
            "segments": [{"label": "Tecnologia, Software e Dados", "cnaes": [{"codigo": 6201500, "descricao": "Dev"}]}],
        }
        with patch("modules.cnaes.router.cache_get", AsyncMock(return_value=cached)):
            response = await client.get("/v1/cnaes")
        assert response.status_code == 200
        assert response.json() == cached

    @pytest.mark.asyncio
    async def test_cache_miss_fetches_from_db_and_returns_segments(self, client: AsyncClient):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {"codigo": 6201500, "descricao": "Desenvolvimento de programas"},
            {"codigo": 5611201, "descricao": "Restaurantes"},
        ])
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("modules.cnaes.router.cache_get", AsyncMock(return_value=None)):
            with patch("modules.cnaes.router.cache_set", AsyncMock()) as mock_set:
                with patch("modules.cnaes.router.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/cnaes")

        assert response.status_code == 200
        data = response.json()
        assert "all" in data
        assert "segments" in data
        assert data["all"][0]["codigo"] == 6201500
        labels = [s["label"] for s in data["segments"]]
        assert "Tecnologia, Software e Dados" in labels
        assert "Alimentos e Bebidas" in labels
        mock_set.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_miss_result_has_correct_structure(self, client: AsyncClient):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[{"codigo": 6201500, "descricao": "Dev"}])
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("modules.cnaes.router.cache_get", AsyncMock(return_value=None)):
            with patch("modules.cnaes.router.cache_set", AsyncMock()):
                with patch("modules.cnaes.router.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/cnaes")

        data = response.json()
        seg = data["segments"][0]
        assert data["all"][0]["codigo"] == 6201500
        assert "label" in seg
        assert "cnaes" in seg
        assert seg["cnaes"][0]["codigo"] == 6201500


# ─── /v1/empresa/{cnpj} ────────────────────────────────────────────────────────


DETAIL_ROW = {
    "cnpj_basico": "12345678", "cnpj_ordem": "0001", "cnpj_dv": "90",
    "cnpj_completo": "12345678000190", "razao_social": "TESTE LTDA",
    "nome_fantasia": None, "situacao_cadastral": 2, "data_situacao": None,
    "motivo_situacao": None, "porte": 3, "natureza_juridica": 2062,
    "ente_federativo": None, "data_inicio": None, "matriz_filial": 1,
    "tipo_logradouro": "RUA", "logradouro": "TESTE", "numero": "100",
    "complemento": None, "bairro": "CENTRO", "cep": "01310100",
    "uf": "SP", "municipio": 3550308, "municipio_descricao": "São Paulo",
    "capital_social": 50000.0, "email": "teste@empresa.com",
    "telefone1": "1133334444", "telefone2": None, "fax": None,
    "cnae_principal": 6201500, "cnae_principal_descricao": "Dev de software",
    "cnae_secundarios": None,
}


def make_empresa_pool(
    fetchrow_side,
    fetch_side,
    crawler_domains=None,
    crawler_contacts=None,
    enrichment_attempted=False,
):
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(side_effect=fetchrow_side)
    mock_conn.fetch = AsyncMock(
        side_effect=[
            *fetch_side,
            crawler_domains or [],
            crawler_contacts or [],
        ]
    )
    # fetchval só é chamado quando NÃO há domains/contacts (para checar se o
    # worker já rodou). Default False => "nunca rodou".
    mock_conn.fetchval = AsyncMock(return_value=enrichment_attempted)
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool


class TestEmpresaRouter:
    @pytest.mark.asyncio
    async def test_found_without_punctuation(self, client: AsyncClient):
        pool = make_empresa_pool([DETAIL_ROW, None], [[]])
        with patch("modules.empresa.router.cache_get", AsyncMock(return_value=None)):
            with patch("modules.empresa.router.cache_set", AsyncMock()):
                with patch("modules.empresa.router.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/empresa/12345678000190")
        assert response.status_code == 200
        data = response.json()
        assert data["cnpj_completo"] == "12345678000190"
        assert data["razao_social"] == "TESTE LTDA"

    @pytest.mark.asyncio
    async def test_found_with_punctuation(self, client: AsyncClient):
        pool = make_empresa_pool([DETAIL_ROW, None], [[]])
        with patch("modules.empresa.router.cache_get", AsyncMock(return_value=None)):
            with patch("modules.empresa.router.cache_set", AsyncMock()):
                with patch("modules.empresa.router.get_pool", AsyncMock(return_value=pool)):
                    # dots and hyphens only — slashes can't be URL path segments
                    response = await client.get("/v1/empresa/12.345.678.0001-90")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self, client: AsyncClient):
        pool = make_empresa_pool([None], [[]])
        with patch("modules.empresa.router.cache_get", AsyncMock(return_value=None)):
            with patch("modules.empresa.router.cache_set", AsyncMock()):
                with patch("modules.empresa.router.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/empresa/00000000000000")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_cnpj_returns_422(self, client: AsyncClient):
        with patch("modules.empresa.router.cache_get", AsyncMock(return_value=None)):
            response = await client.get("/v1/empresa/123")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self, client: AsyncClient):
        cached = {**DETAIL_ROW, "cnae_secundarios": [], "socios": [], "simples": None}
        with patch("modules.empresa.router.cache_get", AsyncMock(return_value=cached)):
            with patch("modules.empresa.router.get_pool") as mock_get_pool:
                response = await client.get("/v1/empresa/12345678000190")
        assert response.status_code == 200
        mock_get_pool.assert_not_called()

    @pytest.mark.asyncio
    async def test_socios_included(self, client: AsyncClient):
        socio = {
            "nome_socio": "MARIA", "cpf_cnpj_socio": "***", "qualificacao": 49,
            "qualificacao_descricao": "Sócio", "data_entrada": None, "faixa_etaria": None,
        }
        pool = make_empresa_pool([DETAIL_ROW, None], [[socio]])
        with patch("modules.empresa.router.cache_get", AsyncMock(return_value=None)):
            with patch("modules.empresa.router.cache_set", AsyncMock()):
                with patch("modules.empresa.router.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/empresa/12345678000190")
        assert response.status_code == 200
        assert response.json()["socios"][0]["nome_socio"] == "MARIA"

    @pytest.mark.asyncio
    async def test_enrichment_available_flag_false_by_default(self, client: AsyncClient):
        pool = make_empresa_pool([DETAIL_ROW, None], [[]])
        with patch("modules.empresa.router.cache_get", AsyncMock(return_value=None)):
            with patch("modules.empresa.router.cache_set", AsyncMock()):
                with patch("modules.empresa.router.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/empresa/12345678000190")
        body = response.json()
        assert body["enrichment_available"] is False
        assert body["enrichment_required_feature"] is None
        assert body["crawler_enrichment"] == {"status": "not_enriched", "domains": [], "contacts": []}

    @pytest.mark.asyncio
    async def test_enrichment_no_public_data_when_worker_ran_but_found_nothing(
        self, client: AsyncClient
    ):
        # Worker rodou (enrichment_targets.status='done') mas nenhum domain/contact
        # foi publicado. Status deve ser "no_public_data" — diferente de "nunca rodou".
        pool = make_empresa_pool([DETAIL_ROW, None], [[]], enrichment_attempted=True)
        with patch("modules.empresa.router.cache_get", AsyncMock(return_value=None)):
            with patch("modules.empresa.router.cache_set", AsyncMock()):
                with patch("modules.empresa.router.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/empresa/12345678000190")
        body = response.json()
        assert body["enrichment_available"] is False
        assert body["crawler_enrichment"]["status"] == "no_public_data"
        assert body["crawler_enrichment"]["domains"] == []
        assert body["crawler_enrichment"]["contacts"] == []

    @pytest.mark.asyncio
    async def test_enrichment_data_is_included_in_separate_block(self, client: AsyncClient):
        domain = {
            "domain": "teste.com.br",
            "homepage_url": "https://teste.com.br",
            "source": "rf_email_domain",
            "confidence": 95,
            "status": "verified",
            "first_seen": None,
            "last_seen": None,
        }
        contact = {
            "contact_type": "email",
            "value": "vendas@teste.com.br",
            "normalized_value": "vendas@teste.com.br",
            "label": "Vendas",
            "source": "official_site",
            "confidence": 100,
            "evidence_url": "https://teste.com.br/contato",
            "source_domain": "teste.com.br",
            "first_seen": None,
            "last_seen": None,
        }
        pool = make_empresa_pool([DETAIL_ROW, None], [[]], crawler_domains=[domain], crawler_contacts=[contact])
        with patch("modules.empresa.router.cache_get", AsyncMock(return_value=None)):
            with patch("modules.empresa.router.cache_set", AsyncMock()):
                with patch("modules.empresa.router.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/empresa/12345678000190")
        body = response.json()
        assert body["enrichment_available"] is True
        assert body["enrichment_required_feature"] == "crawler_contacts"
        assert body["crawler_enrichment"]["status"] == "done"
        assert body["crawler_enrichment"]["domains"][0]["domain"] == "teste.com.br"
        assert body["crawler_enrichment"]["contacts"][0]["value"] == "vendas@teste.com.br"

    @pytest.mark.asyncio
    async def test_simples_nacional_included(self, client: AsyncClient):
        simples = {
            "opcao_simples": "S", "data_opcao_simples": None, "data_exc_simples": None,
            "opcao_mei": "N", "data_opcao_mei": None, "data_exc_mei": None,
        }
        pool = make_empresa_pool([DETAIL_ROW, simples], [[]])
        with patch("modules.empresa.router.cache_get", AsyncMock(return_value=None)):
            with patch("modules.empresa.router.cache_set", AsyncMock()):
                with patch("modules.empresa.router.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/empresa/12345678000190")
        assert response.json()["simples"]["opcao_simples"] == "S"

    @pytest.mark.asyncio
    async def test_cnae_secundarios_parsed_and_resolved(self, client: AsyncClient):
        row = {**DETAIL_ROW, "cnae_secundarios": "6209100,4321500"}
        cnae_rows = [
            {"codigo": 6209100, "descricao": "Suporte TI"},
            {"codigo": 4321500, "descricao": "Instalações"},
        ]
        pool = make_empresa_pool([row, None], [cnae_rows, []])
        with patch("modules.empresa.router.cache_get", AsyncMock(return_value=None)):
            with patch("modules.empresa.router.cache_set", AsyncMock()):
                with patch("modules.empresa.router.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/empresa/12345678000190")
        secundarios = response.json()["cnae_secundarios"]
        assert len(secundarios) == 2
        assert secundarios[0]["codigo"] == 6209100


class TestBairrosRouter:
    @pytest.mark.asyncio
    async def test_returns_empty_when_q_too_short(self, client: AsyncClient):
        response = await client.get("/v1/bairros?uf=SP&q=c")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_q_missing(self, client: AsyncClient):
        response = await client.get("/v1/bairros?uf=SP")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_requires_uf(self, client: AsyncClient):
        response = await client.get("/v1/bairros?q=centro")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_cache_hit_returns_data(self, client: AsyncClient):
        cached = [{"bairro": "CENTRO", "municipio": None, "municipio_descricao": None}]
        with patch("modules.bairros.router.cache_get", AsyncMock(return_value=cached)):
            response = await client.get("/v1/bairros?uf=SP&q=centro&municipio=3550308")
        assert response.status_code == 200
        assert response.json() == cached

    @pytest.mark.asyncio
    async def test_bairro_requires_municipio(self, client: AsyncClient):
        response = await client.get("/v1/bairros?uf=PR&q=sitio")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_bairro_is_restricted_by_municipio(self, client: AsyncClient):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {"bairro": "CENTRO", "municipio": None, "municipio_descricao": None},
        ])
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("modules.bairros.router.cache_get", AsyncMock(return_value=None)):
            with patch("modules.bairros.router.cache_set", AsyncMock()):
                with patch("modules.bairros.router.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/bairros?uf=SP&q=centro&municipio=3550308")
        data = response.json()
        assert response.status_code == 200
        assert data[0]["bairro"] == "CENTRO"
        call_args = mock_conn.fetch.call_args[0]
        assert call_args[1] == "SP"
        assert call_args[3] == 3550308

    @pytest.mark.asyncio
    async def test_uf_is_uppercased(self, client: AsyncClient):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {"bairro": "FLAMENGO", "municipio": None, "municipio_descricao": None},
        ])
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("modules.bairros.router.cache_get", AsyncMock(return_value=None)):
            with patch("modules.bairros.router.cache_set", AsyncMock()):
                with patch("modules.bairros.router.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/bairros?uf=rj&q=flamengo&municipio=3304557")
        assert response.status_code == 200
        call_args = mock_conn.fetch.call_args[0]
        assert call_args[1] == "RJ"

    @pytest.mark.asyncio
    async def test_municipios_returns_empty_when_q_too_short(self, client: AsyncClient):
        response = await client.get("/v1/municipios?uf=SP&q=s")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_municipios_cache_hit_returns_data(self, client: AsyncClient):
        cached = [{"codigo": 3550308, "descricao": "SAO PAULO", "total_estabelecimentos": 100}]
        with patch("modules.bairros.router.cache_get", AsyncMock(return_value=cached)):
            response = await client.get("/v1/municipios?uf=SP&q=sao")
        assert response.status_code == 200
        assert response.json() == cached

    @pytest.mark.asyncio
    async def test_municipios_cache_miss_fetches_from_lookup(self, client: AsyncClient):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {"codigo": 3550308, "descricao": "SAO PAULO", "total_estabelecimentos": 1200000},
        ])
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("modules.bairros.router.cache_get", AsyncMock(return_value=None)):
            with patch("modules.bairros.router.cache_set", AsyncMock()) as mock_cache_set:
                with patch("modules.bairros.router.get_pool", AsyncMock(return_value=pool)):
                    response = await client.get("/v1/municipios?uf=sp&q=sao")
        assert response.status_code == 200
        data = response.json()
        assert data[0]["codigo"] == 3550308
        call_args = mock_conn.fetch.call_args[0]
        assert call_args[1] == "SP"
        assert call_args[2] == "%SAO%"
        mock_cache_set.assert_called_once()
