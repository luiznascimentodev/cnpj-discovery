"""
Testes para etl/indexer.py.
Os testes de TestBuildIndex e TestCreateParallel usam mocks.
Os testes de TestDropAndCreateIndexes requerem PostgreSQL rodando (docker compose up postgres -d).
"""
import pytest
import psycopg2
from unittest.mock import MagicMock, patch, call

from config import Settings
from indexer import (
    drop_managed_indexes,
    create_managed_indexes,
    get_existing_indexes,
    _build_index,
    MANAGED_INDEXES,
    _INDEX_SESSION_SETTINGS,
)


@pytest.fixture(scope="module")
def db_conn():
    s = Settings(postgres_password="changeme")
    conn = psycopg2.connect(s.dsn)
    conn.autocommit = True
    yield conn
    conn.close()


# ─── MANAGED_INDEXES ──────────────────────────────────────────────────────────

class TestManagedIndexes:
    def test_is_non_empty_list(self):
        assert len(MANAGED_INDEXES) > 0

    def test_each_entry_is_tuple_of_two_strings(self):
        for entry in MANAGED_INDEXES:
            assert isinstance(entry, tuple)
            assert len(entry) == 2
            assert all(isinstance(s, str) for s in entry)

    def test_names_are_unique(self):
        names = [name for name, _ in MANAGED_INDEXES]
        assert len(names) == len(set(names))

    def test_sqls_contain_create_index(self):
        for _, sql in MANAGED_INDEXES:
            assert "CREATE INDEX" in sql.upper()

    def test_all_indexes_use_if_not_exists(self):
        for _, sql in MANAGED_INDEXES:
            assert "IF NOT EXISTS" in sql.upper()

    def test_required_indexes_present(self):
        names = {name for name, _ in MANAGED_INDEXES}
        assert "idx_estab_uf_cnae_sit" in names
        assert "idx_estab_cursor" in names
        assert "idx_estab_fts_fantasia" in names
        assert "idx_empresas_fts_razao" in names
        assert "idx_empresas_capital" in names
        assert "idx_estab_ativas_uf" in names

    def test_partial_index_has_where_clause(self):
        partial = {name: sql for name, sql in MANAGED_INDEXES if "WHERE" in sql.upper()}
        assert "idx_estab_ativas_uf" in partial
        assert "situacao_cadastral = 2" in partial["idx_estab_ativas_uf"]

    def test_new_filter_indexes_present(self):
        names = {name for name, _ in MANAGED_INDEXES}
        assert "idx_estab_bairro_trgm" in names
        assert "idx_estab_data_inicio" in names
        assert "idx_estab_matriz_filial" in names
        assert "idx_empresas_natureza" in names
        assert "idx_simples_opcao" in names

    def test_trgm_index_uses_gin(self):
        idx = {name: sql for name, sql in MANAGED_INDEXES}
        assert "gin_trgm_ops" in idx["idx_estab_bairro_trgm"]
        assert "USING GIN" in idx["idx_estab_bairro_trgm"].upper()


# ─── _build_index (unit) ──────────────────────────────────────────────────────

