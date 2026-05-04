"""
Testes para etl/indexer.py.
Requerem PostgreSQL rodando (docker compose up postgres -d).
"""
import pytest
import psycopg2

from config import Settings
from indexer import (
    drop_managed_indexes,
    create_managed_indexes,
    get_existing_indexes,
    MANAGED_INDEXES,
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


# ─── get_existing_indexes ─────────────────────────────────────────────────────

class TestGetExistingIndexes:
    def test_returns_set(self, db_conn):
        result = get_existing_indexes(db_conn)
        assert isinstance(result, set)

    def test_returns_only_managed_index_names(self, db_conn):
        result = get_existing_indexes(db_conn)
        managed_names = {name for name, _ in MANAGED_INDEXES}
        assert result.issubset(managed_names)


# ─── drop e create ───────────────────────────────────────────────────────────

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