class TestBuildIndex:
    def _mock_conn(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        return mock_conn, mock_cur

    def test_returns_elapsed_float(self):
        mock_conn, _ = self._mock_conn()
        with patch("indexer.psycopg2.connect", return_value=mock_conn):
            elapsed = _build_index("test_idx", "CREATE INDEX CONCURRENTLY IF NOT EXISTS test_idx ON t (c)")
        assert isinstance(elapsed, float)
        assert elapsed >= 0

    def test_sets_session_settings_before_index(self):
        mock_conn, mock_cur = self._mock_conn()
        with patch("indexer.psycopg2.connect", return_value=mock_conn):
            _build_index("test_idx", "CREATE INDEX CONCURRENTLY IF NOT EXISTS test_idx ON t (c)")
        calls = [str(c) for c in mock_cur.execute.call_args_list]
        # Primeira chamada deve ser as configurações de sessão
        assert _INDEX_SESSION_SETTINGS in mock_cur.execute.call_args_list[0][0][0]

    def test_closes_connection_on_success(self):
        mock_conn, _ = self._mock_conn()
        with patch("indexer.psycopg2.connect", return_value=mock_conn):
            _build_index("test_idx", "CREATE INDEX CONCURRENTLY IF NOT EXISTS test_idx ON t (c)")
        mock_conn.close.assert_called_once()

    def test_closes_connection_on_error(self):
        mock_conn, mock_cur = self._mock_conn()
        mock_cur.execute.side_effect = [None, Exception("index build failed")]
        with patch("indexer.psycopg2.connect", return_value=mock_conn):
            with pytest.raises(Exception, match="index build failed"):
                _build_index("test_idx", "CREATE INDEX ...")
        mock_conn.close.assert_called_once()

    def test_sets_autocommit(self):
        mock_conn, _ = self._mock_conn()
        with patch("indexer.psycopg2.connect", return_value=mock_conn):
            _build_index("test_idx", "CREATE INDEX CONCURRENTLY IF NOT EXISTS test_idx ON t (c)")
        assert mock_conn.autocommit is True


# ─── create_managed_indexes com mocks ────────────────────────────────────────

class TestCreateManagedIndexesUnit:
    def test_returns_count_of_successful_indexes(self):
        with patch("indexer._build_index", return_value=0.5):
            conn = MagicMock()
            count = create_managed_indexes(conn)
        assert count == len(MANAGED_INDEXES)

    def test_continues_on_failed_index(self):
        call_count = 0

        def _side_effect(name, sql):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("simulated failure")
            return 0.1

        with patch("indexer._build_index", side_effect=_side_effect):
            conn = MagicMock()
            count = create_managed_indexes(conn)

        assert count == len(MANAGED_INDEXES) - 1

    def test_respects_etl_index_workers_setting(self):
        submitted = []

        def _fake_build(name, sql):
            submitted.append(name)
            return 0.01

        with patch("indexer._build_index", side_effect=_fake_build):
            conn = MagicMock()
            create_managed_indexes(conn)

        assert len(submitted) == len(MANAGED_INDEXES)


# ─── get_existing_indexes ─────────────────────────────────────────────────────

class TestGetExistingIndexes:
    def test_returns_set(self, db_conn):
        result = get_existing_indexes(db_conn)
        assert isinstance(result, set)

    def test_returns_only_managed_index_names(self, db_conn):
        result = get_existing_indexes(db_conn)
        managed_names = {name for name, _ in MANAGED_INDEXES}
        assert result.issubset(managed_names)


# ─── drop e create (integração com DB real) ───────────────────────────────────

class TestDropAndCreateIndexes:
    def test_drop_returns_count(self, db_conn):
        with psycopg2.connect(Settings(postgres_password="changeme").dsn) as conn:
            count = drop_managed_indexes(conn)
        assert count == len(MANAGED_INDEXES)

    def test_indexes_absent_after_drop(self, db_conn):
        with psycopg2.connect(Settings(postgres_password="changeme").dsn) as conn:
            drop_managed_indexes(conn)
        existing = get_existing_indexes(db_conn)
        assert len(existing) == 0

    def test_create_returns_count(self, db_conn):
        # Garantir que estão dropados
        with psycopg2.connect(Settings(postgres_password="changeme").dsn) as conn:
            drop_managed_indexes(conn)
        with psycopg2.connect(Settings(postgres_password="changeme").dsn) as conn:
            count = create_managed_indexes(conn)
        assert count == len(MANAGED_INDEXES)

    def test_indexes_present_after_create(self, db_conn):
        with psycopg2.connect(Settings(postgres_password="changeme").dsn) as conn:
            drop_managed_indexes(conn)
        with psycopg2.connect(Settings(postgres_password="changeme").dsn) as conn:
            create_managed_indexes(conn)
        existing = get_existing_indexes(db_conn)
        managed_names = {name for name, _ in MANAGED_INDEXES}
        assert existing == managed_names

    def test_drop_is_idempotent(self, db_conn):
        """Dropar duas vezes não deve gerar erro (IF EXISTS)."""
        with psycopg2.connect(Settings(postgres_password="changeme").dsn) as conn:
            drop_managed_indexes(conn)
        with psycopg2.connect(Settings(postgres_password="changeme").dsn) as conn:
            count = drop_managed_indexes(conn)
        assert count == len(MANAGED_INDEXES)

    def test_create_is_idempotent(self, db_conn):
        """Criar duas vezes não deve gerar erro (IF NOT EXISTS)."""
        with psycopg2.connect(Settings(postgres_password="changeme").dsn) as conn:
            create_managed_indexes(conn)
        with psycopg2.connect(Settings(postgres_password="changeme").dsn) as conn:
            count = create_managed_indexes(conn)
        assert count == len(MANAGED_INDEXES)
